from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.role_analysis import (
    MAX_ANALYSIS_FEEDBACK,
    AnalysisInputTooLarge,
    RoleOutputRejected,
    analyze_with_roles,
)
from backend.app.features.evolution.roles import AnalystOutput, PrioritizerOutput, UxOutput
from backend.app.features.evolution.router import get_database, get_inference
from backend.app.main import app
from backend.app.shared.database import NeonDatabase
from backend.app.shared.fixtures import SESSIONS as FIXTURE_SESSIONS
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import get_settings

PRODUCT = {"category": "product", "issue": "Upload button is hidden", "feedback_refs": ["F1", "F2"],
           "action_refs": ["A1", "A3"], "rationale": "Both personas could not find upload."}
INFRASTRUCTURE = {"category": "infrastructure", "issue": "Browser timed out",
                  "feedback_refs": ["F3"], "action_refs": ["A5"], "rationale": "Harness timeout."}
ASSESSMENTS = [{"cluster_ref": "C1", "severity": 4, "estimated_effort_hours": 2, "rationale": "Blocks upload."},
               {"cluster_ref": "C2", "severity": 2, "estimated_effort_hours": 1, "rationale": "Harness only."}]
PROPOSAL = {"cluster_ref": "C1", "title": "Show the upload control", "problem": "Upload is hidden.",
            "change": "Place the upload button above the fold.",
            "acceptance_check": "The upload button is visible at 1280x720.", "action_refs": ["A1", "A3"]}


async def test_roles_produce_separate_ranked_clusters_and_supported_proposal(
        hf_client, live_settings, live_sessions):
    hf_client.answer([PRODUCT, INFRASTRUCTURE], ASSESSMENTS, [PROPOSAL])
    report = await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                      HuggingFaceInference(live_settings, client=hf_client))
    assert report.mode == "live" and report.method == "structured_hf_roles" and report.inference_used
    assert report.sessions_seen == 4 and report.denominator == 3
    product, infrastructure = report.clusters
    assert product.category == "product" and product.patch_eligible
    assert product.severity_source == product.effort_source == "prioritizer_role"
    assert product.affected_share == pytest.approx(2 / 3) and product.evidence_strength == 1
    assert product.priority_score == pytest.approx(4 * (2 / 3) / 2, abs=1e-6)
    assert product.priority_rationale == "Blocks upload."
    assert set(product.evidence_action_ids) == {live_sessions[0].actions[0].id,
                                                live_sessions[1].actions[0].id}
    assert infrastructure.category == "infrastructure" and not infrastructure.patch_eligible
    [proposal] = report.proposals
    assert proposal.supported and proposal.cluster_id == product.id
    assert set(proposal.supporting_session_ids) == {live_sessions[0].id, live_sessions[1].id}
    assert [run.role for run in report.role_runs] == ["analyst", "prioritizer", "ux_reviewer"]
    assert {run.model_id for run in report.role_runs} == {"test/model"}
    # The UX reviewer only sees the evidenced product cluster, and models never see database IDs.
    ux_data = hf_client.calls[2]["messages"][1]["content"]
    assert '"C1"' in ux_data and '"C2"' not in ux_data
    assert all(str(session.id) not in str(call) for session in live_sessions for call in hf_client.calls)
    assert "test-secret-never-log" not in report.model_dump_json()


@pytest.mark.parametrize("findings,code", [
    ([{**PRODUCT, "action_refs": ["A1", "A5"]}], "CROSS_SESSION_REFERENCE"),
    ([{**PRODUCT, "feedback_refs": ["F1", "F9"]}], "UNKNOWN_REFERENCE"),
    ([{**PRODUCT, "action_refs": ["A99"]}], "UNKNOWN_REFERENCE"),
    ([{**PRODUCT, "feedback_refs": ["F1", "F1"]}], "DUPLICATE_REFERENCE"),
    ([{**INFRASTRUCTURE, "category": "product"}], "CATEGORY_MISMATCH"),
    ([{**PRODUCT, "feedback_refs": ["F1", "F3"], "action_refs": ["A1", "A5"]}], "CATEGORY_MISMATCH"),
    ([PRODUCT, {**PRODUCT, "issue": "  upload BUTTON is hidden "}], "DUPLICATE_FINDING"),
])
async def test_invalid_analyst_references_reject_run_before_other_roles(
        hf_client, live_settings, live_sessions, findings, code):
    hf_client.answer(findings, ASSESSMENTS, [PROPOSAL])
    with pytest.raises(RoleOutputRejected) as rejection:
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert rejection.value.code == code
    assert len(hf_client.calls) == 1


