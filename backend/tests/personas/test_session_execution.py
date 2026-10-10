"""Bounded executor gates and opt-in real Chromium mechanics against a fake product."""
import asyncio
import base64
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from playwright.async_api import async_playwright
from pydantic import ValidationError

from backend.app.features.personas.mock_handoff import mock_handoff, mock_population
from backend.app.features.personas.mock_product import serve_mock_product
from backend.app.features.personas.session_execution import (
    CheckResult,
    Decision,
    FeedbackDraft,
    FixtureEvidenceSink,
    StateReset,
    TrialGateError,
    TrialPlan,
    execute_trial,
    frame_event,
    validate_feedback,
)
from backend.app.shared.contracts import Action, Feedback, Session

BROWSER = pytest.mark.skipif(os.environ.get("B_BROWSER_TESTS") != "1",
                             reason="Set B_BROWSER_TESTS=1 for loopback Chromium tests")
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
       + (1).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"test")


def plan(url="http://127.0.0.1:12345/"):
    population = mock_population(1)
    handoff = mock_handoff(population, url)
    return TrialPlan(mode="fixture", product=handoff.version, task=handoff.tasks[0],
                     persona=population[0], experiment_id=uuid4())


def session_record():
    trial = plan()
    session = Session(id=uuid4(), experiment_id=trial.experiment_id, persona_id=trial.persona.id,
                      product_version_id=trial.product.id, status="fixture", outcome="not_run",
                      actions=[], stream_mode="fixture")
    session.actions.append(Action(id=uuid4(), session_id=session.id, sequence=1,
                                  timestamp=datetime.now(UTC), kind="navigate", target="fixture",
                                  result="fixture_page_loaded"))
    return session


def feedback_record(session):
    return Feedback(id=uuid4(), persona_id=session.persona_id, session_id=session.id,
                    initial_relevance="low", post_trial_relevance="medium", decision="stop",
                    useful_parts=["Test mock navigation"], barriers=[], suggested_changes=[],
                    evidence_action_ids=[session.actions[0].id], reason="Mock feedback only")


@pytest.mark.parametrize("field", ["persona_id", "session_id"])
def test_feedback_rejects_cross_session_and_persona_identity(field):
    session = session_record()
    feedback = feedback_record(session)
    setattr(feedback, field, uuid4())
    with pytest.raises(TrialGateError, match="FEEDBACK_SESSION_MISMATCH"):
        validate_feedback(feedback, session)


@pytest.mark.parametrize("refs", ["unknown", "duplicate"])
def test_feedback_rejects_invented_and_duplicate_action_evidence(refs):
    session = session_record()
    feedback = feedback_record(session)
    feedback.evidence_action_ids = ([uuid4()] if refs == "unknown"
                                    else [session.actions[0].id] * 2)
    with pytest.raises(TrialGateError, match="FEEDBACK_ACTION_MISMATCH"):
        validate_feedback(feedback, session)


def test_feedback_rejects_action_owned_by_other_session():
    session = session_record()
    feedback = feedback_record(session)
    session.actions[0].session_id = uuid4()
    with pytest.raises(TrialGateError, match="ACTION_SESSION_MISMATCH"):
        validate_feedback(feedback, session)


def test_feedback_remains_synthetic_and_exact_session_scoped():
    session = session_record()
    feedback = validate_feedback(feedback_record(session), session)
    assert feedback.synthetic is True
    assert feedback.evidence_action_ids == [session.actions[0].id]


@pytest.mark.parametrize("claim", ["useful_parts", "barriers", "suggested_changes"])
def test_product_claims_cannot_use_external_reviews_without_action_evidence(claim):
    session = session_record()
    feedback = feedback_record(session)
    feedback.useful_parts, feedback.barriers, feedback.suggested_changes = [], [], []
    setattr(feedback, claim, ["Test claim about product"])
    feedback.evidence_action_ids = []
    with pytest.raises(TrialGateError, match="FEEDBACK_EVIDENCE_REQUIRED"):
        validate_feedback(feedback, session)


def test_frame_encoding_preserves_exact_session_capture_time_and_sequence():
    session = session_record()
    timestamp = datetime.now(UTC)
    frame = frame_event(session, PNG, sequence=2, frame_sequence=1, timestamp=timestamp)
    assert frame.session_id == session.id and frame.mode == "fixture"
    assert frame.payload["session_id"] == str(session.id)
    assert frame.payload["captured_at"] == timestamp.isoformat()
    assert base64.b64decode(frame.payload["image_base64"]) == PNG
    assert frame.payload["frame_sequence"] == 1


