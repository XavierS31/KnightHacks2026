"""Synthetic offline evidence tests; database cases use a disposable migrated schema."""

from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.analysis import analyze_fixture_sessions
from backend.app.features.evolution.analysis_repository import (
    AnalysisRepository,
    session_fingerprints,
)
from backend.app.features.evolution.improvement_intake import (
    improvement_from_report,
    validate_improvement,
)
from backend.app.features.evolution.models import (
    PRIORITY_FORMULA,
    AnalysisReport,
    FeedbackCluster,
    ProposalDraft,
    RoleRun,
)
from backend.app.features.evolution.repository import SessionEvidenceRepository
from backend.app.features.evolution.router import frozen_v1_base, get_database
from backend.app.main import app
from backend.app.shared.database import NeonDatabase, RecordInvalid, RecordMissing
from backend.app.shared.fixtures import EXPERIMENT, SESSIONS
from backend.app.shared.session_records import SessionRepository
from backend.app.shared.settings import Settings, get_settings


@pytest.fixture
def analysis_case(live_sessions):
    """Invented checked report for exercising deterministic intake, without model calls."""
    session = live_sessions[0]
    cluster = FeedbackCluster(
        id=uuid4(), category="product", issue="Upload is hidden",
        supporting_session_ids=[session.id], supporting_feedback_ids=[session.feedback.id],
        evidence_action_ids=[session.actions[0].id], severity=4,
        severity_source="prioritizer_role", affected_share=1 / 3, evidence_strength=1,
        estimated_effort_hours=2, effort_source="prioritizer_role", priority_score=2 / 3,
        patch_eligible=True)
    proposal = ProposalDraft(
        id=uuid4(), cluster_id=cluster.id, title="Show upload", problem="Upload is hidden",
        change="Place upload above the fold", acceptance_check="Upload is visible at 1280x720",
        supporting_session_ids=[session.id], evidence_action_ids=[session.actions[0].id],
        supported=True, support_note="Synthetic test evidence")
    report = AnalysisReport(
        experiment_id=session.experiment_id, mode="live", method="structured_hf_roles",
        inference_used=True, sessions_seen=4, feedback_present=3, denominator=3,
        priority_formula=PRIORITY_FORMULA, clusters=[cluster], unclustered_feedback_ids=[],
        proposals=[proposal], role_runs=[RoleRun(
            role=role, request_id=f"synthetic-{role}", model_id="test/model", provider="test",
            prompt_version="test-v1", configuration_hash="test", latency_ms=1, retry_count=0)
            for role in ("analyst", "prioritizer", "ux_reviewer")],
        limitations=["Synthetic test records; no real trials or inference."], next_gate="Review")
    return report, live_sessions


def test_supported_report_supplies_improvement_and_directory_scope(analysis_case):
    report, sessions = analysis_case
    improvement = improvement_from_report(report, report.proposals[0].id, ["product/ui"],
                                          sessions, sessions[0].product_version_id)
    validate_improvement(improvement, report, sessions, sessions[0].product_version_id)
    assert improvement.id == report.proposals[0].id
    assert improvement.status == "proposed"
    assert "Proposed change: Place upload above the fold" in improvement.issue
    assert improvement.supporting_session_ids == [sessions[0].id]


