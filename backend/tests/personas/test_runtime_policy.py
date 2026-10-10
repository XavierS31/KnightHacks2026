"""Fake guarded inference only; no model calls or paid trial counts."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.features.personas.inference_budget import BudgetedInference
from backend.app.features.personas.mock_handoff import mock_handoff, mock_population
from backend.app.features.personas.runtime_policy import HFActionPolicy
from backend.app.features.personas.session_execution import (
    Decision,
    FeedbackDraft,
    Target,
    TrialGateError,
    TrialPlan,
)
from backend.app.shared.contracts import Action, Session
from backend.app.shared.inference import InferenceResult


class FakeGuarded(BudgetedInference):
    """Test-only subclass replaces sends; ledger reservation is tested separately."""

    def __init__(self):
        self.policy = SimpleNamespace(model_id="test/model", provider="test-provider",
                                      policy_id="fake-approved-price")
        self.calls = []
        self.output = Decision(kind="click", target_id="sample")

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return InferenceResult(value=self.output, provenance={
            "request_id": str(uuid4()), "configuration_hash": "a" * 64,
            "latency_ms": 10, "retry_count": 0, "hf_token": "secret-test-token",
            "messages": "private-review", "error": "raw-private-provider-error",
            "token_usage_if_reported": {"prompt_tokens": 100, "completion_tokens": 5,
                                        "total_tokens": 105, "private": "secret-test-token"},
        })


def trial():
    persona = mock_population(1)[0]
    handoff = mock_handoff([persona], "http://127.0.0.1:1234/")
    return TrialPlan(mode="fixture", product=handoff.version, persona=persona,
                     task=handoff.tasks[0], experiment_id=uuid4())


def session(plan):
    record = Session(id=uuid4(), experiment_id=plan.experiment_id, persona_id=plan.persona.id,
                     product_version_id=plan.product.id, status="fixture", outcome="not_run",
                     actions=[], stream_mode="fixture")
    from datetime import UTC, datetime
    record.actions = [Action(id=uuid4(), session_id=record.id, sequence=1, timestamp=datetime.now(UTC),
                             kind="navigate", result="mock_page_loaded")]
    return record


def draft(record):
    return FeedbackDraft(initial_relevance="low", post_trial_relevance="medium",
                         useful_parts=["Mock navigation"], barriers=[], suggested_changes=[],
                         evidence_action_ids=[record.actions[0].id], reason="Synthetic test")


TARGETS = [Target(id="sample", name="Load sample", action="click")]


def test_policy_rejects_direct_unbudgeted_inference():
    with pytest.raises(TypeError, match="BudgetedInference"):
        HFActionPolicy(SimpleNamespace(generate_structured=lambda: None))


async def test_low_relevance_still_decides_with_behavior_and_bounded_untrusted_context():
    inference = FakeGuarded()
    policy = HFActionPolicy(inference, initial_relevance="low")
    plan = trial()
    record = session(plan)
    result = await policy.decide(plan, TARGETS, record.actions)
    assert result.kind == "click" and result.target_id == "sample"
    call = inference.calls[0]
    context = json.loads(call["messages"][1]["content"])
    assert context["mandatory"] and context["initial_relevance"] == "low"
    assert context["fictional_persona"] and context["coverage_is_not_representativeness"]
    assert context["behavior"]["patterns"][0]["agent_policy"]
    assert context["persona"]["attribute_provenance"]
    assert context["observed_targets"] == [TARGETS[0].model_dump()]
    assert call["request_context"]["session_id"] == str(record.id)
    assert "untrusted" in call["messages"][0]["content"]
    assert "password" in call["messages"][0]["content"]
    serialized = json.dumps(policy.provenance)
    assert "secret-test-token" not in serialized and "private-review" not in serialized
    assert "raw-private-provider-error" not in serialized
    assert policy.provenance[0]["token_usage_if_reported"]["total_tokens"] == 105


@pytest.mark.parametrize("kind,target", [("click", "invented"), ("type", "sample")])
async def test_invented_and_wrong_kind_targets_are_rejected(kind, target):
    inference = FakeGuarded()
    inference.output = Decision(kind=kind, target_id=target, value="text" if kind == "type" else None)
    with pytest.raises(TrialGateError, match="UNOBSERVED_ACTION_TARGET"):
        await HFActionPolicy(inference).decide(trial(), TARGETS, [])


async def test_oversized_text_and_total_context_rejected_before_inference():
    inference = FakeGuarded()
    plan = trial()
    plan.persona.software_behavior.patterns[0].rationale = "x" * 1501
    with pytest.raises(TrialGateError, match="TEXT_TOO_LARGE"):
        await HFActionPolicy(inference).decide(plan, TARGETS, [])
    plan = trial()
    plan.persona.constraints = ["x" * 1400] * 20
    with pytest.raises(TrialGateError, match="CONTEXT_TOO_LARGE"):
        await HFActionPolicy(inference).decide(plan, TARGETS, [])
    assert inference.calls == []


async def test_target_duplicate_and_action_session_leak_rejected():
    inference = FakeGuarded()
    plan = trial()
    with pytest.raises(TrialGateError, match="DECISION_BOUND"):
        await HFActionPolicy(inference).decide(plan, TARGETS * 2, [])
    one, two = session(plan), session(plan)
    with pytest.raises(TrialGateError, match="ACTION_SESSION_MISMATCH"):
        await HFActionPolicy(inference).decide(plan, TARGETS, one.actions + two.actions)
    with pytest.raises(TrialGateError, match="ACTION_BOUND_OR_IDENTITY"):
        await HFActionPolicy(inference).decide(plan, TARGETS, one.actions * 7)
    assert inference.calls == []


async def test_policy_cannot_cross_trial_identity_or_loop_unbounded():
    inference = FakeGuarded()
    policy = HFActionPolicy(inference)
    plan = trial()
    for _ in range(6):
        await policy.decide(plan, TARGETS, [])
    with pytest.raises(TrialGateError, match="DECISION_BOUND"):
        await policy.decide(plan, TARGETS, [])
    assert len(inference.calls) == 6
    with pytest.raises(TrialGateError, match="TRIAL_MISMATCH"):
        await policy.decide(trial(), TARGETS, [])


async def test_feedback_uses_only_same_session_evidence_and_returns_validated_draft():
    inference = FakeGuarded()
    policy = HFActionPolicy(inference, initial_relevance="low")
    plan = trial()
    record = session(plan)
    inference.output = draft(record)
    result = await policy.feedback(plan, record)
    assert result.evidence_action_ids == [record.actions[0].id]
    context = json.loads(inference.calls[0]["messages"][1]["content"])
    assert "never evidence" in context["feedback_instruction"]
    with pytest.raises(TrialGateError, match="FEEDBACK_SESSION_MISMATCH"):
        await policy.feedback(plan, record)


@pytest.mark.parametrize("bad", ["foreign_action", "missing_refs", "initial_relevance", "foreign_persona"])
async def test_feedback_blocks_external_review_evidence_and_identity_changes(bad):
    inference = FakeGuarded()
    plan = trial()
    record = session(plan)
    inference.output = draft(record)
    if bad == "foreign_action":
        inference.output.evidence_action_ids = [uuid4()]
    elif bad == "missing_refs":
        inference.output.evidence_action_ids = []
    elif bad == "initial_relevance":
        inference.output.initial_relevance = "high"
    else:
        record.persona_id = uuid4()
    with pytest.raises(TrialGateError):
        await HFActionPolicy(inference, initial_relevance="low").feedback(plan, record)
    if bad == "foreign_persona":
        assert inference.calls == []


async def test_fixture_behavior_cannot_be_switched_into_live_policy():
    inference = FakeGuarded()
    plan = trial()
    plan.mode = "live"
    with pytest.raises(ValueError, match="Live trial"):
        await HFActionPolicy(inference).decide(plan, TARGETS, [])
    assert inference.calls == []


async def test_foreign_actions_in_feedback_are_rejected_before_model_context():
    inference = FakeGuarded()
    plan = trial()
    record = session(plan)
    record.actions[0].session_id = uuid4()
    with pytest.raises(TrialGateError, match="RUNTIME_FEEDBACK_SESSION_MISMATCH"):
        await HFActionPolicy(inference).feedback(plan, record)
    assert inference.calls == []