@pytest.mark.parametrize("data,index,timestamp", [
    (b"html", 1, datetime.now(UTC)), (PNG, 0, datetime.now(UTC)),
    (PNG, 1, datetime(2026, 10, 10)), (PNG + b"0" * (2 * 1024 * 1024), 1, datetime.now(UTC)),
], ids=["not-png", "invalid-sequence", "naive-timestamp", "oversized"])
def test_frame_rejects_invalid_format_size_sequence_and_naive_timestamp(data, index, timestamp):
    with pytest.raises(TrialGateError, match="INVALID_CAPTURED_FRAME"):
        frame_event(session_record(), data, sequence=1, frame_sequence=index, timestamp=timestamp)


@pytest.mark.parametrize("case", ["zero-width", "huge-height", "bad-ihdr", "truncated",
                                  "unavailable", "negative-sequence"])
def test_frame_rejects_malformed_header_dimensions_and_missing_stream(case):
    session, png, sequence = session_record(), PNG, 0
    if case == "zero-width":
        png = PNG[:16] + bytes(4) + PNG[20:]
    elif case == "huge-height":
        png = PNG[:20] + (4097).to_bytes(4, "big") + PNG[24:]
    elif case == "bad-ihdr":
        png = PNG[:12] + b"FAIL" + PNG[16:]
    elif case == "truncated":
        png = PNG[:32]
    elif case == "unavailable":
        session.stream_mode = "unavailable"
    else:
        sequence = -1
    with pytest.raises(TrialGateError, match="INVALID_CAPTURED_FRAME"):
        frame_event(session, png, sequence=sequence, frame_sequence=1, timestamp=datetime.now(UTC))


@pytest.mark.parametrize("change", ["foreign_scenario", "foreign_capability", "external_fixture",
                                     "credential_url", "query_url", "action_budget"])
def test_invalid_handoff_is_rejected_before_execution(change):
    data = plan().model_dump()
    if change == "foreign_scenario":
        data["task"]["scenario_id"] = uuid4()
    elif change == "foreign_capability":
        data["task"]["capability_ids"] = [uuid4()]
    elif change == "external_fixture":
        data["product"]["runtime_url"] = "https://example.com/"
    elif change == "credential_url":
        data["product"]["runtime_url"] = "http://user:password@127.0.0.1/"
    elif change == "query_url":
        data["product"]["runtime_url"] = "http://127.0.0.1/?token=test"
    else:
        data["task"]["action_budget"] = 8
    with pytest.raises(ValidationError):
        TrialPlan.model_validate(data)


class NoBrowser:
    calls = 0

    async def new_context(self, **kwargs):
        self.calls += 1
        raise AssertionError("Browser creation should be gated")


async def reset(session_id, initial_state_ref, product_version_id):
    return StateReset(session_id=session_id, initial_state_ref=initial_state_ref,
                      product_version_id=product_version_id)


async def fixed_check(page, session_id, check_id):
    assert session_id and check_id == "b-mock-two-cards-v1"
    if await page.locator("#error").is_visible():
        return CheckResult(outcome="application_failure", code="mock_application_failure")
    if await page.locator("#cards").is_visible():
        assert await page.locator("#cards article").count() == 2
        assert await page.locator("#cards article p").all_text_contents() == ["Sunlight", "0 C"]
        return CheckResult(outcome="success", code="expected_cards_verified")
    return CheckResult(outcome="continue", code="not_complete")


class MockPolicy:
    def __init__(self, *, invalid=False, repeat=False, cancel=None, bad_feedback=False):
        self.invalid, self.repeat = invalid, repeat
        self.cancel, self.bad_feedback = cancel, bad_feedback
        self.decisions = 0

    async def decide(self, trial, targets, actions):
        self.decisions += 1
        if self.cancel:
            self.cancel.set()
        if self.invalid:
            return Decision(kind="click", target_id="invented-target")
        name = "Load sample" if self.decisions == 1 or self.repeat else "Generate cards"
        target = next(target for target in targets if target.name == name)
        return Decision(kind="click", target_id=target.id)

    async def feedback(self, trial, session):
        return FeedbackDraft(initial_relevance="low", post_trial_relevance="medium",
                             useful_parts=["Mock cards"], barriers=[], suggested_changes=[],
                             evidence_action_ids=([uuid4()] if self.bad_feedback
                                                  else [session.actions[-1].id]),
                             reason="Fixture-only synthetic opinion")


