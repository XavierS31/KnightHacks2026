"""Bounded session executor; real products require A validation and C durable evidence."""
import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from backend.app.shared.contracts import (
    Action,
    Contract,
    Feedback,
    Persona,
    ProductVersion,
    Session,
    StreamEvent,
    Task,
)
from backend.app.shared.inference import InferenceError


class TrialGateError(Exception):
    pass


class _TrialCancelled(Exception):
    """Internal event cancellation; external task cancellation still propagates."""


class TrialPlan(Contract):
    mode: Literal["fixture", "live"]
    product: ProductVersion
    task: Task
    persona: Persona
    experiment_id: UUID

    @model_validator(mode="after")
    def valid_handoff(self):
        if self.task.scenario_id != self.persona.scenario.id:
            raise ValueError("Task must belong to persona scenario")
        if not 2 <= self.task.action_budget <= 6:
            raise ValueError("Mandatory session reserves navigation/check within six actions")
        if not self.task.capability_ids or not set(self.task.capability_ids) <= {
                c.id for c in self.product.capabilities}:
            raise ValueError("Unsupported task capability")
        url = urlsplit(self.product.runtime_url or "")
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError("Explicit credential-free product URL required")
        if self.mode == "fixture":
            if self.product.status != "fixture" or self.persona.software_behavior.status != "fixture":
                raise ValueError("Fixture executor cannot promote live product/persona state")
            if url.hostname != "127.0.0.1" or url.scheme != "http":
                raise ValueError("Fixture browser is loopback only")
        elif (self.product.status not in {"validated", "approved"} or not self.product.commit_sha
                or self.persona.software_behavior.status != "review_informed"
                or any(not c.validated for c in self.product.capabilities
                       if c.id in self.task.capability_ids)):
            raise ValueError("Live trial needs A validated product and approved review behavior")
        return self


class StateReset(Contract):
    session_id: UUID
    product_version_id: UUID
    initial_state_ref: str


class CheckResult(Contract):
    outcome: Literal["continue", "success", "application_failure"]
    code: str = Field(min_length=1, max_length=100)


class Target(Contract):
    id: str
    name: str
    action: Literal["click", "type", "select"]


class Decision(Contract):
    kind: Literal["click", "type", "select", "stop"]
    target_id: str | None
    value: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def action_arguments(self):
        if (self.kind == "stop") != (self.target_id is None):
            raise ValueError("Only stop can omit a target")
        if (self.kind in {"type", "select"}) != (self.value is not None):
            raise ValueError("Only type/select require a bounded value")
        return self


class FeedbackDraft(Contract):
    initial_relevance: Literal["low", "medium", "high"]
    post_trial_relevance: Literal["low", "medium", "high"]
    useful_parts: list[str] = Field(max_length=10)
    barriers: list[str] = Field(max_length=10)
    suggested_changes: list[str] = Field(max_length=10)
    evidence_action_ids: list[UUID] = Field(max_length=6)
    reason: str = Field(min_length=1, max_length=1500)


def validate_feedback(feedback: Feedback, session: Session) -> Feedback:
    feedback = Feedback.model_validate(feedback.model_dump())
    if feedback.persona_id != session.persona_id or feedback.session_id != session.id:
        raise TrialGateError("FEEDBACK_SESSION_MISMATCH")
    if (len(set(feedback.evidence_action_ids)) != len(feedback.evidence_action_ids)
            or not set(feedback.evidence_action_ids) <= {a.id for a in session.actions}):
        raise TrialGateError("FEEDBACK_ACTION_MISMATCH")
    if any(a.session_id != session.id for a in session.actions):
        raise TrialGateError("ACTION_SESSION_MISMATCH")
    if (feedback.useful_parts or feedback.barriers or feedback.suggested_changes) and not feedback.evidence_action_ids:
        raise TrialGateError("FEEDBACK_EVIDENCE_REQUIRED")
    return feedback


