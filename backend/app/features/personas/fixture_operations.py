"""Bounded local mock mechanics; no inference, durable evidence or mandatory counts."""
from collections import OrderedDict
from threading import Lock
from uuid import UUID

from fastapi import HTTPException

from backend.app.features.personas.mock_handoff import mock_handoff
from backend.app.features.personas.mock_product import serve_mock_product
from backend.app.features.personas.session_execution import (
    CheckResult,
    Decision,
    FeedbackDraft,
    StateReset,
    TrialPlan,
    execute_trial,
)
from backend.app.shared.contracts import Persona, Session, StreamEvent
from backend.app.shared.fixtures import EXPERIMENT


class LatestFixtureSink:
    durable = False

    def __init__(self):
        self.session: Session | None = None
        self.frame: StreamEvent | None = None

    async def save_session(self, session):
        if session.status != "fixture" or session.outcome != "not_run":
            raise ValueError("Fixture cannot store live session")
        self.session = session.model_copy(deep=True)

    async def save_action(self, action):
        if self.session is None or action.session_id != self.session.id:
            raise ValueError("Foreign action")

    async def save_frame(self, event):
        if (self.session is None or event.session_id != self.session.id or event.mode != "fixture"
                or len(event.payload.get("image_base64", "")) > 2796204):
            raise ValueError("Foreign or oversized capture")
        self.frame = event.model_copy(deep=True)


class FixtureStore:
    def __init__(self):
        self.lock = Lock()
        self.busy: set[UUID] = set()
        self.records: OrderedDict[UUID, tuple[Session, StreamEvent | None]] = OrderedDict()

    def reserve(self, persona_id: UUID):
        with self.lock:
            if persona_id in self.busy or len(self.busy) >= 4:
                raise HTTPException(409, detail={"code": "MOCK_TRIAL_BUSY",
                                    "message": "Selected persona or four local workers are busy."})
            self.busy.add(persona_id)

    def release(self, persona_id: UUID):
        with self.lock:
            self.busy.discard(persona_id)

    def save(self, session: Session, frame: StreamEvent | None):
        if session.status != "fixture" or session.outcome != "not_run":
            raise ValueError("Fixture cannot store live session")
        with self.lock:
            self.records[session.id] = (session.model_copy(deep=True),
                                        frame.model_copy(deep=True) if frame else None)
            while len(self.records) > 20:
                self.records.popitem(last=False)

    def get(self, session_id: UUID):
        with self.lock:
            result = self.records.get(session_id)
            return (result[0].model_copy(deep=True), result[1].model_copy(deep=True)
                    if result[1] else None) if result else None

    def latest(self):
        with self.lock:
            latest = {}
            for session, _ in self.records.values():
                latest[session.persona_id] = session.model_copy(deep=True)
            return latest


store = FixtureStore()


class MockPolicy:
    def __init__(self):
        self.next_names = ["Load sample", "Generate cards"]

    async def decide(self, plan, targets, actions):
        name = self.next_names.pop(0) if self.next_names else None
        target = next((item for item in targets if item.name == name and item.action == "click"), None)
        return Decision(kind="click", target_id=target.id) if target else Decision(kind="stop", target_id=None)

    async def feedback(self, plan, session):
        return FeedbackDraft(initial_relevance="medium", post_trial_relevance="medium",
            useful_parts=["Fixed mock workflow"] if session.stop_reason == "success" else [],
            barriers=[] if session.stop_reason == "success" else ["Mock check did not succeed"],
            suggested_changes=[], evidence_action_ids=[action.id for action in session.actions],
            reason="Scripted synthetic feedback from this session's actions; no HF inference.")


async def run_fixture(persona: Persona):
    from playwright.async_api import async_playwright

    sink = LatestFixtureSink()
    with serve_mock_product() as url:
        handoff = mock_handoff([persona], url)
        task = handoff.tasks[0]
        expected = [card.model_dump() for card in handoff.checks[0].expected_cards]

        async def reset(session_id, initial_state_ref, product_version_id):
            # Product has no server state; each fresh context starts with blank notes/hidden cards.
            return StateReset(session_id=session_id, initial_state_ref=initial_state_ref,
                              product_version_id=product_version_id)

        async def check(page, session_id, check_id):
            if check_id != task.check_id:
                raise ValueError("Unknown fixed check")
            if await page.get_by_role("alert").is_visible():
                return CheckResult(outcome="application_failure", code="MOCK_APPLICATION_FAILURE")
            actual = []
            if await page.locator("#cards").is_visible():
                cards = page.locator("#cards article")
                for index in range(await cards.count()):
                    card = cards.nth(index)
                    actual.append({"question": await card.locator("h2").inner_text(),
                                   "answer": await card.locator("p").inner_text()})
            return CheckResult(outcome="success" if actual == expected else "continue",
                               code="MOCK_FIXED_CARDS_CHECK")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                result = await execute_trial(browser, TrialPlan(mode="fixture", product=handoff.version,
                    task=task, persona=persona, experiment_id=EXPERIMENT.id),
                    policy=MockPolicy(), sink=sink, reset_state=reset, check=check)
            finally:
                await browser.close()
    store.save(result.session, sink.frame)
    return result.session