async def test_pre_cancel_has_no_browser_reset_actions_or_frames():
    browser = NoBrowser()
    sink = FixtureEvidenceSink()
    cancel = asyncio.Event()
    cancel.set()

    async def forbidden_reset(*args):
        raise AssertionError("No state reset after cancellation")

    result = await execute_trial(browser, plan(), policy=MockPolicy(), sink=sink,
                                 reset_state=forbidden_reset, check=fixed_check, cancel=cancel)
    assert result.check_outcome == "cancelled"
    assert result.session.status == "fixture" and result.session.outcome == "not_run"
    assert result.session.actions == sink.frames == []
    assert not result.counts_as_mandatory_trial and browser.calls == 0


async def test_state_reset_identity_mismatch_blocks_browser_and_surfaces_failure():
    browser = NoBrowser()
    sink = FixtureEvidenceSink()

    async def wrong_reset(session_id, initial_state_ref, product_version_id):
        return StateReset(session_id=uuid4(), initial_state_ref=initial_state_ref,
                          product_version_id=product_version_id)

    result = await execute_trial(browser, plan(), policy=MockPolicy(), sink=sink,
                                 reset_state=wrong_reset, check=fixed_check)
    assert result.check_outcome == "STATE_RESET_SCOPE_MISMATCH"
    assert result.session.stop_reason == result.check_outcome
    assert not result.counts_as_mandatory_trial and browser.calls == 0


def live_test_plan(url="http://127.0.0.1:12345/"):
    # Invented source-shaped test data strictly to reach the persistence gate.
    data = plan(url).model_dump()
    data["mode"] = "live"
    data["product"].update(status="validated", commit_sha="a" * 40)
    for capability in data["product"]["capabilities"]:
        capability["validated"] = True
    profile = data["persona"]["software_behavior"]
    profile["status"] = "review_informed"
    for evidence in profile["evidence"]:
        evidence.update(kind="source", platform="other", external_id="test-only-review",
                        source_url="https://example.com/test-only", report_type="opinion",
                        collection_method="manual", content_sha256="b" * 64)
    return TrialPlan.model_validate(data)


async def test_live_trial_requires_durable_sink_before_creating_browser():
    browser = NoBrowser()
    with pytest.raises(TrialGateError, match="DURABLE_EVIDENCE_REQUIRED"):
        await execute_trial(browser, live_test_plan(), policy=MockPolicy(),
                            sink=FixtureEvidenceSink(), reset_state=reset, check=fixed_check)
    assert browser.calls == 0


async def test_fixture_sink_cannot_accept_live_completed_records_or_unsaved_evidence():
    sink = FixtureEvidenceSink()
    session = session_record()
    with pytest.raises(TrialGateError, match="ACTION_SESSION_NOT_SAVED"):
        await sink.save_action(session.actions[0])
    session.status = "completed"
    session.outcome = "success"
    with pytest.raises(TrialGateError, match="FIXTURE_SINK_CANNOT_SAVE_LIVE_SESSION"):
        await sink.save_session(session)


@pytest.fixture
async def browser():
    async with async_playwright() as playwright:
        instance = await playwright.chromium.launch()
        yield instance
        await instance.close()


@BROWSER
async def test_actual_mock_actions_frames_and_low_relevance_do_not_count_as_live(browser):
    sink = FixtureEvidenceSink()
    resets = []

    async def scoped_reset(*args):
        resets.append(args)
        return await reset(*args)

    with serve_mock_product() as url:
        trial = plan(url)
        result = await execute_trial(browser, trial, policy=MockPolicy(), sink=sink,
                                     reset_state=scoped_reset, check=fixed_check)
    assert result.check_outcome == "success"
    assert result.session.feedback.initial_relevance == "low"
    assert result.session.status == "fixture" and result.session.outcome == "not_run"
    assert [a.kind for a in result.session.actions] == ["navigate", "click", "click", "check"]
    assert resets == [(result.session.id, trial.task.initial_state_ref, trial.product.id)]
    assert result.session.feedback.synthetic and "Mock product only" in result.session.feedback.reason
    assert len(sink.frames) == 4 and not result.counts_as_mandatory_trial
    for frame in sink.frames:
        assert frame.session_id == result.session.id
        assert base64.b64decode(frame.payload["image_base64"]).startswith(b"\x89PNG")
    assert browser.contexts == []


