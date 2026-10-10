# Ordered migrations

Developer C owns migration order. `001_initial.sql` establishes product-version, experiment/task-configuration, session-attempt, action, feedback and durable-job provenance. `002_persistence_checks.sql` adds an append-only table for the write/read gate. `003_records_and_job_leases.sql` adds job attempt limits, session lifecycle columns, screenshot-safe action limits and analysis role records. `004_integration_records.sql` adds A's discovery records and the catalog of frozen product versions. 001 to 004 are applied to the Neon `dev` branch (see `docs/status.md`). The `production` branch has no migrations.

## Runner

`python -m backend.migrations.runner` lists each `NNN_name.sql` file and its SHA-256. It makes no database request. Numbers must be contiguous from 001.

`python -m backend.migrations.runner --live` applies the pending files through `NeonDatabase`. It needs `APP_MODE=live` and `DATABASE_URL`. All pending files and their `schema_migrations` rows commit in one transaction. An advisory lock stops concurrent runners. The runner refuses to continue if the recorded history is not an unchanged prefix of the files. A SQL failure rolls back every pending file and reports only the version and SQLSTATE.

Migration files contain no `BEGIN`/`COMMIT`; the runner owns the transaction. Do not edit an applied migration. Add the next numbered file instead.

## Neon write/read gate

Run these steps once against the intended Neon database:

1. Confirm the Neon project and branch. Put `APP_MODE=live` and `DATABASE_URL=<Neon URL>` in the git-ignored `.env`. Do not type the URL in shell history or logs.
2. `python -m backend.migrations.runner` and compare the printed checksums with the reviewed files.
3. `python -m backend.migrations.runner --live`.
4. `python -m backend.migrations.roundtrip --live`.

The round trip checks that the recorded migrations match the files. It then commits one `persistence_checks` row through one pool, closes that pool, and reads the row back through a new pool. Next, it inserts a second row, confirms that the row is visible inside its transaction, and raises inside the `NeonDatabase` scope. It then confirms that the second row is absent. The output reports `Neon host: yes` only for a `*.neon.tech` host. Record the printed output in `docs/status.md`. The durable row stays as evidence.

## Repositories

Repositories run every write in one `NeonDatabase` transaction with statement and lock timeouts. A rejected write raises `RecordMissing`, `RecordConflict` or `RecordInvalid`, and the transaction rolls back, so nothing is stored. Fixture records stay in memory and never enter these tables.

- `backend/app/shared/session_records.py` (`SessionRepository`): B's worker creates a queued or running session, appends actions in strict sequence, records one feedback, and finishes the session. A finished session cannot be replaced or extended. Feedback must cite at least one action, and every cited action must belong to the same session and persona.
- `backend/app/features/evolution/analysis_repository.py` (`AnalysisRepository`): stores one output of the analyst, prioritizer or UX reviewer role. Every cited session must belong to the experiment, and every cited action must belong to a cited session. Records are append-only; an identical retry is accepted.
- No row holds screenshot bytes. `artifact_ref` must be a short relative path under `ARTIFACT_ROOT`. The repository rejects `data:` URIs, absolute paths and `..`. The schema also rejects `data:` references and action payloads over 16 KiB.

## A's discovery records and frozen versions

`004_integration_records.sql` stores the I1 records that were only in memory before:

- `discovery_runs` holds each live run. `discovery_candidates` lists its repositories in rank order.
- `source_snapshots` holds the commit-pinned source text of one candidate of one run.
- `extractions` holds one HF interpretation of a snapshot.
- `proposal_previews` holds one proposal preview. `proposal_preview_extractions` links its extractions in order.

Each table keeps the exact API contract as JSONB. Columns repeat only the identities that other rows reference. `DiscoveryRepository` (`backend/app/features/integration/discovery_repository.py`) checks that each snapshot belongs to a stored candidate, that each extraction has the commit of its snapshot, and that each citation resolves in that snapshot. Reads reject a record that disagrees with its columns. The schema refuses fixture runs.

`VersionRepository` also writes the catalog of a version. `product_version_initial_states` and `product_version_checks` hold the initial states and fixed checks. `product_version_pins` holds the source commits, the implementation file fingerprints and the runtime image ID. Reads reject a catalog that differs from the manifest.

All of these rows are append-only. A trigger refuses `UPDATE` and `DELETE`. A product version is frozen when its status is not `draft`. After that, a trigger refuses any change to the row, so a frozen version identity cannot be rewritten.

After the gate passes, run A's check against Neon:

```sh
python -m backend.app.features.integration.version_repository --live
```

It saves v1, reads it back with exact equality and confirms that the database refuses a rewrite. It needs the local image ID file under `ARTIFACT_ROOT` (see `backend/app/features/integration/product/README.md`).

## Durable jobs

`backend/app/shared/jobs.py` (`JobQueue`) implements the job semantics on the `jobs` table:

- `claim(owner, kinds, lease_seconds)` first recovers expired leases. It then leases the oldest queued job of those kinds with `FOR UPDATE SKIP LOCKED`, so two workers never receive the same job. Each claim adds one to `attempt`.
- A lease is fenced by job, owner and attempt. `heartbeat`, `complete` and `fail` succeed only while the lease is held and unexpired. Otherwise they raise `LeaseLost`, and the worker must stop.
- An expired running job returns to `queued` while attempts remain. Otherwise it becomes `failed`. Both keep `last_error`. `recover_expired()` runs the same recovery without a claim.
- `fail(..., retryable=True)` requeues while attempts remain. `cancel(job_id)` stops queued or running work, and a running worker sees `LeaseLost` on its next heartbeat. Workers heartbeat between actions.

## Tests

Offline tests check file discovery, absent configuration and validation that runs before any connection. Tests that use a real database run only when `TEST_DATABASE_URL` names a disposable TLS PostgreSQL. Each test creates and drops its own schema. They cover the idempotent apply, rejection of an edited migration, full rollback of a failed migration and the round trip. They also cover repository round trips, rejected cross-session evidence with nothing written, concurrent claims, a lease that really expires and is recovered, and the schema checks.

The lazy `NeonDatabase` helper opens no connection in fixture mode or at import time. Its scoped connection commits success and rolls back exceptions through psycopg's pool context. [Psycopg pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)

Matched task/configuration relationships and version promotion are not implemented yet. The repository and job tests pass against a Neon branch (see `docs/status.md`). Use the direct (unpooled) URL for `TEST_DATABASE_URL`, because the pooler rejects the `search_path` startup option.
