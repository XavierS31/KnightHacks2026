-- Initial persistent pipeline. Apply only to an authorized configured database.
-- Transactional DDL; record checksum in schema_migrations after review.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE product_versions (
    id uuid PRIMARY KEY,
    label text NOT NULL,
    status text NOT NULL CHECK (status IN ('fixture', 'draft', 'validated', 'approved')),
    commit_sha text,
    runtime_url text,
    manifest jsonb NOT NULL,
    fixture boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE experiments (
    id uuid PRIMARY KEY,
    population_id uuid NOT NULL,
    product_version_id uuid NOT NULL REFERENCES product_versions(id),
    task_set_id uuid NOT NULL,
    configuration jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('fixture', 'queued', 'running', 'completed', 'failed', 'cancelled')),
    fixture boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    experiment_id uuid NOT NULL REFERENCES experiments(id),
    persona_id uuid NOT NULL,
    task_id uuid NOT NULL,
    product_version_id uuid NOT NULL REFERENCES product_versions(id),
    attempt integer NOT NULL CHECK (attempt >= 1),
    status text NOT NULL,
    outcome text NOT NULL,
    provenance jsonb NOT NULL,
    fixture boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, persona_id, task_id, attempt)
);

CREATE TABLE actions (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id),
    sequence integer NOT NULL CHECK (sequence >= 1),
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    artifact_ref text,
    UNIQUE (session_id, sequence)
);

CREATE TABLE feedback (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL UNIQUE REFERENCES sessions(id),
    payload jsonb NOT NULL,
    synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id uuid PRIMARY KEY,
    kind text NOT NULL,
    experiment_id uuid REFERENCES experiments(id),
    session_id uuid REFERENCES sessions(id),
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    payload jsonb NOT NULL,
    result jsonb,
    lease_owner text,
    lease_expires_at timestamptz,
    fixture boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL))
);

CREATE INDEX jobs_claimable ON jobs (status, created_at) WHERE status = 'queued';
CREATE INDEX jobs_expired_leases ON jobs (lease_expires_at) WHERE status = 'running';
CREATE INDEX sessions_experiment ON sessions (experiment_id, persona_id);

COMMIT;
