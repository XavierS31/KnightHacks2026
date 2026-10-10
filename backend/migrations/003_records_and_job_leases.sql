-- Repository constraints for sessions/actions/feedback, analysis role records and job leases.
-- Fixture records stay in memory; these tables hold only live records.

ALTER TABLE jobs
    ADD COLUMN max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    ADD COLUMN last_error text CHECK (char_length(last_error) <= 500),
    ADD CHECK (attempt <= max_attempts),
    ADD CHECK (octet_length(payload::text) <= 65536),
    ADD CHECK (result IS NULL OR octet_length(result::text) <= 65536);

ALTER TABLE sessions
    ADD COLUMN stop_reason text,
    ADD COLUMN stream_mode text NOT NULL DEFAULT 'unavailable'
        CHECK (stream_mode IN ('unavailable', 'live', 'replay')),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
    ADD CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    ADD CHECK (outcome IN ('not_run', 'success', 'application_failure',
                           'infrastructure_failure', 'irrelevant'));

-- Screenshot bytes live under ARTIFACT_ROOT. A row keeps only a short reference.
ALTER TABLE actions
    ADD CHECK (artifact_ref IS NULL OR (char_length(artifact_ref) BETWEEN 1 AND 512
                                        AND artifact_ref !~* '^data:')),
    ADD CHECK (octet_length(payload::text) <= 16384);

CREATE INDEX actions_session ON actions (session_id, sequence);

-- One validated output of a read-only engineering role, with its exact evidence.
CREATE TABLE analysis_records (
    id uuid PRIMARY KEY,
    experiment_id uuid NOT NULL REFERENCES experiments(id),
    job_id uuid REFERENCES jobs(id),
    role text NOT NULL CHECK (role IN ('analyst', 'prioritizer', 'ux_reviewer')),
    method text NOT NULL CHECK (char_length(method) >= 1),
    prompt_version text,
    inference jsonb,
    output jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analysis_record_sessions (
    analysis_id uuid NOT NULL REFERENCES analysis_records(id),
    session_id uuid NOT NULL REFERENCES sessions(id),
    PRIMARY KEY (analysis_id, session_id)
);

CREATE TABLE analysis_record_actions (
    analysis_id uuid NOT NULL REFERENCES analysis_records(id),
    action_id uuid NOT NULL REFERENCES actions(id),
    PRIMARY KEY (analysis_id, action_id)
);

CREATE INDEX analysis_records_experiment ON analysis_records (experiment_id, created_at);
