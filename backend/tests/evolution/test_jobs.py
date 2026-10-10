import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from backend.app.shared.database import DatabaseUnavailable, NeonDatabase, RecordInvalid
from backend.app.shared.jobs import EXPIRED_LEASE_ERROR, JobQueue, LeaseLost
from backend.app.shared.settings import Settings


@pytest.mark.parametrize("mode,url", [("fixture", "postgresql://fixture:secret@invalid/test"),
                                      ("live", "")])
def test_absent_configuration_makes_no_connection(mode, url):
    settings = Settings(_env_file=None, app_mode=mode, database_url=SecretStr(url))
    queue = JobQueue(NeonDatabase(settings))
    with pytest.raises(DatabaseUnavailable) as error:
        queue.enqueue("browser_session", {"persona": 1})
    assert "secret" not in str(error.value)
    with pytest.raises(DatabaseUnavailable):
        queue.claim("worker-1", ["browser_session"], 30)


@pytest.mark.parametrize("owner,seconds", [("worker-1", 0), ("worker-1", 3601), (" ", 30)])
def test_invalid_lease_requests_fail_before_any_connection(owner, seconds):
    settings = Settings(_env_file=None, app_mode="fixture")
    with pytest.raises(RecordInvalid):
        JobQueue(NeonDatabase(settings)).claim(owner, ["browser_session"], seconds)


def test_claim_lease_and_complete(migrated):
    queue = JobQueue(migrated["database"])
    queued = queue.enqueue("browser_session", {"persona": 1},
                           experiment_id=migrated["experiment_id"])
    assert (queued.status, queued.attempt, queued.lease_owner) == ("queued", 0, None)

    lease = queue.claim("worker-1", ["browser_session"], 30)
    assert lease.job.id == queued.id
    assert (lease.job.status, lease.job.attempt, lease.job.lease_owner) == ("running", 1, "worker-1")
    assert queue.claim("worker-2", ["browser_session"], 30) is None

    extended = queue.heartbeat(lease, 60)
    assert extended.expires_at > lease.expires_at
    done = queue.complete(extended, {"session": "recorded"})
    assert (done.status, done.result, done.lease_owner, done.lease_expires_at) == (
        "completed", {"session": "recorded"}, None, None)
    with pytest.raises(LeaseLost):
        queue.complete(extended, {"session": "replaced"})
    assert queue.get(queued.id).result == {"session": "recorded"}


def test_claim_filters_by_kind_and_takes_oldest_first(migrated):
    queue = JobQueue(migrated["database"])
    first = queue.enqueue("browser_session", {"n": 1})
    queue.enqueue("analysis", {"n": 2})
    third = queue.enqueue("browser_session", {"n": 3})
    assert queue.claim("worker-1", ["browser_session"], 30).job.id == first.id
    assert queue.claim("worker-1", ["browser_session"], 30).job.id == third.id
    assert queue.claim("worker-1", ["browser_session"], 30) is None


def test_two_workers_cannot_claim_the_same_job_concurrently(migrated):
    settings = migrated["settings"]
    queues = [JobQueue(NeonDatabase(settings)) for _ in range(4)]
    job_ids = {queues[0].enqueue("browser_session", {"n": n}).id for n in range(5)}
    try:
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(queues[n % 4].claim, f"worker-{n}", ["browser_session"], 30)
                       for n in range(24)]
            leases = [future.result() for future in futures]
    finally:
        for queue in queues:
            queue.database.close()
    claimed = [lease.job.id for lease in leases if lease is not None]
    assert len(claimed) == 5 and set(claimed) == job_ids
    assert sum(lease is None for lease in leases) == 19


def test_a_row_locked_by_another_transaction_is_skipped(migrated):
    queue = JobQueue(migrated["database"])
    locked = queue.enqueue("browser_session", {"n": 1})
    free = queue.enqueue("browser_session", {"n": 2})
    with psycopg.connect(migrated["settings"].database_url.get_secret_value(),
                         sslmode="require") as other:
        other.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (locked.id,))
        assert queue.claim("worker-1", ["browser_session"], 30).job.id == free.id
        assert queue.claim("worker-2", ["browser_session"], 30) is None
    assert queue.claim("worker-2", ["browser_session"], 30).job.id == locked.id


def test_expired_lease_is_recovered_and_the_old_holder_is_fenced_out(migrated):
    queue = JobQueue(migrated["database"])
    job = queue.enqueue("browser_session", {"persona": 1})
    stale = queue.claim("worker-1", ["browser_session"], 0.5)
    time.sleep(1)

    with pytest.raises(LeaseLost):
        queue.heartbeat(stale, 30)
    recovered = queue.claim("worker-1", ["browser_session"], 30)
    assert recovered.job.id == job.id
    assert (recovered.job.attempt, recovered.job.last_error) == (2, EXPIRED_LEASE_ERROR)
    with pytest.raises(LeaseLost):
        queue.complete(stale, {"from": "stale holder"})
    assert queue.complete(recovered, {"from": "attempt 2"}).result == {"from": "attempt 2"}


def test_expired_lease_without_attempts_left_fails_visibly(migrated):
    queue = JobQueue(migrated["database"])
    job = queue.enqueue("browser_session", {"persona": 1}, max_attempts=1)
    queue.claim("worker-1", ["browser_session"], 0.5)
    time.sleep(1)
    recovered = queue.recover_expired()
    assert [(item.id, item.status, item.attempt) for item in recovered] == [(job.id, "failed", 1)]
    assert queue.get(job.id).last_error == EXPIRED_LEASE_ERROR
    assert queue.claim("worker-2", ["browser_session"], 30) is None


def test_failure_requeues_only_while_retryable_attempts_remain(migrated):
    queue = JobQueue(migrated["database"])
    job = queue.enqueue("browser_session", {"persona": 1}, max_attempts=2)
    retried = queue.fail(queue.claim("worker-1", ["browser_session"], 30), "timeout",
                         retryable=True)
    assert (retried.status, retried.attempt, retried.last_error) == ("queued", 1, "timeout")
    exhausted = queue.fail(queue.claim("worker-1", ["browser_session"], 30), "timeout",
                           retryable=True)
    assert (exhausted.status, exhausted.attempt) == ("failed", 2)

    other = queue.enqueue("browser_session", {"persona": 2}, max_attempts=3)
    final = queue.fail(queue.claim("worker-1", ["browser_session"], 30), "invalid target",
                       retryable=False)
    assert (final.id, final.status) == (other.id, "failed")
    assert queue.get(job.id).status == "failed"


def test_cancel_stops_the_running_worker_at_its_next_heartbeat(migrated):
    queue = JobQueue(migrated["database"])
    job = queue.enqueue("browser_session", {"persona": 1})
    lease = queue.claim("worker-1", ["browser_session"], 30)
    assert queue.cancel(job.id).status == "cancelled"
    with pytest.raises(LeaseLost):
        queue.heartbeat(lease, 30)
    assert queue.cancel(job.id) is None
    assert queue.cancel(uuid4()) is None


def test_running_rows_require_a_lease_in_the_schema(migrated):
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(migrated["settings"].database_url.get_secret_value(),
                             sslmode="require") as connection:
            connection.execute("INSERT INTO jobs (id, kind, status, payload) "
                               "VALUES (%s, 'browser_session', 'running', '{}')", (uuid4(),))
