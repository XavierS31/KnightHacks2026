"""Append-only analysis role records. Every cited session and action must resolve in-experiment."""

from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.features.evolution.models import AnalysisRecord
from backend.app.shared.database import (
    RecordConflict,
    RecordInvalid,
    RecordMissing,
    bound_transaction,
)

SELECT_RECORDS = (
    "SELECT r.id, r.experiment_id, r.job_id, r.role, r.method, r.prompt_version, r.inference, "
    "r.output, "
    "ARRAY(SELECT session_id FROM analysis_record_sessions WHERE analysis_id = r.id "
    "ORDER BY session_id) AS session_ids, "
    "ARRAY(SELECT action_id FROM analysis_record_actions WHERE analysis_id = r.id "
    "ORDER BY action_id) AS action_ids "
    "FROM analysis_records r ")


def _canonical(record: AnalysisRecord) -> AnalysisRecord:
    """Evidence order carries no meaning, so stored and compared records use sorted IDs."""
    return record.model_copy(update={"session_ids": sorted(set(record.session_ids)),
                                     "action_ids": sorted(set(record.action_ids))})


class AnalysisRepository:
    def __init__(self, database):
        self.database = database

    def save(self, record: AnalysisRecord) -> UUID:
        """Store a role output once. An identical retry is accepted; a different one conflicts."""
        record = _canonical(record)
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id FROM sessions WHERE experiment_id = %s AND id = ANY(%s) "
                               "FOR SHARE", (record.experiment_id, record.session_ids))
                if {row["id"] for row in cursor.fetchall()} != set(record.session_ids):
                    raise RecordInvalid("Cited sessions are missing or belong to another "
                                        "experiment.")
                cursor.execute("SELECT id FROM actions WHERE session_id = ANY(%s) AND id = ANY(%s)",
                               (record.session_ids, record.action_ids))
                if {row["id"] for row in cursor.fetchall()} != set(record.action_ids):
                    raise RecordInvalid("Cited actions are missing or belong to an uncited session.")
                if record.job_id is not None:
                    cursor.execute("SELECT 1 FROM jobs WHERE id = %s", (record.job_id,))
                    if cursor.fetchone() is None:
                        raise RecordMissing("The analysis job does not exist.")
                cursor.execute(
                    "INSERT INTO analysis_records (id, experiment_id, job_id, role, method, "
                    "prompt_version, inference, output) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING RETURNING id",
                    (record.id, record.experiment_id, record.job_id, record.role, record.method,
                     record.prompt_version,
                     None if record.inference is None else Jsonb(record.inference),
                     Jsonb(record.output)))
                if cursor.fetchone() is None:
                    cursor.execute(SELECT_RECORDS + "WHERE r.id = %s", (record.id,))
                    if AnalysisRecord(**cursor.fetchone()) != record:
                        raise RecordConflict("This analysis identity already holds a different "
                                             "record; no rewrite occurred.")
                    return record.id
                cursor.executemany("INSERT INTO analysis_record_sessions (analysis_id, session_id) "
                                   "VALUES (%s, %s)",
                                   [(record.id, session_id) for session_id in record.session_ids])
                cursor.executemany("INSERT INTO analysis_record_actions (analysis_id, action_id) "
                                   "VALUES (%s, %s)",
                                   [(record.id, action_id) for action_id in record.action_ids])
        return record.id

    def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        records = self._load("r.id = %s", (analysis_id,))
        return records[0] if records else None

    def list_for_experiment(self, experiment_id: UUID) -> list[AnalysisRecord]:
        return self._load("r.experiment_id = %s", (experiment_id,))

    def _load(self, condition: str, params: tuple) -> list[AnalysisRecord]:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(SELECT_RECORDS + f"WHERE {condition} ORDER BY r.created_at, r.id",
                               params)
                return [AnalysisRecord(**row) for row in cursor.fetchall()]
