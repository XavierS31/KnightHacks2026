"""Bounded browser mechanics against an explicit mock, never production trial records."""
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import model_validator

from backend.app.features.personas.mock_handoff import MockHandoff, select_task
from backend.app.shared.contracts import Contract, Persona


class ObservedTarget(Contract):
    id: str
    name: str


class BrowserDecision(Contract):
    kind: Literal["click", "stop"]
    target_id: str | None

    @model_validator(mode="after")
    def target_matches_action(self):
        if (self.kind == "click") != (self.target_id is not None):
            raise ValueError("Click requires a target; stop cannot have a target")
        return self


class DecisionPolicy(Protocol):
    async def decide(self, targets: list[ObservedTarget]) -> BrowserDecision: ...


class ScriptedMockPolicy:
    """Fixture choice script, explicitly not model inference."""

    def __init__(self):
        self.remaining = ["load-sample", "generate-cards"]

    async def decide(self, targets: list[ObservedTarget]) -> BrowserDecision:
        if not self.remaining:
            return BrowserDecision(kind="stop", target_id=None)
        target = self.remaining.pop(0)
        if target not in {t.id for t in targets}:
            return BrowserDecision(kind="stop", target_id=None)
        return BrowserDecision(kind="click", target_id=target)


@dataclass
class MockFrame:
    run_id: UUID
    sequence: int
    timestamp: datetime
    png: bytes


@dataclass
class MockRun:
    persona_id: UUID
    task_id: UUID
    product_version_id: UUID
    run_id: UUID = field(default_factory=uuid4)
    mode: str = "fixture"
    counts_as_mandatory_trial: bool = False
    inference_used: bool = False
    status: str = "not_run"
    actions: list[dict] = field(default_factory=list)
    frames: list[MockFrame] = field(default_factory=list)

    def summary(self):
        return {
            "mode": self.mode, "run_id": str(self.run_id), "persona_id": str(self.persona_id),
            "task_id": str(self.task_id), "product_version_id": str(self.product_version_id),
            "counts_as_mandatory_trial": False, "inference_used": False, "status": self.status,
            "actions": self.actions, "captured_frame_count": len(self.frames),
            "frames_retained": "in memory only",
        }


def require_mock_origin(url: str):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.path != "/"
            or parsed.query or parsed.fragment):
        raise ValueError("Mock execution requires the explicit loopback product origin")


async def observed_targets(page) -> list[ObservedTarget]:
    buttons = page.get_by_role("button")
    targets = []
    for index in range(await buttons.count()):
        button = buttons.nth(index)
        if not await button.is_visible() or not await button.is_enabled():
            continue
        target_id = await button.get_attribute("data-target-id")
        if target_id:
            targets.append(ObservedTarget(id=target_id, name=(await button.inner_text())[:160]))
    if len({t.id for t in targets}) != len(targets):
        raise ValueError("Observed target IDs are ambiguous")
    return targets


async def run_mock_trial(browser, handoff: MockHandoff, persona: Persona, task_id: UUID,
                         *, policy: DecisionPolicy | None = None,
                         cancel: asyncio.Event | None = None) -> MockRun:
    task = select_task(handoff, persona, task_id)
    # Revalidate copies: callers cannot bypass gates via model_copy(update=...).
    MockHandoff.model_validate(handoff.model_dump())
    if persona.software_behavior.status != "fixture":
        raise ValueError("Mock worker cannot consume live persona behavior")
    url = handoff.version.runtime_url or ""
    require_mock_origin(url)
    policy = policy or ScriptedMockPolicy()
    result = MockRun(persona.id, task.id, handoff.version.id)
    if cancel is not None and cancel.is_set():
        result.status = "cancelled"
        return result
    context = await browser.new_context(service_workers="block", accept_downloads=False)
    try:
        # Allow exactly the known page. All other requests, redirects and origins are blocked.
        async def restrict(route):
            if route.request.url == url and route.request.method == "GET":
                await route.continue_()
            else:
                await route.abort()

        await context.route("**/*", restrict)
        page = await context.new_page()
        page.set_default_timeout(3000)
        check = next(c for c in handoff.checks if c.id == task.check_id)
        initial_state = next(s for s in handoff.initial_states if s.id == task.initial_state_ref)

        async def capture(kind: str, target: str | None = None):
            timestamp = datetime.now(UTC)
            result.actions.append({
                "sequence": len(result.actions) + 1, "kind": kind, "target": target,
                "timestamp": timestamp.isoformat(), "run_id": str(result.run_id),
                "result": "observed in mock browser; no source integration",
            })
            png = await page.screenshot()
            result.frames.append(MockFrame(result.run_id, len(result.frames) + 1, timestamp, png))

        async with asyncio.timeout(120):
            await page.goto(url, wait_until="domcontentloaded")
            if await page.title() != "RepoFusion mock product":
                result.status = "unexpected_mock_product"
                return result
            await capture("navigate", url)
            # Reserve a final deterministic check; navigate + clicks + check <= task budget.
            for _ in range(task.action_budget - 2):
                if cancel is not None and cancel.is_set():
                    result.status = "cancelled"
                    return result
                if page.url != url:
                    result.status = "blocked_navigation"
                    return result
                if await page.get_by_role("alert").is_visible():
                    result.status = "application_failure"
                    break
                cards = page.locator("#cards article")
                actual = []
                if await page.locator("#cards").is_visible():
                    for index in range(await cards.count()):
                        card = cards.nth(index)
                        actual.append({"question": await card.locator("h2").inner_text(),
                                       "answer": await card.locator("p").inner_text()})
                if actual == [c.model_dump() for c in check.expected_cards]:
                    result.status = "check_success"
                    break
                targets = await observed_targets(page)
                decision = BrowserDecision.model_validate((await policy.decide(targets)).model_dump())
                if cancel is not None and cancel.is_set():
                    result.status = "cancelled"
                    return result
                if decision.kind == "stop":
                    result.status = "policy_stopped"
                    break
                if decision.target_id not in {t.id for t in targets}:
                    result.status = "invalid_target"
                    break
                if (decision.target_id == "generate-cards"
                        and await page.locator("#notes").input_value() != initial_state.notes):
                    result.status = "invalid_initial_state"
                    break
                # IDs are observed values, never interpolated into selectors from model output.
                buttons = page.get_by_role("button")
                clicked = False
                for index in range(await buttons.count()):
                    button = buttons.nth(index)
                    if await button.get_attribute("data-target-id") == decision.target_id:
                        await button.click()
                        clicked = True
                        break
                if not clicked:
                    result.status = "invalid_target"
                    break
                await capture("click", decision.target_id)
            else:
                result.status = "action_limit"
            # Always evaluate independently, including after the last permitted click.
            if result.status == "action_limit" and await page.locator("#cards").is_visible():
                actual = []
                cards = page.locator("#cards article")
                for index in range(await cards.count()):
                    card = cards.nth(index)
                    actual.append({"question": await card.locator("h2").inner_text(),
                                   "answer": await card.locator("p").inner_text()})
                if actual == [c.model_dump() for c in check.expected_cards]:
                    result.status = "check_success"
            await capture("check", check.id)
    except Exception:
        # Browser/provider failures may contain paths or supplied secrets; retain only a safe code.
        result.status = "infrastructure_failure"
    finally:
        await context.close()
    return result
