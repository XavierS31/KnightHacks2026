# Ordered migrations

Developer C owns migration order. `001_initial.sql` establishes product-version, experiment/task-configuration, session-attempt, action, feedback and durable-job provenance. `002_persistence_checks.sql` adds an append-only table for the write/read gate. Both files are applied to the Neon `dev` branch (see `docs/status.md`). The `production` branch has no migrations yet.

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

## Tests

Offline tests check file discovery. Tests that use a real database run only when `TEST_DATABASE_URL` names a disposable TLS PostgreSQL. Each test creates and drops its own schema. They cover the idempotent apply, rejection of an edited migration, full rollback of a failed migration, and the round trip.

The lazy `NeonDatabase` helper opens no connection in fixture mode or at import time. Its scoped connection commits success and rolls back exceptions through psycopg's pool context. [Psycopg pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)

Before production workers use these tables, add feature-owned schemas and enforce matched task/configuration and feedback-action relationships through repositories. The migrations do not implement job claiming or version promotion. Test a worker lease transition when the job repository exists.
