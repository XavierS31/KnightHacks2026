"""Append-only analysis role records. Every cited session and action must resolve in-experiment."""

import hashlib
import json
from datetime import UTC
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.features.evolution.evidence import validate_session_evidence
from backend.app.features.evolution.models import AnalysisRecord, AnalysisReport
from backend.app.shared.contracts import Session
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


def session_fingerprints(sessions: list[Session]) -> dict[str, str]:
    fingerprints = {}
    for session in sessions:
        actions = []
        for action in sorted(session.actions, key=lambda item: item.sequence):
            if action.timestamp.tzinfo is None:
                raise RecordInvalid("Executed action timestamps must include a timezone.")
            actions.append(action.model_copy(update={
                "timestamp": action.timestamp.astimezone(UTC)}))
        payload = session.model_copy(update={"actions": actions}).model_dump(mode="json")
        fingerprints[str(session.id)] = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return fingerprints


class AnalysisRepository:
    def __init__(self, database):
        self.database = database

    def save_report(self, report: AnalysisReport, sessions: list[Session]) -> UUID | None:
        """Persist the checked report and all role provenance before returning live proposals."""
        if report.mode != "live":
            raise RecordInvalid("Fixture analysis reports stay in memory.")
        evidence = validate_session_evidence(report.experiment_id, sessions, "live")
        if not report.inference_used:
            if report.proposals or report.clusters or report.role_runs:
                raise RecordInvalid("An analysis without inference cannot contain role proposals.")
            return None
        if not evidence.feedback or report.sessions_seen != len(sessions):
            raise RecordInvalid("A live report must describe the evidence it analyzed.")
        if [run.role for run in report.role_runs] not in (
                ["analyst"], ["analyst", "prioritizer"],
                ["analyst", "prioritizer", "ux_reviewer"]):
            raise RecordInvalid("A report requires the ordered E1 engineering roles.")
        payload = {"analysis_report": report.model_dump(mode="json"),
                   "session_fingerprints": session_fingerprints(sessions)}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        last = report.role_runs[-1]
        return self.save(AnalysisRecord(
            id=uuid5(NAMESPACE_URL, f"repofusion:analysis-report:{digest}"),
            experiment_id=report.experiment_id, role=last.role, method=report.method,
            prompt_version=last.prompt_version, inference=last.model_dump(mode="json"),
            session_ids=sorted(evidence.sessions), action_ids=sorted(evidence.actions),
            output=payload))

    def report_for_proposal(self, proposal_id: UUID) -> tuple[AnalysisRecord, AnalysisReport]:
        """Only server-persisted report outputs can supply E2 proposals."""
        records = self._load("r.role = 'ux_reviewer' AND r.method = 'structured_hf_roles' "
                             "AND r.output @> %s", (Jsonb({"analysis_report": {
                                 "proposals": [{"id": str(proposal_id)}]}}),), latest=True)
        if not records:
            raise RecordMissing("No stored E1 analysis contains this improvement proposal.")
        record = records[-1]
        report = AnalysisReport.model_validate(record.output["analysis_report"])
        if (report.mode != "live" or not report.inference_used
                or report.experiment_id != record.experiment_id
                or not report.role_runs or report.role_runs[-1].role != "ux_reviewer"
                or record.inference != report.role_runs[-1].model_dump(mode="json")):
            raise RecordInvalid("Stored analysis provenance disagrees with its report.")
        return record, report

    def validate_report_evidence(self, record: AnalysisRecord, sessions: list[Session]) -> None:
        if (set(record.session_ids) != {session.id for session in sessions}
                or set(record.action_ids) != {action.id for session in sessions
                                             for action in session.actions}
                or record.output.get("session_fingerprints") != session_fingerprints(sessions)):
            raise RecordInvalid("Session evidence changed since E1 analysis; analyze it again.")

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

    def _load(self, condition: str, params: tuple, *, latest: bool = False) -> list[AnalysisRecord]:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                order = (" ORDER BY r.created_at DESC, r.id DESC LIMIT 1" if latest
                         else " ORDER BY r.created_at, r.id")
                cursor.execute(SELECT_RECORDS + f"WHERE {condition}" + order, params)
                return [AnalysisRecord(**row) for row in cursor.fetchall()]
