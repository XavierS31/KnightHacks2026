from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.analysis import (
    EvidenceMismatch,
    analyze_fixture_sessions,
    validate_patch_paths,
)
from backend.app.main import app
from backend.app.shared.contracts import Action, Feedback
from backend.app.shared.fixtures import EXPERIMENT, FIXTURE_TIME, SESSIONS


def feedback_session(index=0, *, barrier="Input format is unclear", outcome="application_failure"):
    session = SESSIONS[index].model_copy(deep=True)
    action = Action(id=uuid4(), session_id=session.id, sequence=1, timestamp=FIXTURE_TIME,
                    kind="click", target="input", result="Illustrative fixture action")
    session.actions = [action]
    session.outcome = outcome
    session.feedback = Feedback(
        id=uuid4(), persona_id=session.persona_id, session_id=session.id,
        initial_relevance="medium", post_trial_relevance="medium", decision="stop",
        useful_parts=[], barriers=[barrier] if barrier else [], suggested_changes=[],
        evidence_action_ids=[action.id], reason="Fixture feedback only",
    )
    return session


def test_no_feedback_does_not_invent_support_or_improvements():
    report = analyze_fixture_sessions(EXPERIMENT.id, SESSIONS)
    assert report.sessions_seen == 10
    assert report.feedback_present == report.denominator == 0
    assert report.clusters == []
    assert report.mode == "fixture" and report.inference_used is False


def test_grouping_and_priority_use_supplied_feedback_denominator():
    first, second = feedback_session(), feedback_session(1, barrier="  Input format is unclear ")
    third = feedback_session(2, barrier="Connection timed out", outcome="infrastructure_failure")
    report = analyze_fixture_sessions(EXPERIMENT.id, [first, second, third, SESSIONS[3]])
    assert report.denominator == 3
    product = next(c for c in report.clusters if c.category == "product")
    assert product.affected_share == pytest.approx(2 / 3)
    assert product.priority_score == 2
    assert set(product.evidence_action_ids) == {first.actions[0].id, second.actions[0].id}
    assert next(c for c in report.clusters if c.category == "infrastructure").patch_eligible is False


@pytest.mark.parametrize("corrupt", ["action", "persona", "experiment", "duplicate", "missing"])
def test_invalid_evidence_is_rejected(corrupt):
    session = feedback_session()
    sessions = [session]
    if corrupt == "action":
        session.feedback.evidence_action_ids = [uuid4()]
    elif corrupt == "persona":
        session.feedback.persona_id = uuid4()
    elif corrupt == "experiment":
        session.experiment_id = uuid4()
    elif corrupt == "duplicate":
        sessions.append(session)
    else:
        session.feedback.evidence_action_ids = []
    with pytest.raises(EvidenceMismatch):
        analyze_fixture_sessions(EXPERIMENT.id, sessions)


def test_low_relevance_does_not_become_patch_defect():
    session = feedback_session(barrier="")
    session.feedback.post_trial_relevance = "low"
    report = analyze_fixture_sessions(EXPERIMENT.id, [session])
    assert report.clusters[0].category == "relevance"
    assert report.clusters[0].patch_eligible is False


def test_irrelevant_outcome_barriers_are_not_product_defects():
    session = feedback_session(barrier="I have no personal need for this", outcome="irrelevant")
    report = analyze_fixture_sessions(EXPERIMENT.id, [session])
    assert report.clusters[0].category == "relevance"
    assert report.clusters[0].patch_eligible is False


def test_live_sessions_cannot_be_submitted_as_fixture_evidence():
    session = feedback_session()
    session.status = "completed"
    session.stream_mode = "live"
    with pytest.raises(EvidenceMismatch):
        analyze_fixture_sessions(EXPERIMENT.id, [session])


def test_routes_keep_fixture_label_and_deny_unreviewed_promotion():
    client = TestClient(app)
    response = client.post(f"/api/v1/experiments/{EXPERIMENT.id}/analysis")
    assert response.status_code == 200
    assert response.json()["mode"] == "fixture"
    assert response.json()["clusters"] == []
    assert client.post(f"/api/v1/experiments/{uuid4()}/analysis").status_code == 404
    denial = client.post(f"/api/v1/patch-runs/{uuid4()}/approve")
    assert denial.status_code == 409
    assert denial.json()["error"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("path", ["../product/a.py", "product/../backend/app.py", "/product/a.py",
                                  "C:\\product\\a.py", "backend/a.py", "product"])
def test_patch_boundaries_reject_escape(path):
    with pytest.raises(ValueError):
        validate_patch_paths([path])


def test_product_descendant_path_is_allowed():
    validate_patch_paths(["product/src/app.py"])
