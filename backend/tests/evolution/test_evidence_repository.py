from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.repository import (
    ExperimentNotFound,
    SessionEvidenceRepository,
    assemble_sessions,
)
from backend.app.features.evolution.router import get_database, get_inference
from backend.app.main import app
from backend.app.shared.database import NeonDatabase
from backend.app.shared.inference import HuggingFaceInference
from backend.app.shared.settings import get_settings

FINDINGS = [{"category": "product", "issue": "Upload button is hidden", "feedback_refs": ["F1", "F2"],
             "action_refs": ["A1", "A3"], "rationale": "Both personas could not find upload."},
            {"category": "infrastructure", "issue": "Browser timed out", "feedback_refs": ["F3"],
             "action_refs": ["A5"], "rationale": "Harness timeout."}]
ASSESSMENTS = [{"cluster_ref": "C1", "severity": 4, "estimated_effort_hours": 2, "rationale": "Blocks upload."},
               {"cluster_ref": "C2", "severity": 2, "estimated_effort_hours": 1, "rationale": "Harness only."}]
PROPOSALS = [{"cluster_ref": "C1", "title": "Show the upload control", "problem": "Upload is hidden.",
              "change": "Place the upload button above the fold.",
              "acceptance_check": "The upload button is visible at 1280x720.", "action_refs": ["A1"]}]


@pytest.fixture
def rows(live_sessions):
    """The stored-row form of live_sessions, following the repository's row convention."""
    experiment = {"id": live_sessions[0].experiment_id, "fixture": False}
    sessions = [{"id": s.id, "experiment_id": s.experiment_id, "persona_id": s.persona_id,
                 "product_version_id": s.product_version_id, "status": s.status, "outcome": s.outcome,
                 "provenance": {"stream_mode": s.stream_mode, "stop_reason": s.stop_reason},
                 "fixture": False} for s in live_sessions]
    actions = [{"id": a.id, "session_id": a.session_id, "sequence": a.sequence, "occurred_at": a.timestamp,
                "payload": {"kind": a.kind, "target": a.target, "result": a.result},
                "artifact_ref": a.artifact_ref} for s in live_sessions for a in reversed(s.actions)]
    feedback = [{"id": s.feedback.id, "session_id": s.id, "payload": s.feedback.model_dump(mode="json")}
                for s in live_sessions if s.feedback]
    return experiment, sessions, actions, feedback


def test_rows_rebuild_contract_sessions_in_sequence_order(rows, live_sessions):
    assert assemble_sessions(*rows) == live_sessions


@pytest.mark.parametrize("corrupt", ["fixture_experiment", "fixture_session", "foreign_session",
                                     "orphan_action", "orphan_feedback", "payload_identity",
                                     "action_payload", "feedback_payload", "stream_mode"])
def test_disagreeing_or_orphaned_rows_are_rejected(rows, corrupt):
    experiment, sessions, actions, feedback = rows
    if corrupt == "fixture_experiment":
        experiment["fixture"] = True
    elif corrupt == "fixture_session":
        sessions[0]["fixture"] = True
    elif corrupt == "foreign_session":
        sessions[0]["experiment_id"] = uuid4()
    elif corrupt == "orphan_action":
        actions[0]["session_id"] = uuid4()
    elif corrupt == "orphan_feedback":
        feedback[0]["session_id"] = uuid4()
    elif corrupt == "payload_identity":
        feedback[0]["payload"]["session_id"] = str(sessions[1]["id"])
    elif corrupt == "action_payload":
        del actions[0]["payload"]["kind"]
    elif corrupt == "feedback_payload":
        feedback[0]["payload"]["decision"] = "maybe"
    else:
        del sessions[0]["provenance"]["stream_mode"]
    with pytest.raises(EvidenceMismatch):
        assemble_sessions(experiment, sessions, actions, feedback)


@pytest.fixture
def corrupt():
    return None


@pytest.fixture
def stored(migrated_settings, live_sessions, corrupt):
    """Persist live_sessions, with any requested faulty reference, into the 001 tables."""
    if corrupt == "missing_action":
        live_sessions[0].feedback.evidence_action_ids.append(uuid4())
    elif corrupt == "cross_session":
        live_sessions[0].feedback.evidence_action_ids = [live_sessions[1].actions[0].id]
    url = migrated_settings.database_url.get_secret_value()
    first = live_sessions[0]
    with psycopg.connect(url, sslmode="require") as connection:
        connection.execute(
            "INSERT INTO product_versions (id, label, status, manifest) VALUES (%s, 'v1', 'validated', %s)",
            (first.product_version_id, Jsonb({})))
        connection.execute(
            "INSERT INTO experiments (id, population_id, product_version_id, task_set_id, "
            "configuration, status) VALUES (%s, %s, %s, %s, %s, 'completed')",
            (first.experiment_id, uuid4(), first.product_version_id, uuid4(), Jsonb({})))
        for session in live_sessions:
            connection.execute(
                "INSERT INTO sessions (id, experiment_id, persona_id, task_id, product_version_id, "
                "attempt, status, outcome, provenance) VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)",
                (session.id, session.experiment_id, session.persona_id, uuid4(),
                 session.product_version_id, session.status, session.outcome,
                 Jsonb({"stream_mode": session.stream_mode, "stop_reason": session.stop_reason})))
            for action in session.actions:
                connection.execute(
                    "INSERT INTO actions (id, session_id, sequence, occurred_at, payload) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (action.id, session.id, action.sequence, action.timestamp,
                     Jsonb({"kind": action.kind, "target": action.target, "result": action.result})))
            if session.feedback:
                connection.execute(
                    "INSERT INTO feedback (id, session_id, payload) VALUES (%s, %s, %s)",
                    (session.feedback.id, session.id, Jsonb(session.feedback.model_dump(mode="json"))))
    return migrated_settings


def test_repository_reads_persisted_evidence_in_one_snapshot(stored, live_sessions):
    database = NeonDatabase(stored)
    try:
        loaded = SessionEvidenceRepository(database).load(live_sessions[0].experiment_id)
        assert sorted(loaded, key=lambda s: s.id) == sorted(live_sessions, key=lambda s: s.id)
        with pytest.raises(ExperimentNotFound):
            SessionEvidenceRepository(database).load(uuid4())
    finally:
        database.close()


@pytest.mark.parametrize("corrupt,status,code", [
    (None, 200, None),
    ("missing_action", 422, "EVIDENCE_MISMATCH"),
    ("cross_session", 422, "EVIDENCE_MISMATCH"),
])
def test_live_route_analyzes_only_grounded_persisted_evidence(
        stored, live_sessions, hf_client, corrupt, status, code):
    hf_client.answer(FINDINGS, ASSESSMENTS, PROPOSALS)
    database = NeonDatabase(stored)
    app.dependency_overrides[get_settings] = lambda: stored
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_inference] = lambda: HuggingFaceInference(stored, client=hf_client)
    try:
        response = TestClient(app).post(f"/api/v1/experiments/{live_sessions[0].experiment_id}/analysis")
    finally:
        app.dependency_overrides.clear()
        database.close()
    assert response.status_code == status
    if code:
        assert response.json()["error"]["code"] == code
        assert hf_client.calls == []
        return
    report = response.json()
    assert report["mode"] == "live" and report["inference_used"] is True
    assert [run["role"] for run in report["role_runs"]] == ["analyst", "prioritizer", "ux_reviewer"]
    assert [cluster["category"] for cluster in report["clusters"]] == ["product", "infrastructure"]
    assert report["proposals"][0]["supported"] is True