@pytest.mark.parametrize("corruption", [
    "unsupported", "missing_proposal", "duplicate_proposal", "infrastructure_cluster",
    "ineligible", "weak_evidence", "unknown_action", "cross_session", "missing_session",
    "no_action", "duplicate_action", "duplicate_session", "wrong_base", "not_run",
    "irrelevant", "no_feedback", "no_product_barrier", "outside_cluster", "no_inference",
])
def test_unexecuted_or_unresolvable_proposals_cannot_start_runs(analysis_case, corruption):
    report, sessions = analysis_case
    proposal = report.proposals[0]
    base = sessions[0].product_version_id
    if corruption == "unsupported":
        proposal.supported = False
    elif corruption == "missing_proposal":
        report.proposals = []
    elif corruption == "duplicate_proposal":
        report.proposals.append(proposal)
    elif corruption == "infrastructure_cluster":
        report.clusters[0].category = "infrastructure"
    elif corruption == "ineligible":
        report.clusters[0].patch_eligible = False
    elif corruption == "weak_evidence":
        report.clusters[0].evidence_strength = 0.5
    elif corruption == "unknown_action":
        proposal.evidence_action_ids = [uuid4()]
    elif corruption == "cross_session":
        proposal.evidence_action_ids = [sessions[1].actions[0].id]
        report.clusters[0].evidence_action_ids = proposal.evidence_action_ids
    elif corruption == "missing_session":
        proposal.supporting_session_ids = [uuid4()]
    elif corruption == "no_action":
        proposal.evidence_action_ids = []
    elif corruption == "duplicate_action":
        proposal.evidence_action_ids *= 2
    elif corruption == "duplicate_session":
        proposal.supporting_session_ids *= 2
    elif corruption == "wrong_base":
        base = uuid4()
    elif corruption == "not_run":
        sessions[0].outcome = "not_run"
    elif corruption == "irrelevant":
        sessions[0].outcome = "irrelevant"
    elif corruption == "no_feedback":
        sessions[0].feedback = None
    elif corruption == "no_product_barrier":
        sessions[0].feedback.barriers = []
    elif corruption == "outside_cluster":
        report.clusters[0].supporting_session_ids = []
    else:
        report.inference_used = False
    with pytest.raises(RecordInvalid):
        improvement_from_report(report, proposal.id, ["product/ui/app.js"], sessions, base)


@pytest.mark.parametrize("scope", [[], ["product"], ["product/ui/checks.py"],
                                  ["product/backend/app.py"],
                                  ["product/ui/../checks.py"], ["product/ui/app.js"] * 2])
def test_scope_is_bounded_before_human_review(analysis_case, scope):
    report, sessions = analysis_case
    with pytest.raises(RecordInvalid, match="scope"):
        improvement_from_report(report, report.proposals[0].id, scope, sessions,
                                sessions[0].product_version_id)


@pytest.mark.parametrize("update", [
    {"title": "A different improvement"}, {"acceptance_check": "Always passes"},
    {"severity": 1}, {"evidence_strength": 0.5}, {"status": "reviewed"},
    {"supporting_session_ids": []},
])
def test_caller_cannot_rewrite_proposal_or_priority_inputs(analysis_case, update):
    report, sessions = analysis_case
    improvement = improvement_from_report(report, report.proposals[0].id, ["product/ui/app.js"],
                                          sessions, sessions[0].product_version_id)
    with pytest.raises(RecordInvalid):
        validate_improvement(improvement.model_copy(update=update), report, sessions,
                             sessions[0].product_version_id)


def test_fixture_report_never_opens_persistent_storage():
    database = NeonDatabase(Settings(_env_file=None, app_mode="fixture"))
    report = analyze_fixture_sessions(EXPERIMENT.id, SESSIONS)
    with pytest.raises(RecordInvalid, match="Fixture"):
        AnalysisRepository(database).save_report(report, SESSIONS)
    with pytest.raises(RecordInvalid, match="live E1"):
        improvement_from_report(report, uuid4(), ["product/ui"], SESSIONS, uuid4())


def test_live_intake_without_storage_fails_closed(analysis_case):
    report, sessions = analysis_case
    settings = Settings(_env_file=None, app_mode="live", database_url="")
    database = NeonDatabase(settings)
    improvement = improvement_from_report(report, report.proposals[0].id, ["product/ui/app.js"],
                                          sessions, sessions[0].product_version_id)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database] = lambda: database
    try:
        response = TestClient(app).post(f"/api/v1/improvements/{improvement.id}/patch-runs", json={
            "actor": {"id": "test-reviewer", "role": "human_reviewer"},
            "improvement": improvement.model_dump(mode="json")})
    finally:
        app.dependency_overrides.clear()
        database.close()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_fingerprints_normalize_database_timezone_and_action_order(analysis_case):
    _, sessions = analysis_case
    expected = session_fingerprints(sessions)
    for session in sessions:
        session.actions.reverse()
        for action in session.actions:
            action.timestamp = action.timestamp.astimezone(timezone(timedelta(hours=-4)))
    assert session_fingerprints(sessions) == expected
    sessions[0].actions[0].timestamp = sessions[0].actions[0].timestamp.replace(tzinfo=None)
    with pytest.raises(RecordInvalid, match="timezone"):
        session_fingerprints(sessions)


