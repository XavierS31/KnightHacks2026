-- Append-only write/read evidence for the Neon gate (backend.migrations.roundtrip).
CREATE TABLE persistence_checks (
    id uuid PRIMARY KEY,
    label text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