def frame_event(session: Session, png: bytes, *, sequence: int, frame_sequence: int,
                  timestamp: datetime) -> StreamEvent:
    if (not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) < 33
            or png[8:16] != b"\x00\x00\x00\x0dIHDR"
            or not 0 < int.from_bytes(png[16:20], "big") <= 4096
            or not 0 < int.from_bytes(png[20:24], "big") <= 4096
            or len(png) > 2 * 1024 * 1024 or session.stream_mode == "unavailable"
            or sequence < 0 or frame_sequence < 1 or timestamp.tzinfo is None):
        raise TrialGateError("INVALID_CAPTURED_FRAME")
    return StreamEvent(
        session_id=session.id, sequence=sequence, timestamp=timestamp,
        type="frame", mode=session.stream_mode,
        payload={"session_id": str(session.id), "frame_sequence": frame_sequence,
                 "captured_at": timestamp.isoformat(), "mime_type": "image/png",
                 "image_base64": base64.b64encode(png).decode()},
    )


class EvidenceSink(Protocol):
    durable: bool

    async def save_session(self, session: Session): ...
    async def save_action(self, action: Action): ...
    async def save_frame(self, event: StreamEvent) -> str | None: ...


class FixtureEvidenceSink:
    """No durable persistence, no live records, no completed experiment counts."""
    durable = False

    def __init__(self):
        self.sessions: dict[UUID, Session] = {}
        self.actions: list[Action] = []
        self.frames: list[StreamEvent] = []

    async def save_session(self, session):
        if session.status != "fixture" or session.outcome != "not_run":
            raise TrialGateError("FIXTURE_SINK_CANNOT_SAVE_LIVE_SESSION")
        self.sessions[session.id] = session.model_copy(deep=True)

    async def save_action(self, action):
        if action.session_id not in self.sessions:
            raise TrialGateError("ACTION_SESSION_NOT_SAVED")
        self.actions.append(action.model_copy(deep=True))

    async def save_frame(self, event):
        if event.mode != "fixture" or event.session_id not in self.sessions:
            raise TrialGateError("FIXTURE_SINK_CANNOT_SAVE_LIVE_FRAME")
        self.frames.append(event.model_copy(deep=True))


class ActionPolicy(Protocol):
    async def decide(self, plan: TrialPlan, targets: list[Target], actions: list[Action]) -> Decision: ...
    async def feedback(self, plan: TrialPlan, session: Session) -> FeedbackDraft: ...


@dataclass
class TrialExecution:
    session: Session
    check_outcome: str
    counts_as_mandatory_trial: bool


async def _target_fingerprint(element):
    # Trusted deterministic inspection, never JavaScript supplied by the model.
    return await element.evaluate("""element => ({
        connected: element.isConnected, tag: element.tagName,
        attributes: ['type', 'id', 'name', 'aria-label', 'placeholder', 'href',
                     'formaction', 'readonly'].map(name => element.getAttribute(name)),
        text: (element.textContent || '').slice(0, 160)
    })""")


async def _observe(page):
    targets, locators = [], {}
    for selector, kind in (("button, input[type=submit], a[href]", "click"),
                           ("input:not([type]), input[type=text], input[type=search], textarea", "type"),
                           ("select", "select")):
        elements = page.locator(selector)
        for index in range(min(await elements.count(), 50)):
            # A Locator resolves afresh after inference; pin this actual DOM element.
            element = await elements.nth(index).element_handle()
            if element is None:
                continue
            fingerprint = await _target_fingerprint(element)
            if (not fingerprint["connected"] or not await element.is_visible() or not await element.is_enabled()
                    or (kind == "type" and await element.get_attribute("readonly") is not None)):
                continue
            name = (await element.get_attribute("aria-label") or await element.inner_text()
                    or await element.get_attribute("placeholder") or f"Visible {kind} control")[:160]
            target_id = f"target-{len(targets)}"
            targets.append(Target(id=target_id, name=name, action=kind))
            locators[target_id] = (element, fingerprint)
    return targets, locators


