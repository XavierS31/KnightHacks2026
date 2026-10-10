"""Durable Postgres job queue: claim, lease, heartbeat, expiry recovery and terminal states.

A claim locks one queued row with FOR UPDATE SKIP LOCKED, so two workers never receive the
same job. A lease is fenced by (job, owner, attempt): after expiry and recovery, the old
holder cannot heartbeat, complete or fail the job, even when a worker reuses its name.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.shared.database import RecordInvalid, bound_transaction

MAX_LEASE_SECONDS = 3600
EXPIRED_LEASE_ERROR = "Lease expired before the worker finished."
COLUMNS = ("id, kind, status, attempt, max_attempts, payload, result, last_error, "
           "lease_owner, lease_expires_at, experiment_id, session_id")


class LeaseLost(RuntimeError):
    """The lease expired, was recovered or was cancelled. The worker must stop this job."""


@dataclass(frozen=True)
class JobRecord:
    id: UUID
    kind: str
    status: str
    attempt: int
    max_attempts: int
    payload: dict[str, Any]
    result: dict[str, Any] | None
    last_error: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    experiment_id: UUID | None
    session_id: UUID | None


@dataclass(frozen=True)
class Lease:
    job: JobRecord

    @property
    def expires_at(self) -> datetime:
        return self.job.lease_expires_at


def _lease_seconds(seconds: float) -> float:
    if not 0 < seconds <= MAX_LEASE_SECONDS:
        raise RecordInvalid(f"Lease seconds must be in (0, {MAX_LEASE_SECONDS}].")
    return seconds


def _worker(owner: str) -> str:
    if not owner.strip() or len(owner) > 200:
        raise RecordInvalid("Worker identity must be 1-200 visible characters.")
    return owner


class JobQueue:
    def __init__(self, database):
        self.database = database

    def enqueue(self, kind: str, payload: dict[str, Any], *, experiment_id: UUID | None = None,
                session_id: UUID | None = None, max_attempts: int = 3) -> JobRecord:
        if not kind.strip() or max_attempts < 1:
            raise RecordInvalid("A job needs a kind and at least one allowed attempt.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"INSERT INTO jobs (id, kind, status, payload, max_attempts, experiment_id, "
                    f"session_id) VALUES (%s, %s, 'queued', %s, %s, %s, %s) RETURNING {COLUMNS}",
                    (uuid4(), kind, Jsonb(payload), max_attempts, experiment_id, session_id))
                return JobRecord(**cursor.fetchone())

    def get(self, job_id: UUID) -> JobRecord | None:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(f"SELECT {COLUMNS} FROM jobs WHERE id = %s", (job_id,))
                row = cursor.fetchone()
                return None if row is None else JobRecord(**row)

    @staticmethod
    def _recover(cursor) -> list[JobRecord]:
        cursor.execute(
            f"UPDATE jobs SET status = CASE WHEN attempt < max_attempts THEN 'queued' "
            f"ELSE 'failed' END, last_error = %s, lease_owner = NULL, lease_expires_at = NULL, "
            f"updated_at = clock_timestamp() "
            f"WHERE id IN (SELECT id FROM jobs WHERE status = 'running' "
            f"AND lease_expires_at <= clock_timestamp() FOR UPDATE SKIP LOCKED) "
            f"RETURNING {COLUMNS}", (EXPIRED_LEASE_ERROR,))
        return [JobRecord(**row) for row in cursor.fetchall()]

    def recover_expired(self) -> list[JobRecord]:
        """Requeue expired running jobs that have attempts left; fail the rest."""
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                return self._recover(cursor)

    def claim(self, owner: str, kinds: list[str], lease_seconds: float) -> Lease | None:
        """Recover expired leases, then lease the oldest queued job of the given kinds."""
        owner, lease_seconds = _worker(owner), _lease_seconds(lease_seconds)
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                self._recover(cursor)
                cursor.execute(
                    f"UPDATE jobs SET status = 'running', attempt = attempt + 1, lease_owner = %s, "
                    f"lease_expires_at = clock_timestamp() + make_interval(secs => %s), "
                    f"updated_at = clock_timestamp() "
                    f"WHERE id = (SELECT id FROM jobs WHERE status = 'queued' AND kind = ANY(%s) "
                    f"ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING {COLUMNS}",
                    (owner, lease_seconds, kinds))
                row = cursor.fetchone()
                return None if row is None else Lease(JobRecord(**row))

    def _transition(self, lease: Lease, assignment: str, params: tuple) -> JobRecord:
        job = lease.job
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"UPDATE jobs SET {assignment}, updated_at = clock_timestamp() "
                    f"WHERE id = %s AND status = 'running' AND lease_owner = %s AND attempt = %s "
                    f"AND lease_expires_at > clock_timestamp() RETURNING {COLUMNS}",
                    (*params, job.id, job.lease_owner, job.attempt))
                row = cursor.fetchone()
                if row is None:
                    raise LeaseLost("The lease is no longer held; stop work on this job.")
                return JobRecord(**row)

    def heartbeat(self, lease: Lease, lease_seconds: float) -> Lease:
        """Extend a live lease. Workers call this between actions to detect cancellation."""
        return Lease(self._transition(
            lease, "lease_expires_at = clock_timestamp() + make_interval(secs => %s)",
            (_lease_seconds(lease_seconds),)))

    def complete(self, lease: Lease, result: dict[str, Any]) -> JobRecord:
        return self._transition(
            lease, "status = 'completed', result = %s, last_error = NULL, lease_owner = NULL, "
                   "lease_expires_at = NULL", (Jsonb(result),))

    def fail(self, lease: Lease, error: str, *, retryable: bool) -> JobRecord:
        """Requeue a retryable failure while attempts remain; otherwise fail the job."""
        return self._transition(
            lease, "status = CASE WHEN %s AND attempt < max_attempts THEN 'queued' "
                   "ELSE 'failed' END, last_error = %s, lease_owner = NULL, "
                   "lease_expires_at = NULL", (retryable, error[:500]))

    def cancel(self, job_id: UUID) -> JobRecord | None:
        """Cancel queued or running work. A running worker sees LeaseLost on its next call."""
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"UPDATE jobs SET status = 'cancelled', lease_owner = NULL, "
                    f"lease_expires_at = NULL, updated_at = clock_timestamp() "
                    f"WHERE id = %s AND status IN ('queued', 'running') RETURNING {COLUMNS}",
                    (job_id,))
                row = cursor.fetchone()
                return None if row is None else JobRecord(**row)
