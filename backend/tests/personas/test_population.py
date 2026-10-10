"""Invented sources and fake HF only; no actual review or population generation evidence."""
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.features.personas.behavior_extraction import BehaviorProposals, PendingExtraction
from backend.app.features.personas.population import (
    ApprovedBehavior,
    CoverageQuota,
    FictionalDetails,
    FrozenPopulation,
    IndependentSupportReview,
    PopulationError,
    approve_behavior,
    generate_population,
)
from backend.app.features.personas.review_corpus import (
    CollectedReview,
    curate_review,
    freeze_corpus,
)
from backend.app.shared.contracts import Task
from backend.app.shared.inference import InferenceError


def inputs():
    source = CollectedReview(platform="hacker_news", external_id="101",
        source_url="https://news.ycombinator.com/item?id=101", published_at=None,
        retrieved_at=datetime(2026, 10, 10, tzinfo=UTC), software_context="Study cards",
        selection_context="Invented unit test", collection_method="manual",
        access_basis="Invented test-only record, never collected",
        source_text="I try a sample first.")
    review = curate_review(source, summary="Test paraphrase: tries sample first",
        excerpt="I try a sample first.", report_type="self_report", privacy_reviewed=True,
        limitations=["Invented test-only source"])
    corpus = freeze_corpus([review], software_context="Study cards", selection_limits=["Test only"])
    pattern_id = uuid4()
    proposals = BehaviorProposals.model_validate({"software_context": "Study cards",
        "limitations": ["Tentative interpretation"], "proposals": [{"pattern": {
            "id": str(pattern_id), "dimension": "onboarding", "tendency": "Try sample first",
            "trigger": "First use", "agent_policy": "Select sample if available within limits",
            "evidence_ids": [str(review.evidence.id)], "interpretation_confidence": "low",
            "rationale": "The test report explicitly mentions trying a sample"},
            "source_support": [{"evidence_id": str(review.evidence.id), "excerpt": "sample first"}]}]})
    draft = PendingExtraction(corpus.version, proposals.model_dump_json(),
                              json.dumps({"request_id": "extractor-request", "provider": "fake"}))
    support = IndependentSupportReview(reviewer_ref="independent-test-reviewer",
        reviewer_kind="human", independent_of_extractor=True, context_compatible=True,
        decisions=[{"pattern_id": pattern_id, "supported": True, "context_compatible": True,
                    "rationale": "Test source supports sample preference in compatible workflow"}],
        limitations=["Test-only review; not real approval"])
    task = Task(id=uuid4(), scenario_id=uuid4(), capability_ids=[uuid4()], goal="Try sample",
                initial_state_ref="sample-state", check_id="sample-check", task_version="v1",
                action_budget=6)
    quota = CoverageQuota(cohort="resident", count=2, active_role="Learner", location_id="home",
                          device="laptop", task_template_id=task.id,
                          assumption="Intentional fictional learner coverage, not demographics")
    return corpus, draft, support, task, quota


class FakeHF:
    def __init__(self, payload=None, fail=False):
        self.calls = []
        self.payload = payload or {"synthetic_name": "Fictional learner", "skills": ["Reading"],
                                   "constraints": ["Short time budget"]}
        self.fail = fail

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise InferenceError("BUDGET_EXHAUSTED")
        return SimpleNamespace(value=kwargs["output_schema"].model_validate(self.payload),
                               provenance={"provider": "fake", "request_id": str(len(self.calls))})


async def generated(count=2, purpose="pilot", adapter=None):
    corpus, draft, support, task, quota = inputs()
    quota.count = count
    approval = approve_behavior(draft, corpus, support)
    return await generate_population(corpus, approval, adapter or FakeHF(), quotas=[quota],
                                    task_templates=[task], generation_version="generation-v1",
                                    purpose=purpose)


def test_approval_is_explicit_independent_and_hash_bound():
    corpus, draft, review, _, _ = inputs()
    approved = approve_behavior(draft, corpus, review)
    assert approved.data(corpus)["review"]["reviewer_kind"] == "human"
    assert not hasattr(draft, "software_behavior")
    with pytest.raises(PopulationError, match="APPROVAL_VERSION_MISMATCH"):
        ApprovedBehavior(approved.snapshot_json + " ", approved.version).data(corpus)
    review.reviewer_ref = "extractor-request"
    with pytest.raises(PopulationError, match="EXTRACTOR_CANNOT_APPROVE_OWN_DRAFT"):
        approve_behavior(draft, corpus, review)


@pytest.mark.parametrize("field,value", [("independent_of_extractor", False),
    ("reviewer_kind", "software_behavior_extractor"), ("context_compatible", False)])
def test_review_rejects_self_approval_or_context_mismatch(field, value):
    _, _, review, _, _ = inputs()
    data = review.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        IndependentSupportReview.model_validate(data)


def test_review_must_resolve_each_unique_pattern():
    corpus, draft, review, _, _ = inputs()
    review.decisions[0].pattern_id = uuid4()
    with pytest.raises(PopulationError, match="INVALID_SUPPORT_DECISIONS"):
        approve_behavior(draft, corpus, review)
    proposals = BehaviorProposals.model_validate_json(draft.output_json)
    review.decisions[0].pattern_id = proposals.proposals[0].pattern.id
    review.decisions.append(review.decisions[0])
    with pytest.raises(PopulationError, match="INVALID_SUPPORT_DECISIONS"):
        approve_behavior(draft, corpus, review)