async def execute_trial(browser, plan: TrialPlan, *, policy: ActionPolicy, sink: EvidenceSink,
                         reset_state, check, cancel: asyncio.Event | None = None) -> TrialExecution:
    """C supplies a durable sink; A supplies state reset/fixed check, never the runtime model."""
    plan = TrialPlan.model_validate(plan.model_dump())
    if plan.mode == "live" and not sink.durable:
        raise TrialGateError("DURABLE_EVIDENCE_REQUIRED")
    session = Session(id=uuid4(), experiment_id=plan.experiment_id, persona_id=plan.persona.id,
                      product_version_id=plan.product.id, status="fixture" if plan.mode == "fixture"
                      else "running", outcome="not_run", actions=[], stream_mode=plan.mode)
    await sink.save_session(session)
    if cancel is not None and cancel.is_set():
        session.stop_reason = "cancelled_before_trial"
        if plan.mode == "live":
            session.status = "cancelled"
        await sink.save_session(session)
        return TrialExecution(session, "cancelled", False)
    context = None
    result = "infrastructure_failure"

    def check_cancelled():
        if cancel is not None and cancel.is_set():
            raise _TrialCancelled()

    try:
        async with asyncio.timeout(120):
            check_cancelled()
            reset = StateReset.model_validate((await reset_state(session.id, plan.task.initial_state_ref,
                                                 plan.product.id)).model_dump())
            check_cancelled()
            if reset != StateReset(session_id=session.id, initial_state_ref=plan.task.initial_state_ref,
                                   product_version_id=plan.product.id):
                raise TrialGateError("STATE_RESET_SCOPE_MISMATCH")
            context = await browser.new_context(service_workers="block", accept_downloads=False)
            check_cancelled()
            url = plan.product.runtime_url
            origin = urlsplit(url)

            async def restrict(route):
                request_url = urlsplit(route.request.url)
                if (request_url.scheme, request_url.netloc) != (origin.scheme, origin.netloc):
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", restrict)
            page = await context.new_page()
            page.set_default_timeout(3000)
            check_cancelled()

            async def record(kind, target, code):
                action = Action(id=uuid4(), session_id=session.id, sequence=len(session.actions) + 1,
                                timestamp=datetime.now(UTC), kind=kind, target=target, result=code)
                capture_failed = False
                try:
                    png = await page.screenshot()
                    action.artifact_ref = await sink.save_frame(frame_event(
                        session, png, sequence=2 * action.sequence,
                        frame_sequence=action.sequence, timestamp=datetime.now(UTC)))
                except Exception:
                    # The observed action still happened. Keep it in the durable record
                    # and surface the missing frame as an infrastructure failure.
                    capture_failed = True
                await sink.save_action(action)
                session.actions.append(action)
                await sink.save_session(session)
                if capture_failed:
                    raise TrialGateError("CAPTURED_FRAME_UNAVAILABLE")

            await page.goto(url, wait_until="domcontentloaded")
            await record("navigate", url, "product_page_loaded")
            check_cancelled()
            for _ in range(plan.task.action_budget - 2):
                if cancel is not None and cancel.is_set():
                    result = "cancelled"
                    break
                outcome = CheckResult.model_validate((await check(page, session.id,
                                                       plan.task.check_id)).model_dump())
                check_cancelled()
                if outcome.outcome != "continue":
                    result = outcome.outcome
                    break
                current = urlsplit(page.url)
                if (current.scheme, current.netloc) != (origin.scheme, origin.netloc):
                    raise TrialGateError("DISALLOWED_NAVIGATION")
                targets, locators = await _observe(page)
                check_cancelled()
                decision = Decision.model_validate((await policy.decide(plan, targets,
                                                       list(session.actions))).model_dump())
                if cancel is not None and cancel.is_set():
                    result = "cancelled"
                    break
                if decision.kind == "stop":
                    result = "policy_stopped"
                    break
                target = next((t for t in targets if t.id == decision.target_id), None)
                if target is None or target.action != decision.kind:
                    raise TrialGateError("UNOBSERVED_ACTION_TARGET")
                element, fingerprint = locators[target.id]
                try:
                    unchanged = (await _target_fingerprint(element) == fingerprint
                                 and await element.is_visible() and await element.is_enabled())
                except Exception:
                    unchanged = False
                if not unchanged:
                    raise TrialGateError("STALE_ACTION_TARGET")
                href = await element.get_attribute("href")
                if href:
                    from urllib.parse import urljoin
                    destination = urlsplit(urljoin(page.url, href))
                    if (destination.scheme, destination.netloc) != (origin.scheme, origin.netloc):
                        raise TrialGateError("DISALLOWED_NAVIGATION")
                check_cancelled()
                if decision.kind == "click":
                    await element.click()
                elif decision.kind == "type":
                    await element.fill(decision.value)
                else:
                    await element.select_option(value=decision.value)
                await record(decision.kind, target.id, "action_executed")
                check_cancelled()
            else:
                result = "action_limit"
            if result != "cancelled":
                check_cancelled()
                final = CheckResult.model_validate((await check(page, session.id,
                                                       plan.task.check_id)).model_dump())
                check_cancelled()
                if final.outcome != "continue":
                    result = final.outcome
                await record("check", plan.task.check_id, f"deterministic_{result}")
                check_cancelled()
            if result == "cancelled":
                raise _TrialCancelled()
            if plan.mode == "live":
                session.outcome = result if result in {"success", "application_failure"} else "infrastructure_failure"
                session.status = "completed" if result in {"success", "application_failure"} else "failed"
                if result == "cancelled":
                    session.status = "cancelled"
            session.stop_reason = result
            if result != "cancelled":
                check_cancelled()
                draft = FeedbackDraft.model_validate((await policy.feedback(plan, session)).model_dump())
                check_cancelled()
                feedback = Feedback(id=uuid4(), persona_id=session.persona_id, session_id=session.id,
                    decision="stop", **draft.model_dump())
                if plan.mode == "fixture":
                    feedback.reason = "Mock product only: " + feedback.reason
                session.feedback = validate_feedback(feedback, session)
            check_cancelled()
            await sink.save_session(session)
            check_cancelled()
    except _TrialCancelled:
        result = "cancelled"
        session.stop_reason, session.feedback = "cancelled", None
        if plan.mode == "live":
            session.status, session.outcome = "cancelled", "not_run"
        await sink.save_session(session)
    except asyncio.CancelledError:
        session.stop_reason, session.feedback = "cancelled", None
        if plan.mode == "live":
            session.status, session.outcome = "cancelled", "not_run"
        await sink.save_session(session)
        raise
    except Exception as failure:
        result = failure.code if isinstance(failure, InferenceError) else (
            str(failure) if isinstance(failure, TrialGateError) else "SESSION_EXECUTION_FAILED")
        session.stop_reason = result
        if plan.mode == "live":
            session.status, session.outcome = "failed", "infrastructure_failure"
        await sink.save_session(session)
    finally:
        if context is not None:
            try:
                await context.close()
            except asyncio.CancelledError:
                session.stop_reason, session.feedback = "cancelled", None
                if plan.mode == "live":
                    session.status, session.outcome = "cancelled", "not_run"
                await sink.save_session(session)
                raise
    if cancel is not None and cancel.is_set():
        result = "cancelled"
        session.stop_reason, session.feedback = "cancelled", None
        if plan.mode == "live":
            session.status, session.outcome = "cancelled", "not_run"
        await sink.save_session(session)
    return TrialExecution(session, result, plan.mode == "live" and bool(session.actions)
                          and session.feedback is not None and session.status == "completed")