@pytest.fixture
def persisted_case(migrated, analysis_case):
    report, sessions = analysis_case
    report.experiment_id = migrated["experiment_id"]
    repository = SessionRepository(migrated["database"])
    for session in sessions:
        session.experiment_id = migrated["experiment_id"]
        session.product_version_id = migrated["version_id"]
        repository.create(session.model_copy(update={
            "status": "running", "outcome": "not_run", "actions": [], "feedback": None}),
            task_id=uuid4(), attempt=1, provenance={"worker": "synthetic-test"})
        for action in session.actions:
            repository.append_action(action)
        if session.feedback:
            repository.record_feedback(session.feedback)
        repository.finish(session.id, status=session.status, outcome=session.outcome,
                          stop_reason=session.stop_reason)
    return migrated, report, sessions


def test_report_survives_repository_restart_and_is_idempotent(persisted_case):
    migrated, report, sessions = persisted_case
    repository = AnalysisRepository(migrated["database"])
    identity = repository.save_report(report, sessions)
    assert repository.save_report(report, sessions) == identity
    restarted = AnalysisRepository(migrated["database"])
    record, restored = restarted.report_for_proposal(report.proposals[0].id)
    assert restored == report and record.id == identity
    restarted.validate_report_evidence(record, sessions)
    with pytest.raises(RecordMissing):
        restarted.report_for_proposal(uuid4())
    sessions[0].actions[0].result = "Evidence changed after analysis"
    with pytest.raises(RecordInvalid, match="changed"):
        restarted.validate_report_evidence(record, sessions)


def test_worker_written_evidence_columns_feed_e1(persisted_case):
    migrated, report, sessions = persisted_case
    loaded = SessionEvidenceRepository(migrated["database"]).load(report.experiment_id)
    assert sorted(loaded, key=lambda item: item.id) == sorted(sessions, key=lambda item: item.id)
    assert loaded[0].stop_reason == "task ended"
    assert loaded[0].stream_mode == "replay"


def test_live_route_requires_a_saved_matching_e1_proposal(persisted_case):
    migrated, report, sessions = persisted_case
    # The task's runtime base is A's frozen v1, not the invented database test version.
    with migrated["database"].connection() as connection:
        connection.execute("INSERT INTO product_versions (id, label, status, manifest) "
                           "VALUES (%s, 'test frozen base', 'validated', '{}') "
                           "ON CONFLICT DO NOTHING", (frozen_v1_base().version_id,))
        connection.execute("UPDATE sessions SET product_version_id = %s WHERE experiment_id = %s",
                           (frozen_v1_base().version_id, report.experiment_id))
    for session in sessions:
        session.product_version_id = frozen_v1_base().version_id
    improvement = improvement_from_report(report, report.proposals[0].id, ["product/ui/app.js"],
                                          sessions, frozen_v1_base().version_id)
    app.dependency_overrides[get_settings] = lambda: migrated["settings"]
    app.dependency_overrides[get_database] = lambda: migrated["database"]
    client = TestClient(app)
    body = {"actor": {"id": "test-prioritizer", "role": "prioritizer"},
            "improvement": improvement.model_dump(mode="json")}
    try:
        missing = client.post(f"/api/v1/improvements/{improvement.id}/patch-runs", json=body)
        assert missing.status_code == 409
        assert missing.json()["error"]["code"] == "E1_PROPOSAL_REQUIRED"
        record_id = AnalysisRepository(migrated["database"]).save_report(report, sessions)
        created = client.post(f"/api/v1/improvements/{improvement.id}/patch-runs", json=body)
        assert created.status_code == 201, created.json()
        assert created.json()["state"] == "proposed"
        assert str(record_id) in created.json()["events"][0]["note"]
        body["improvement"]["acceptance_check"] = "Always passes"
        rejected = client.post(f"/api/v1/improvements/{improvement.id}/patch-runs", json=body)
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "E1_EVIDENCE_MISMATCH"
    finally:
        app.dependency_overrides.clear()