async def test_irrelevant_outcome_cannot_become_product_defect(hf_client, live_settings, live_sessions):
    live_sessions[0].outcome = "irrelevant"
    hf_client.answer([{**PRODUCT, "feedback_refs": ["F1"], "action_refs": ["A1"]}])
    with pytest.raises(RoleOutputRejected, match="boundary"):
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))


@pytest.mark.parametrize("assessments,code", [
    (ASSESSMENTS[:1], "INCOMPLETE_ASSESSMENT"),
    ([*ASSESSMENTS, {**ASSESSMENTS[0], "cluster_ref": "C3"}], "UNKNOWN_REFERENCE"),
    ([ASSESSMENTS[0], ASSESSMENTS[0], ASSESSMENTS[1]], "DUPLICATE_REFERENCE"),
])
async def test_prioritizer_must_assess_each_cluster_once(
        hf_client, live_settings, live_sessions, assessments, code):
    hf_client.answer([PRODUCT, INFRASTRUCTURE], assessments, [PROPOSAL])
    with pytest.raises(RoleOutputRejected) as rejection:
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert rejection.value.code == code
    assert len(hf_client.calls) == 2


@pytest.mark.parametrize("proposal,code", [
    ({**PROPOSAL, "cluster_ref": "C2", "action_refs": ["A5"]}, "INELIGIBLE_PROPOSAL"),
    ({**PROPOSAL, "action_refs": ["A1", "A5"]}, "EVIDENCE_OUTSIDE_CLUSTER"),
    ({**PROPOSAL, "action_refs": ["A2"]}, "EVIDENCE_OUTSIDE_CLUSTER"),
    ({**PROPOSAL, "cluster_ref": "C7"}, "UNKNOWN_REFERENCE"),
])
async def test_ux_proposals_stay_inside_product_cluster_evidence(
        hf_client, live_settings, live_sessions, proposal, code):
    hf_client.answer([PRODUCT, INFRASTRUCTURE], ASSESSMENTS, [proposal])
    with pytest.raises(RoleOutputRejected) as rejection:
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert rejection.value.code == code


async def test_proposal_without_cited_evidence_is_not_supported(hf_client, live_settings, live_sessions):
    hf_client.answer([PRODUCT], ASSESSMENTS[:1], [{**PROPOSAL, "action_refs": []}])
    report = await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                      HuggingFaceInference(live_settings, client=hf_client))
    [proposal] = report.proposals
    assert proposal.supported is False and proposal.evidence_action_ids == []
    assert "not a supported proposal" in proposal.support_note
    assert report.unclustered_feedback_ids == [live_sessions[2].feedback.id]


@pytest.mark.parametrize("action_refs,strength", [([], 0), (["A1"], 0.5)])
async def test_product_cluster_with_missing_evidence_never_reaches_ux_review(
        hf_client, live_settings, live_sessions, action_refs, strength):
    hf_client.answer([{**PRODUCT, "action_refs": action_refs}], ASSESSMENTS[:1])
    report = await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                      HuggingFaceInference(live_settings, client=hf_client))
    [cluster] = report.clusters
    assert cluster.evidence_strength == strength and cluster.patch_eligible is False
    assert cluster.priority_score == pytest.approx(4 * (2 / 3) * strength / 2, abs=1e-6)
    assert report.proposals == []
    assert [run.role for run in report.role_runs] == ["analyst", "prioritizer"]


async def test_no_feedback_makes_no_inference_call(hf_client, live_settings, live_sessions):
    sessions = [live_sessions[3]]
    report = await analyze_with_roles(sessions[0].experiment_id, sessions,
                                      HuggingFaceInference(live_settings, client=hf_client))
    assert report.mode == "live" and report.inference_used is False
    assert report.clusters == [] and report.denominator == 0 and hf_client.calls == []