@BROWSER
async def test_external_task_cancellation_saves_terminal_state_and_closes_context(browser):
    class FakeDurableSink:
        # Test-only: never a real durable persistence implementation.
        durable = True

        def __init__(self):
            self.sessions = []

        async def save_session(self, session):
            self.sessions.append(session.model_copy(deep=True))

        async def save_action(self, action):
            pass

        async def save_frame(self, event):
            pass

    entered = asyncio.Event()

    class BlockingPolicy(MockPolicy):
        async def decide(self, trial, targets, actions):
            entered.set()
            await asyncio.Event().wait()

    sink = FakeDurableSink()
    with serve_mock_product() as url:
        task = asyncio.create_task(execute_trial(browser, live_test_plan(url),
                                   policy=BlockingPolicy(), sink=sink, reset_state=reset,
                                   check=fixed_check))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert sink.sessions[-1].status == "cancelled"
    assert sink.sessions[-1].outcome == "not_run"
    assert "cancel" in sink.sessions[-1].stop_reason
    assert sink.sessions[-1].feedback is None
    assert browser.contexts == []


@BROWSER
@pytest.mark.parametrize("failure,expected", [("application", "application_failure"),
                                               ("timeout", "action_limit")])
async def test_mock_application_failure_and_action_exhaustion_remain_visible(browser, failure, expected):
    with serve_mock_product(failure) as url:
        policy = MockPolicy(repeat=failure == "timeout")
        result = await execute_trial(browser, plan(url), policy=policy, sink=FixtureEvidenceSink(),
                                     reset_state=reset, check=fixed_check)
    assert result.check_outcome == result.session.stop_reason == expected
    assert len(result.session.actions) <= 6
    assert not result.counts_as_mandatory_trial and result.session.outcome == "not_run"
    assert browser.contexts == []


@BROWSER
async def test_bad_target_and_feedback_evidence_fail_honestly_and_close_context(browser):
    with serve_mock_product() as url:
        bad_target = await execute_trial(browser, plan(url), policy=MockPolicy(invalid=True),
                                        sink=FixtureEvidenceSink(), reset_state=reset, check=fixed_check)
        bad_feedback = await execute_trial(browser, plan(url), policy=MockPolicy(bad_feedback=True),
                                          sink=FixtureEvidenceSink(), reset_state=reset, check=fixed_check)
    assert bad_target.check_outcome == "UNOBSERVED_ACTION_TARGET"
    assert not any(action.kind == "click" for action in bad_target.session.actions)
    assert bad_feedback.check_outcome == "FEEDBACK_ACTION_MISMATCH"
    assert bad_feedback.session.feedback is None
    assert not bad_feedback.counts_as_mandatory_trial
    assert browser.contexts == []


@BROWSER
async def test_mid_trial_cancellation_stops_before_proposed_click(browser):
    cancel = asyncio.Event()
    with serve_mock_product() as url:
        result = await execute_trial(browser, plan(url), policy=MockPolicy(cancel=cancel),
                                     sink=FixtureEvidenceSink(), reset_state=reset,
                                     check=fixed_check, cancel=cancel)
    assert result.check_outcome == "cancelled"
    assert [action.kind for action in result.session.actions] == ["navigate"]
    assert result.session.feedback is None and not result.counts_as_mandatory_trial
    assert browser.contexts == []


@BROWSER
async def test_parallel_trials_preserve_session_and_frame_identity_and_clean_contexts(browser):
    sink = FixtureEvidenceSink()
    with serve_mock_product() as url:
        trial = plan(url)
        results = await asyncio.gather(*[
            execute_trial(browser, trial, policy=MockPolicy(), sink=sink, reset_state=reset,
                          check=fixed_check) for _ in range(2)
        ])
    assert len({result.session.id for result in results}) == 2
    for result in results:
        assert result.check_outcome == "success"
        assert len([frame for frame in sink.frames if frame.session_id == result.session.id]) == 4
        assert all(action.session_id == result.session.id for action in result.session.actions)
    assert browser.contexts == []


@BROWSER
async def test_dom_reorder_during_policy_cannot_redirect_observed_button(browser):
    wrong_clicks = []

    class ReorderPolicy(MockPolicy):
        async def decide(self, trial, targets, actions):
            if self.decisions == 0:
                page = browser.contexts[0].pages[0]
                await page.evaluate("""() => {
                    window.wrongClick = false;
                    const extra = document.createElement('button');
                    extra.textContent = 'Unobserved new button';
                    extra.onclick = () => { window.wrongClick = true; };
                    document.body.prepend(extra);
                }""")
            return await super().decide(trial, targets, actions)

    async def checked(page, *args):
        wrong_clicks.append(await page.evaluate("Boolean(window.wrongClick)"))
        return await fixed_check(page, *args)

    with serve_mock_product() as url:
        result = await execute_trial(browser, plan(url), policy=ReorderPolicy(),
                                     sink=FixtureEvidenceSink(), reset_state=reset, check=checked)
    assert result.check_outcome in {"success", "STALE_ACTION_TARGET"}
    assert wrong_clicks and not any(wrong_clicks)
    assert not result.counts_as_mandatory_trial
    assert browser.contexts == []


