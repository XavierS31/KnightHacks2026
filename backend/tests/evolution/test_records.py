from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from backend.app.features.evolution.analysis_repository import AnalysisRepository
from backend.app.features.evolution.models import AnalysisRecord
from backend.app.shared.contracts import Action, Feedback, Session
from backend.app.shared.database import (
    DatabaseUnavailable,
    NeonDatabase,
    RecordConflict,
    RecordInvalid,
    RecordMissing,
)
from backend.app.shared.session_records import SessionRepository
from backend.app.shared.settings import Settings

STARTED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def offline():
    return NeonDatabase(Settings(_env_file=None, app_mode="fixture"))


@pytest.fixture
def recorded(migrated):
    """Two running sessions in the migrated experiment, each with two actions."""
    repository = SessionRepository(migrated["database"])
    sessions = []
    for _ in range(2):
        session = Session(id=uuid4(), experiment_id=migrated["experiment_id"], persona_id=uuid4(),
                          product_version_id=migrated["version_id"], status="running",
                          outcome="not_run", actions=[], stream_mode="live")
        repository.create(session, task_id=uuid4(), attempt=1, provenance={"worker": "test"})
        actions = [Action(id=uuid4(), session_id=session.id, sequence=sequence,
                          timestamp=STARTED, kind="click", target=f"button-{sequence}",
                          result="opened", artifact_ref=f"sessions/{session.id}/{sequence}.png")
                   for sequence in (1, 2)]
        for action in actions:
            repository.append_action(action)
        sessions.append(session.model_copy(update={"actions": actions}))
    return {**migrated, "repository": repository, "sessions": sessions}


@pytest.mark.parametrize("mode,url", [("fixture", "postgresql://fixture:secret@invalid/test"),
                                      ("live", "")])
def test_absent_configuration_makes_no_connection(mode, url):
    database = NeonDatabase(Settings(_env_file=None, app_mode=mode, database_url=SecretStr(url)))
    with pytest.raises(DatabaseUnavailable):
        SessionRepository(database).get(uuid4())
    with pytest.raises(DatabaseUnavailable):
        AnalysisRepository(database).list_for_experiment(uuid4())


@pytest.mark.parametrize("reference", [
    "data:image/png;base64,iVBORw0KGgo=", "/var/artifacts/1.png", "C:\\artifacts\\1.png",
    "../secrets/1.png", "sessions/a\n.png", "", "x" * 513])
def test_inline_or_escaping_artifact_refs_fail_before_any_connection(offline, reference):
    action = Action(id=uuid4(), session_id=uuid4(), sequence=1, timestamp=STARTED, kind="click",
                    result="opened", artifact_ref=reference)
    with pytest.raises(RecordInvalid):
        SessionRepository(offline).append_action(action)


@pytest.mark.parametrize("update", [{"status": "fixture"}, {"stream_mode": "fixture"},
                                    {"status": "completed"}, {"outcome": "success"}])
def test_fixture_or_finished_sessions_cannot_be_created(offline, update):
    session = Session(id=uuid4(), experiment_id=uuid4(), persona_id=uuid4(),
                      product_version_id=uuid4(), status="running", outcome="not_run",
                      actions=[], stream_mode="live").model_copy(update=update)
    with pytest.raises(RecordInvalid):
        SessionRepository(offline).create(session, task_id=uuid4(), attempt=1, provenance={})


def test_session_actions_and_feedback_round_trip(recorded):
    repository, session = recorded["repository"], recorded["sessions"][0]
    feedback = Feedback(id=uuid4(), persona_id=session.persona_id, session_id=session.id,
                        initial_relevance="medium", post_trial_relevance="high", decision="stop",
                        useful_parts=["table preview"], barriers=["unclear error"],
                        suggested_changes=["name the bad cell"],
                        evidence_action_ids=[session.actions[1].id], reason="Task finished.")
    repository.record_feedback(feedback)
    repository.finish(session.id, status="completed", outcome="success", stop_reason="verified")

    expected = session.model_copy(update={"status": "completed", "outcome": "success",
                                          "stop_reason": "verified", "feedback": feedback})
    assert repository.get(session.id) == expected
    assert repository.list_for_experiment(recorded["experiment_id"]) == [
        expected, recorded["sessions"][1]]
    assert repository.get(uuid4()) is None


def test_cross_session_feedback_is_rejected_and_nothing_is_written(recorded):
    repository, (session, other) = recorded["repository"], recorded["sessions"]
    feedback = Feedback(id=uuid4(), persona_id=session.persona_id, session_id=session.id,
                        initial_relevance="low", post_trial_relevance="low", decision="stop",
                        useful_parts=[], barriers=["slow"], suggested_changes=[],
                        evidence_action_ids=[session.actions[0].id, other.actions[0].id],
                        reason="Too slow.")
    with pytest.raises(RecordInvalid, match="another session"):
        repository.record_feedback(feedback)
    with pytest.raises(RecordInvalid, match="persona"):
        repository.record_feedback(feedback.model_copy(update={"persona_id": other.persona_id}))
    with pytest.raises(RecordMissing):
        repository.record_feedback(feedback.model_copy(update={"session_id": uuid4()}))
    assert repository.get(session.id).feedback is None

    valid = feedback.model_copy(update={"evidence_action_ids": [session.actions[0].id]})
    repository.record_feedback(valid)
    with pytest.raises(RecordConflict):
        repository.record_feedback(valid.model_copy(update={"id": uuid4()}))
    assert repository.get(session.id).feedback == valid