async def test_fixture_and_unfinished_sessions_are_not_live_evidence(hf_client, live_settings, live_sessions):
    with pytest.raises(EvidenceMismatch, match="fixture"):
        await analyze_with_roles(FIXTURE_SESSIONS[0].experiment_id, FIXTURE_SESSIONS,
                                 HuggingFaceInference(live_settings, client=hf_client))
    live_sessions[0].status = "running"
    with pytest.raises(EvidenceMismatch, match="finished"):
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert hf_client.calls == []


async def test_cross_session_feedback_evidence_is_rejected_before_inference(
        hf_client, live_settings, live_sessions):
    live_sessions[0].feedback.evidence_action_ids = [live_sessions[1].actions[0].id]
    with pytest.raises(EvidenceMismatch, match="own session"):
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert hf_client.calls == []


async def test_oversized_evidence_is_refused_before_inference(hf_client, live_settings, live_sessions):
    template = live_sessions[0]
    sessions = []
    for _ in range(MAX_ANALYSIS_FEEDBACK + 1):
        session_id, action_id = uuid4(), uuid4()
        action = template.actions[0].model_copy(update={"id": action_id, "session_id": session_id})
        feedback = template.feedback.model_copy(update={
            "id": uuid4(), "session_id": session_id, "evidence_action_ids": [action_id]})
        sessions.append(template.model_copy(update={
            "id": session_id, "actions": [action], "feedback": feedback}))
    with pytest.raises(AnalysisInputTooLarge):
        await analyze_with_roles(template.experiment_id, sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))
    assert hf_client.calls == []


@pytest.mark.parametrize("schema", [AnalystOutput, PrioritizerOutput, UxOutput])
def test_role_schemas_are_strict(schema):
    document = schema.model_json_schema()
    for definition in [document, *document.get("$defs", {}).values()]:
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])


@pytest.mark.parametrize("findings", [
    [{**PRODUCT, "category": "usability"}],
    [{**PRODUCT, "feedback_refs": ["feedback-1"]}],
    [{**PRODUCT, "feedback_refs": []}],
    [{**PRODUCT, "severity": 5}],
])
async def test_malformed_analyst_output_fails_at_the_adapter(hf_client, live_settings, live_sessions, findings):
    hf_client.answer(findings, ASSESSMENTS, [PROPOSAL])
    with pytest.raises(InferenceError, match="INVALID_MODEL_OUTPUT"):
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))


@pytest.mark.parametrize("assessment", [{**ASSESSMENTS[0], "severity": 6},
                                        {**ASSESSMENTS[0], "estimated_effort_hours": 0},
                                        {**ASSESSMENTS[0], "cluster_ref": "cluster-1"}])
async def test_out_of_range_priority_inputs_fail_at_the_adapter(
        hf_client, live_settings, live_sessions, assessment):
    hf_client.answer([PRODUCT], [assessment])
    with pytest.raises(InferenceError, match="INVALID_MODEL_OUTPUT"):
        await analyze_with_roles(live_sessions[0].experiment_id, live_sessions,
                                 HuggingFaceInference(live_settings, client=hf_client))


@pytest.fixture
def live_api(live_settings):
    app.dependency_overrides[get_settings] = lambda: live_settings
    app.dependency_overrides[get_database] = lambda: NeonDatabase(live_settings)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_live_route_refuses_submitted_sessions(live_api, live_sessions):
    response = live_api.post(f"/api/v1/experiments/{live_sessions[0].experiment_id}/analysis",
                             json={"sessions": [s.model_dump(mode="json") for s in live_sessions]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SUBMITTED_SESSIONS_FORBIDDEN"


def test_live_route_without_database_reports_unavailable(live_api, hf_client, live_settings):
    app.dependency_overrides[get_inference] = lambda: HuggingFaceInference(live_settings, client=hf_client)
    response = live_api.post(f"/api/v1/experiments/{uuid4()}/analysis")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "DATABASE_UNAVAILABLE", "retryable": True, "details": {},
        "message": "DATABASE_URL is required for persistent database access."}
    assert hf_client.calls == []
