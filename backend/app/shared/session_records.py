"""Live session, action and feedback records. B's worker writes them; C's analysis reads them.

Fixture sessions stay in memory and never enter these tables. Actions keep only an
artifact reference; screenshot bytes belong under ARTIFACT_ROOT.
"""

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from backend.app.shared.contracts import Action, Feedback, Session
from backend.app.shared.database import (
    RecordConflict,
    RecordInvalid,
    RecordMissing,
    bound_transaction,
)

ACTIVE = ("queued", "running")
TERMINAL = ("completed", "failed", "cancelled")
OUTCOMES = ("not_run", "success", "application_failure", "infrastructure_failure", "irrelevant")
MAX_ARTIFACT_REF = 512
SESSION_FIELDS = ("id", "experiment_id", "persona_id", "product_version_id", "status", "outcome",
                  "stop_reason", "stream_mode")


def validate_artifact_ref(reference: str | None) -> None:
    """Accept a short ARTIFACT_ROOT-relative path. Reject inline data such as screenshot bytes."""
    if reference is None:
        return
    normalized = reference.replace("\\", "/")
    if (not reference or len(reference) > MAX_ARTIFACT_REF or ":" in reference
            or normalized.startswith("/") or ".." in normalized.split("/")
            or any(not character.isprintable() for character in reference)):
        raise RecordInvalid("Artifact references must be short relative paths under ARTIFACT_ROOT.")


class SessionRepository:
    def __init__(self, database):
        self.database = database

    def create(self, session: Session, *, task_id: UUID, attempt: int,
               provenance: dict[str, Any]) -> None:
        """Record a new queued or running session. Actions and feedback are appended later."""
        if session.status not in ACTIVE or session.outcome != "not_run":
            raise RecordInvalid("A new session must be queued or running with outcome not_run.")
        if session.stream_mode == "fixture":
            raise RecordInvalid("Fixture sessions stay in memory.")
        if session.actions or session.feedback is not None or attempt < 1:
            raise RecordInvalid("Create the session first, then append actions and feedback.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            created = connection.execute(
                "INSERT INTO sessions (id, experiment_id, persona_id, task_id, product_version_id, "
                "attempt, status, outcome, stop_reason, stream_mode, provenance, fixture) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false) "
                "ON CONFLICT DO NOTHING RETURNING id",
                (session.id, session.experiment_id, session.persona_id, task_id,
                 session.product_version_id, attempt, session.status, session.outcome,
                 session.stop_reason, session.stream_mode, Jsonb(provenance))).fetchone()
            if created is None:
                raise RecordConflict("The session identity or persona/task attempt already exists.")

    def append_action(self, action: Action) -> None:
        """Append the next action in sequence to an active session."""
        validate_artifact_ref(action.artifact_ref)
        with self.database.connection() as connection:
            bound_transaction(connection)
            session = connection.execute("SELECT status FROM sessions WHERE id = %s FOR UPDATE",
                                         (action.session_id,)).fetchone()
            if session is None:
                raise RecordMissing("The action's session does not exist.")
            if session[0] not in ACTIVE:
                raise RecordConflict("Actions cannot be added to a finished session.")
            last = connection.execute("SELECT coalesce(max(sequence), 0) FROM actions "
                                      "WHERE session_id = %s", (action.session_id,)).fetchone()[0]
            if action.sequence != last + 1:
                raise RecordConflict(f"The next action sequence for this session is {last + 1}.")
            created = connection.execute(
                "INSERT INTO actions (id, session_id, sequence, occurred_at, payload, artifact_ref) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
                (action.id, action.session_id, action.sequence, action.timestamp,
                 Jsonb({"kind": action.kind, "target": action.target, "result": action.result}),
                 action.artifact_ref)).fetchone()
            if created is None:
                raise RecordConflict("The action identity already exists.")

    def finish(self, session_id: UUID, *, status: str, outcome: str,
               stop_reason: str | None) -> None:
        """Move an active session to a terminal state. A finished session is never replaced."""
        if status not in TERMINAL or outcome not in OUTCOMES:
            raise RecordInvalid("A finished session needs a terminal status and a known outcome.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            updated = connection.execute(
                "UPDATE sessions SET status = %s, outcome = %s, stop_reason = %s, "
                "updated_at = clock_timestamp() WHERE id = %s AND status IN ('queued', 'running') "
                "RETURNING id", (status, outcome, stop_reason, session_id)).fetchone()
            if updated is not None:
                return
            if connection.execute("SELECT 1 FROM sessions WHERE id = %s",
                                  (session_id,)).fetchone() is None:
                raise RecordMissing("The session does not exist.")
            raise RecordConflict("The session already finished; its outcome cannot be replaced.")

    def record_feedback(self, feedback: Feedback) -> None:
        """Store the session's single feedback. Every cited action must belong to that session."""
        cited = set(feedback.evidence_action_ids)
        if not cited:
            raise RecordInvalid("Feedback must cite at least one action from its own session.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            session = connection.execute("SELECT persona_id FROM sessions WHERE id = %s FOR SHARE",
                                         (feedback.session_id,)).fetchone()
            if session is None:
                raise RecordMissing("The feedback's session does not exist.")
            if session[0] != feedback.persona_id:
                raise RecordInvalid("Feedback persona does not match its session.")
            owned = connection.execute(
                "SELECT id FROM actions WHERE session_id = %s AND id = ANY(%s)",
                (feedback.session_id, list(cited))).fetchall()
            if {row[0] for row in owned} != cited:
                raise RecordInvalid("Feedback cites actions that are missing or belong to "
                                    "another session.")
            created = connection.execute(
                "INSERT INTO feedback (id, session_id, payload, synthetic) VALUES (%s, %s, %s, true) "
                "ON CONFLICT DO NOTHING RETURNING id",
                (feedback.id, feedback.session_id,
                 Jsonb(feedback.model_dump(mode="json")))).fetchone()
            if created is None:
                raise RecordConflict("This session or feedback identity already has feedback.")

    def get(self, session_id: UUID) -> Session | None:
        sessions = self._load("s.id = %s", (session_id,))
        return sessions[0] if sessions else None

    def list_for_experiment(self, experiment_id: UUID) -> list[Session]:
        return self._load("s.experiment_id = %s", (experiment_id,))

    def _load(self, condition: str, params: tuple) -> list[Session]:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"SELECT {', '.join(f's.{field}' for field in SESSION_FIELDS)}, "
                    f"f.payload AS feedback FROM sessions s "
                    f"LEFT JOIN feedback f ON f.session_id = s.id "
                    f"WHERE {condition} ORDER BY s.created_at, s.id", params)
                rows = cursor.fetchall()
                cursor.execute(
                    "SELECT id, session_id, sequence, occurred_at, payload, artifact_ref "
                    "FROM actions WHERE session_id = ANY(%s) ORDER BY session_id, sequence",
                    ([row["id"] for row in rows],))
                actions: dict[UUID, list[Action]] = {row["id"]: [] for row in rows}
                try:
                    for action in cursor.fetchall():
                        actions[action["session_id"]].append(Action(
                            id=action["id"], session_id=action["session_id"],
                            sequence=action["sequence"], timestamp=action["occurred_at"],
                            artifact_ref=action["artifact_ref"], **action["payload"]))
                    return [Session(**{field: row[field] for field in SESSION_FIELDS},
                                    actions=actions[row["id"]],
                                    feedback=None if row["feedback"] is None
                                    else Feedback.model_validate(row["feedback"]))
                            for row in rows]
                except (ValidationError, TypeError):
                    raise RecordInvalid("A stored session record no longer matches the "
                                        "shared contract.") from None