async def test_pilot_freezes_exact_identity_behavior_task_and_assumptions():
    corpus, draft, review, task, quota = inputs()
    approval = approve_behavior(draft, corpus, review)
    hf = FakeHF()
    first = await generate_population(corpus, approval, hf, quotas=[quota], task_templates=[task],
                                      generation_version="generation-v1", purpose="pilot")
    second = await generate_population(corpus, approval, FakeHF(), quotas=[quota],
        task_templates=[task], generation_version="generation-v1", purpose="pilot")
    assert first.version == second.version
    data = first.data()
    assert data["status"] == "pilot_only" and data["completed_trials"] == 0
    assert len(hf.calls) == 2
    personas = first.personas()
    assert len({p.id for p in personas}) == 2
    assert personas[0].software_behavior.status == "review_informed"
    assert personas[0].software_behavior.corpus_version == corpus.version
    assert all(p.attribute_provenance["cohort"] == "scenario_assumption" for p in personas)
    assert "source_url" not in hf.calls[0]["messages"][1]["content"]
    personas[0].software_behavior.patterns[0].agent_policy = "Mutated"
    assert first.personas()[0].software_behavior.patterns[0].agent_policy != "Mutated"
    assert first.tasks()[0].check_id == task.check_id


@pytest.mark.parametrize("count,purpose", [(20, "complete"), (21, "pilot"), (0, "pilot")])
async def test_invalid_population_size_fails_before_hf(count, purpose):
    corpus, draft, review, task, quota = inputs()
    quota.count = count
    hf = FakeHF()
    with pytest.raises((PopulationError, ValidationError)):
        await generate_population(corpus, approve_behavior(draft, corpus, review), hf,
            quotas=[quota], task_templates=[task], generation_version="v1", purpose=purpose)
    assert hf.calls == []


async def test_complete_population_is_exactly_500_configured_not_trials():
    snapshot = await generated(500, "complete")
    assert snapshot.data()["configured_count"] == 500
    assert snapshot.data()["completed_trials"] == 0
    assert len({p.id for p in snapshot.personas()}) == 500


@pytest.mark.parametrize("extra", ["cohort", "software_behavior", "evidence", "source_url"])
async def test_model_cannot_supply_sources_behavior_or_demographics(extra):
    hf = FakeHF({"synthetic_name": "Fictional", "skills": ["Reading"],
                 "constraints": ["Time"], extra: "invented"})
    with pytest.raises(ValidationError):
        await generated(adapter=hf)


async def test_provider_budget_failure_remains_failure_without_fixture_fallback():
    with pytest.raises(InferenceError, match="BUDGET_EXHAUSTED"):
        await generated(adapter=FakeHF(fail=True))


@pytest.mark.parametrize("change", ["task_check", "task_catalog", "corpus_version", "fixture",
                                     "completed_trials", "persona_id", "policy", "evidence",
                                     "scenario", "attribute_provenance"])
async def test_matched_snapshot_rejects_identity_and_lineage_alterations(change):
    original = await generated()
    data = original.data()
    if change == "task_check":
        data["tasks"][0]["check_id"] = "altered-check"
    elif change == "task_catalog":
        data["task_catalog"][0]["check_id"] = "altered-check"
    elif change == "fixture":
        data["personas"][0]["software_behavior"]["status"] = "fixture"
    elif change == "corpus_version":
        data["personas"][0]["software_behavior"]["corpus_version"] = "other"
    elif change == "persona_id":
        data["personas"][0]["id"] = str(uuid4())
    elif change == "policy":
        data["personas"][0]["software_behavior"]["patterns"][0]["agent_policy"] = "New policy"
    elif change == "evidence":
        data["personas"][0]["software_behavior"]["evidence"][0]["content_sha256"] = "b" * 64
    elif change == "scenario":
        data["personas"][0]["scenario"]["goal"] = "Changed goal"
    elif change == "attribute_provenance":
        data["personas"][0]["attribute_provenance"]["cohort"] = "sourced_distribution"
    else:
        data["completed_trials"] = 1
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
    altered = FrozenPopulation(encoded, hashlib.sha256(encoded.encode()).hexdigest())
    with pytest.raises((PopulationError, ValidationError)):
        altered.data()


def test_pending_extraction_cannot_pass_as_approved_behavior():
    corpus, draft, review, _, _ = inputs()
    altered = PendingExtraction("wrong-version", draft.output_json, draft.provenance_json)
    with pytest.raises(PopulationError, match="INVALID_PENDING_EXTRACTION"):
        approve_behavior(altered, corpus, review)
    assert not hasattr(draft, "data")


def test_bounded_fictional_schema_rejects_large_output():
    with pytest.raises(ValidationError):
        FictionalDetails(synthetic_name="A" * 100, skills=["Read"], constraints=["Time"])


@pytest.mark.parametrize("change", ["missing", "too_many_actions", "no_check", "duplicate"])
async def test_invalid_task_catalog_prevents_generation(change):
    corpus, draft, review, task, quota = inputs()
    hf = FakeHF()
    templates = [task]
    if change == "missing":
        quota.task_template_id = uuid4()
    elif change == "too_many_actions":
        task.action_budget = 8
    elif change == "no_check":
        task.check_id = ""
    else:
        templates.append(task)
    with pytest.raises(PopulationError, match="INVALID_TASK_CATALOG"):
        await generate_population(corpus, approve_behavior(draft, corpus, review), hf,
            quotas=[quota], task_templates=templates, generation_version="v1", purpose="pilot")
    assert hf.calls == []


def test_independent_model_review_is_allowed_without_extractor_self_approval():
    corpus, draft, review, _, _ = inputs()
    review.reviewer_kind = "independent_model"
    assert approve_behavior(draft, corpus, review).data(corpus)["review"]["reviewer_kind"] == (
        "independent_model")