def test_actions_follow_sequence_and_stop_after_the_session_finishes(recorded):
    repository, session = recorded["repository"], recorded["sessions"][0]
    gap = Action(id=uuid4(), session_id=session.id, sequence=4, timestamp=STARTED, kind="stop",
                 result="done")
    with pytest.raises(RecordConflict, match="is 3"):
        repository.append_action(gap)
    with pytest.raises(RecordConflict, match="identity"):
        repository.append_action(session.actions[0].model_copy(update={"sequence": 3}))
    with pytest.raises(RecordMissing):
        repository.append_action(gap.model_copy(update={"session_id": uuid4(), "sequence": 1}))

    repository.finish(session.id, status="failed", outcome="application_failure",
                      stop_reason="blocking error")
    with pytest.raises(RecordConflict, match="finished"):
        repository.append_action(gap.model_copy(update={"sequence": 3}))
    with pytest.raises(RecordConflict, match="cannot be replaced"):
        repository.finish(session.id, status="completed", outcome="success", stop_reason=None)
    with pytest.raises(RecordMissing):
        repository.finish(uuid4(), status="completed", outcome="success", stop_reason=None)
    assert repository.get(session.id).outcome == "application_failure"
    assert len(repository.get(session.id).actions) == 2


def test_duplicate_persona_task_attempt_is_a_conflict(recorded):
    repository, session = recorded["repository"], recorded["sessions"][0]
    task_id = uuid4()
    fresh = session.model_copy(update={"id": uuid4(), "actions": []})
    repository.create(fresh, task_id=task_id, attempt=1, provenance={})
    with pytest.raises(RecordConflict):
        repository.create(fresh.model_copy(update={"id": uuid4()}), task_id=task_id, attempt=1,
                          provenance={})
    repository.create(fresh.model_copy(update={"id": uuid4()}), task_id=task_id, attempt=2,
                      provenance={"retry_of": str(fresh.id)})


def test_schema_rejects_screenshot_bytes_in_action_rows(recorded):
    session = recorded["sessions"][0]
    url = recorded["settings"].database_url.get_secret_value()
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(url, sslmode="require") as connection:
            connection.execute(
                "INSERT INTO actions (id, session_id, sequence, occurred_at, payload, artifact_ref) "
                "VALUES (%s, %s, 3, now(), '{}', 'data:image/png;base64,iVBORw0KGgo=')",
                (uuid4(), session.id))
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(url, sslmode="require") as connection:
            connection.execute(
                "INSERT INTO actions (id, session_id, sequence, occurred_at, payload) "
                "VALUES (%s, %s, 3, now(), jsonb_build_object('result', repeat('A', 20000)))",
                (uuid4(), session.id))


def test_analysis_record_round_trip_is_append_only(recorded):
    repository = AnalysisRepository(recorded["database"])
    session, other = recorded["sessions"]
    record = AnalysisRecord(id=uuid4(), experiment_id=recorded["experiment_id"], role="analyst",
                            method="hf_structured_output", prompt_version="analyst-v1",
                            inference={"model": "example/model", "attempts": 1},
                            session_ids=[other.id, session.id],
                            action_ids=[other.actions[0].id, session.actions[1].id],
                            output={"clusters": [{"issue": "unclear error"}]})
    assert repository.save(record) == record.id
    assert repository.save(record) == record.id

    stored = repository.get(record.id)
    assert stored.model_dump(exclude={"session_ids", "action_ids"}) == record.model_dump(
        exclude={"session_ids", "action_ids"})
    assert set(stored.session_ids) == set(record.session_ids)
    assert set(stored.action_ids) == set(record.action_ids)
    assert repository.list_for_experiment(recorded["experiment_id"]) == [stored]
    with pytest.raises(RecordConflict):
        repository.save(record.model_copy(update={"output": {"clusters": []}}))
    assert repository.get(record.id) == stored


def test_analysis_evidence_must_resolve_inside_the_experiment(recorded):
    repository = AnalysisRepository(recorded["database"])
    session, other = recorded["sessions"]
    record = AnalysisRecord(id=uuid4(), experiment_id=recorded["experiment_id"],
                            role="prioritizer", method="deterministic_evidence_grouping",
                            session_ids=[session.id], action_ids=[session.actions[0].id],
                            output={"ranked": []})
    with pytest.raises(RecordInvalid, match="uncited session"):
        repository.save(record.model_copy(update={"action_ids": [other.actions[0].id]}))
    with pytest.raises(RecordInvalid, match="experiment"):
        repository.save(record.model_copy(update={"session_ids": [uuid4()]}))
    with pytest.raises(RecordInvalid, match="experiment"):
        repository.save(record.model_copy(update={"experiment_id": uuid4()}))
    with pytest.raises(RecordMissing):
        repository.save(record.model_copy(update={"job_id": uuid4()}))
    assert repository.list_for_experiment(recorded["experiment_id"]) == []
