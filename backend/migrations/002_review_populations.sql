-- C-owned B lineage storage. Apply after 001 to an authorized database.
BEGIN;

CREATE TABLE review_corpora (
    version text PRIMARY KEY CHECK (version ~ '^[0-9a-f]{64}$'),
    snapshot_json text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE software_reviews (
    id uuid PRIMARY KEY,
    platform text NOT NULL,
    external_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (platform, external_id)
);
CREATE TABLE review_corpus_members (
    corpus_version text NOT NULL REFERENCES review_corpora(version),
    review_id uuid NOT NULL REFERENCES software_reviews(id),
    payload jsonb NOT NULL CHECK (payload->>'kind' = 'source'),
    PRIMARY KEY (corpus_version, review_id)
);
CREATE TABLE behavior_approvals (
    version text PRIMARY KEY CHECK (version ~ '^[0-9a-f]{64}$'),
    corpus_version text NOT NULL REFERENCES review_corpora(version),
    snapshot_json text NOT NULL,
    reviewer_ref text NOT NULL,
    operator_attestation jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (version, corpus_version)
);
CREATE TABLE populations (
    version text PRIMARY KEY CHECK (version ~ '^[0-9a-f]{64}$'),
    id uuid NOT NULL UNIQUE,
    corpus_version text NOT NULL REFERENCES review_corpora(version),
    approval_version text NOT NULL,
    generation_version text NOT NULL,
    configured_count integer NOT NULL CHECK (configured_count BETWEEN 1 AND 500),
    completed_trials integer NOT NULL CHECK (completed_trials = 0),
    snapshot_json text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (approval_version, corpus_version)
        REFERENCES behavior_approvals(version, corpus_version)
);
CREATE TABLE immutable_personas (
    id uuid PRIMARY KEY,
    population_version text NOT NULL REFERENCES populations(version),
    payload jsonb NOT NULL CHECK (payload->'software_behavior'->>'status' = 'review_informed'),
    UNIQUE (id, population_version)
);
CREATE TABLE immutable_scenarios (
    id uuid PRIMARY KEY,
    persona_id uuid NOT NULL REFERENCES immutable_personas(id),
    payload jsonb NOT NULL,
    UNIQUE (id, persona_id)
);
CREATE TABLE immutable_tasks (
    id uuid PRIMARY KEY,
    persona_id uuid NOT NULL REFERENCES immutable_personas(id),
    scenario_id uuid NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (scenario_id, persona_id) REFERENCES immutable_scenarios(id, persona_id)
);

-- Never overwrite a frozen record. Retention deletion remains an administrative action.
CREATE FUNCTION reject_frozen_lineage_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Frozen lineage records cannot be updated';
END;
$$;
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['review_corpora', 'software_reviews',
        'review_corpus_members', 'behavior_approvals', 'populations', 'immutable_personas',
        'immutable_scenarios', 'immutable_tasks']
    LOOP
        EXECUTE format('CREATE TRIGGER frozen_lineage_no_update BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION reject_frozen_lineage_update()', table_name);
    END LOOP;
END;
$$;
COMMIT;