@BROWSER
@pytest.mark.parametrize("mutation", ["replaced", "renamed"])
async def test_replaced_or_mutated_observed_control_is_rejected(browser, mutation):
    class MutatePolicy(MockPolicy):
        async def decide(self, trial, targets, actions):
            page = browser.contexts[0].pages[0]
            await page.evaluate("""mode => {
                const original = document.querySelector('[data-target-id="load-sample"]');
                if (mode === 'replaced') {
                    const replacement = original.cloneNode(true);
                    original.replaceWith(replacement);
                } else {
                    original.textContent = 'Unexpected changed behavior';
                }
            }""", mutation)
            return await super().decide(trial, targets, actions)

    with serve_mock_product() as url:
        result = await execute_trial(browser, plan(url), policy=MutatePolicy(),
                                     sink=FixtureEvidenceSink(), reset_state=reset, check=fixed_check)
    assert result.check_outcome == "STALE_ACTION_TARGET"
    assert [action.kind for action in result.session.actions] == ["navigate"]
    assert not result.counts_as_mandatory_trial and browser.contexts == []


class TestOnlyLiveSink:
    """Fake durable flag allows testing terminal state; never production persistence."""
    __test__ = False
    durable = True

    def __init__(self):
        self.sessions = []
        self.actions = []
        self.frames = []

    async def save_session(self, session):
        self.sessions.append(session.model_copy(deep=True))

    async def save_action(self, action):
        self.actions.append(action.model_copy(deep=True))

    async def save_frame(self, event):
        self.frames.append(event.model_copy(deep=True))


@BROWSER
async def test_cancellation_during_state_reset_prevents_context_and_navigation(browser):
    cancel = asyncio.Event()
    sink = TestOnlyLiveSink()

    async def cancel_reset(*args):
        cancel.set()
        return await reset(*args)

    with serve_mock_product() as url:
        result = await execute_trial(browser, live_test_plan(url), policy=MockPolicy(), sink=sink,
                                     reset_state=cancel_reset, check=fixed_check, cancel=cancel)
    assert result.check_outcome == "cancelled"
    assert result.session.actions == sink.frames == []
    assert result.session.status == "cancelled" and result.session.outcome == "not_run"
    assert result.session.feedback is None and not result.counts_as_mandatory_trial
    assert browser.contexts == []


@BROWSER
async def test_cancellation_during_final_check_prevents_feedback_request(browser):
    cancel = asyncio.Event()
    feedback_calls = []
    checks = 0
    sink = TestOnlyLiveSink()

    async def cancel_final_check(page, *args):
        nonlocal checks
        checks += 1
        outcome = await fixed_check(page, *args)
        if checks == 4:
            cancel.set()
        return outcome

    class CountFeedbackPolicy(MockPolicy):
        async def feedback(self, *args):
            feedback_calls.append(True)
            return await super().feedback(*args)

    with serve_mock_product() as url:
        result = await execute_trial(browser, live_test_plan(url), policy=CountFeedbackPolicy(),
                                     sink=sink, reset_state=reset, check=cancel_final_check, cancel=cancel)
    assert checks == 4 and feedback_calls == []
    assert result.check_outcome == "cancelled"
    assert result.session.status == "cancelled" and result.session.outcome == "not_run"
    assert [action.kind for action in result.session.actions] == ["navigate", "click", "click"]
    assert not result.counts_as_mandatory_trial and browser.contexts == []


@BROWSER
async def test_cancellation_during_feedback_retains_actions_but_discards_feedback(browser):
    cancel = asyncio.Event()
    sink = TestOnlyLiveSink()

    class CancelFeedbackPolicy(MockPolicy):
        async def feedback(self, *args):
            cancel.set()
            return await super().feedback(*args)

    with serve_mock_product() as url:
        result = await execute_trial(browser, live_test_plan(url), policy=CancelFeedbackPolicy(),
                                     sink=sink, reset_state=reset, check=fixed_check, cancel=cancel)
    assert result.check_outcome == "cancelled"
    assert result.session.status == "cancelled" and result.session.outcome == "not_run"
    assert [action.kind for action in result.session.actions] == ["navigate", "click", "click", "check"]
    assert len(sink.actions) == len(sink.frames) == 4
    assert sink.sessions[-1].feedback is None and result.session.feedback is None
    assert not result.counts_as_mandatory_trial and browser.contexts == []
