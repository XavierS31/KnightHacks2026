"""Read one experiment's persisted sessions, actions and feedback from the 001 tables.

Stored row convention (writers in the persistence tasks must follow it):
- sessions.provenance holds {"stream_mode": ..., "stop_reason": ...}.
- actions.payload holds {"kind": ..., "target": ..., "result": ...}; occurred_at is the timestamp.
- feedback.payload holds the full Feedback contract; its id and session_id must equal the columns.
"""

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from pydantic import ValidationError

from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.shared.contracts import Action, Feedback, Session
from backend.app.shared.database import NeonDatabase


class ExperimentNotFound(LookupError):
    """No persisted experiment has this identity."""


def assemble_sessions(experiment: dict[str, Any], session_rows: list[dict[str, Any]],
                      action_rows: list[dict[str, Any]],
                      feedback_rows: list[dict[str, Any]]) -> list[Session]:
    """Rebuild contract sessions; disagreeing or orphaned rows are rejected, never repaired."""
    if experiment["fixture"] or any(row["fixture"] for row in session_rows):
        raise EvidenceMismatch("Persisted fixture records cannot become live evidence.")
    known = {row["id"] for row in session_rows}
    if (any(row["experiment_id"] != experiment["id"] for row in session_rows)
            or any(row["session_id"] not in known for row in action_rows + feedback_rows)):
        raise EvidenceMismatch("Persisted records reference a session outside the experiment.")
    try:
        actions: dict[UUID, list[Action]] = {identity: [] for identity in known}
        for row in action_rows:
            payload = row["payload"]
            actions[row["session_id"]].append(Action(
                id=row["id"], session_id=row["session_id"], sequence=row["sequence"],
                timestamp=row["occurred_at"], kind=payload["kind"], target=payload.get("target"),
                result=payload["result"], artifact_ref=row["artifact_ref"]))
        feedback: dict[UUID, Feedback] = {}
        for row in feedback_rows:
            item = Feedback.model_validate(row["payload"])
            if item.id != row["id"] or item.session_id != row["session_id"]:
                raise EvidenceMismatch("Stored feedback payload disagrees with its row.")
            feedback[row["session_id"]] = item
        return [Session(
            id=row["id"], experiment_id=row["experiment_id"], persona_id=row["persona_id"],
            product_version_id=row["product_version_id"], status=row["status"],
            outcome=row["outcome"], stop_reason=row["provenance"].get("stop_reason"),
            stream_mode=row["provenance"]["stream_mode"],
            actions=sorted(actions[row["id"]], key=lambda action: action.sequence),
            feedback=feedback.get(row["id"]),
        ) for row in session_rows]
    except (ValidationError, KeyError, TypeError, AttributeError):
        raise EvidenceMismatch("A persisted record does not match the session contract.") from None


class SessionEvidenceRepository:
    def __init__(self, database: NeonDatabase):
        self.database = database

    def load(self, experiment_id: UUID) -> list[Session]:
        """Read every record in one read-only snapshot so evidence cannot shift mid-analysis."""
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute("SELECT id, fixture FROM experiments WHERE id = %s", (experiment_id,))
                experiment = cursor.fetchone()
                if experiment is None:
                    raise ExperimentNotFound("No persisted experiment has this ID.")
                cursor.execute(
                    "SELECT id, experiment_id, persona_id, product_version_id, status, outcome, "
                    "provenance, fixture FROM sessions WHERE experiment_id = %s "
                    "ORDER BY created_at, id", (experiment_id,))
                sessions = cursor.fetchall()
                cursor.execute(
                    "SELECT a.id, a.session_id, a.sequence, a.occurred_at, a.payload, a.artifact_ref "
                    "FROM actions a JOIN sessions s ON s.id = a.session_id "
                    "WHERE s.experiment_id = %s ORDER BY a.session_id, a.sequence", (experiment_id,))
                actions = cursor.fetchall()
                cursor.execute(
                    "SELECT f.id, f.session_id, f.payload FROM feedback f "
                    "JOIN sessions s ON s.id = f.session_id WHERE s.experiment_id = %s",
                    (experiment_id,))
                feedback = cursor.fetchall()
        return assemble_sessions(experiment, sessions, actions, feedback)
