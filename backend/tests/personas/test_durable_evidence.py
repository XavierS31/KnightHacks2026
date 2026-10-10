"""B's durable sink contract against a fake C repository and local artifact root."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.app.features.personas.durable_evidence import DurableEvidenceSink
from backend.app.features.personas.session_execution import TrialGateError, frame_event
from backend.app.shared.contracts import Action, Feedback, Session

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
       + (1).to_bytes(4, "big") * 2 + b"\x08\x06\x00\x00\x00" + b"test")


class FakeSessionRepository:
    def __init__(self):
        self.created = []
        self.actions = []
        self.feedback = []
        self.finished = []

    def create(self, session, **kwargs):
        self.created.append((session.model_copy(deep=True), kwargs))

    def append_action(self, action):
        self.actions.append(action.model_copy(deep=True))

    def record_feedback(self, feedback):
        self.feedback.append(feedback.model_copy(deep=True))

    def finish(self, identity, **kwargs):
        self.finished.append((identity, kwargs))


def running_session():
    return Session(id=uuid4(), experiment_id=uuid4(), persona_id=uuid4(),
                   product_version_id=uuid4(), status="running", outcome="not_run",
                   actions=[], stream_mode="live")


async def test_live_sink_links_exact_png_action_feedback_and_terminal_record(tmp_path):
    repository = FakeSessionRepository()
    task_id = uuid4()
    guards = []

    async def guard():
        guards.append(True)

    sink = DurableEvidenceSink(repository, task_id=task_id, attempt=2,
                               artifact_root=tmp_path, before_write=guard)
    session = running_session()
    await sink.save_session(session)
    event = frame_event(session, PNG, sequence=2, frame_sequence=1, timestamp=datetime.now(UTC))
    reference = await sink.save_frame(event)
    action = Action(id=uuid4(), session_id=session.id, sequence=1,
                    timestamp=datetime.now(UTC), kind="navigate", target="local-product",
                    result="product_page_loaded", artifact_ref=reference)
    await sink.save_action(action)
    session.actions.append(action)
    await sink.save_session(session)
    session.feedback = Feedback(id=uuid4(), persona_id=session.persona_id,
        session_id=session.id, initial_relevance="medium", post_trial_relevance="high",
        decision="stop", useful_parts=["Inspected sample"], barriers=[],
        suggested_changes=[], evidence_action_ids=[action.id], reason="Fake test feedback")
    session.status, session.outcome, session.stop_reason = "completed", "success", "success"
    await sink.save_session(session)
    await sink.save_session(session)

    assert repository.created[0][1]["task_id"] == task_id
    assert repository.created[0][1]["attempt"] == 2
    assert repository.actions == [action]
    assert repository.feedback == [session.feedback]
    assert repository.finished == [(session.id, {"status": "completed", "outcome": "success",
                                            "stop_reason": "success"})]
    assert len(guards) >= 5
    path = tmp_path / reference
    assert path.read_bytes() == PNG
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["session_id"] == str(session.id)
    assert metadata["captured_at"] == event.payload["captured_at"]
    assert base64.b64decode(event.payload["image_base64"]) == PNG


async def test_live_sink_rejects_foreign_or_changed_evidence(tmp_path):
    sink = DurableEvidenceSink(FakeSessionRepository(), task_id=uuid4(), attempt=1,
                               artifact_root=tmp_path)
    session = running_session()
    await sink.save_session(session)
    foreign = Action(id=uuid4(), session_id=uuid4(), sequence=1,
                     timestamp=datetime.now(UTC), kind="click", result="test")
    with pytest.raises(TrialGateError, match="EVIDENCE_ACTION_SESSION_MISMATCH"):
        await sink.save_action(foreign)
    event = frame_event(session, PNG, sequence=2, frame_sequence=1, timestamp=datetime.now(UTC))
    await sink.save_frame(event)
    changed = event.model_copy(deep=True)
    changed.payload["image_base64"] = base64.b64encode(PNG + b"changed").decode()
    with pytest.raises(TrialGateError, match="CAPTURED_FRAME_CONFLICT"):
        await sink.save_frame(changed)
