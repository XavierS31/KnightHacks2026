# Ordered migrations

Developer C owns migration order. `001_initial.sql` establishes product-version, experiment/task-configuration, session-attempt, action, feedback and durable-job provenance. It has not been run against Neon and is not a completed persistence integration.

Before applying: verify the intended database/branch, review the SQL, record the file's SHA-256, and run once in a configured authorized environment. Keep credentials outside shell history/logs. Record version/checksum in `schema_migrations` as part of the deployment procedure. Do not replay `CREATE TABLE` migrations or edit an already applied migration; introduce the next numbered migration.

The lazy `NeonDatabase` helper opens no connection in fixture mode or at import time. Its scoped connection commits success and rolls back exceptions through psycopg's pool context. [Psycopg pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)

Before production workers use these tables, add feature-owned schemas and enforce matched task/configuration and feedback-action relationships through repositories. The initial SQL does not implement job claiming, version promotion, full feature persistence or a migration runner. Test a real rollback, write/read and worker lease transition when connection access is available.
