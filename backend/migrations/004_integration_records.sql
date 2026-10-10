-- A's discovery records (I1) and the catalog of frozen product versions.
-- Fixture records stay in memory; these tables hold only live records.
-- Every record here is append-only. Triggers reject UPDATE and DELETE.

CREATE FUNCTION reject_record_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% records are append-only', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

-- A version leaves 'draft' only when it is frozen. After that its identity cannot change.
CREATE FUNCTION reject_frozen_version_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'draft' THEN
        RAISE EXCEPTION 'product version % is frozen', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER product_versions_frozen BEFORE UPDATE OR DELETE ON product_versions
    FOR EACH ROW EXECUTE FUNCTION reject_frozen_version_change();

-- One live discovery run. record holds the exact DiscoveryRun contract.
CREATE TABLE discovery_runs (
    id uuid PRIMARY KEY,
    discovery_mode text NOT NULL CHECK (discovery_mode IN ('popular', 'trending', 'emerging')),
    source_collected_at timestamptz NOT NULL,
    record jsonb NOT NULL CHECK (record->>'mode' = 'live' AND record->>'storage' = 'database'
                                 AND octet_length(record::text) <= 262144),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Each repository candidate of a run, in rank order. Snapshots reference these rows.
CREATE TABLE discovery_candidates (
    run_id uuid NOT NULL REFERENCES discovery_runs(id),
    repository_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 1),
    full_name text NOT NULL,
    PRIMARY KEY (run_id, repository_id),
    UNIQUE (run_id, position)
);

-- Commit-pinned source text of one candidate. record holds the exact SourceSnapshot contract.
CREATE TABLE source_snapshots (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    commit_sha text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    record jsonb NOT NULL CHECK (record->>'storage' = 'database'
                                 AND octet_length(record::text) <= 2097152),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id, repository_id) REFERENCES discovery_candidates (run_id, repository_id)
);

-- One HF interpretation of a snapshot. record holds the exact Extraction contract.
CREATE TABLE extractions (
    id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES source_snapshots(id),
    record jsonb NOT NULL CHECK (record->>'storage' = 'database'
                                 AND octet_length(record::text) <= 131072),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- One HF proposal preview. record holds the exact ProposalPreview contract.
CREATE TABLE proposal_previews (
    id uuid PRIMARY KEY,
    record jsonb NOT NULL CHECK (record->>'storage' = 'database'
                                 AND octet_length(record::text) <= 131072),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proposal_preview_extractions (
    preview_id uuid NOT NULL REFERENCES proposal_previews(id),
    extraction_id uuid NOT NULL REFERENCES extractions(id),
    position integer NOT NULL CHECK (position >= 1),
    PRIMARY KEY (preview_id, extraction_id),
    UNIQUE (preview_id, position)
);

-- The frozen manifest of a version, split into rows that tasks and experiments can reference.
CREATE TABLE product_version_initial_states (
    product_version_id uuid NOT NULL REFERENCES product_versions(id),
    state_id text NOT NULL CHECK (char_length(state_id) BETWEEN 1 AND 200),
    state jsonb NOT NULL,
    PRIMARY KEY (product_version_id, state_id)
);

CREATE TABLE product_version_checks (
    product_version_id uuid NOT NULL,
    check_id text NOT NULL CHECK (char_length(check_id) BETWEEN 1 AND 200),
    initial_state_id text NOT NULL,
    definition jsonb NOT NULL,
    PRIMARY KEY (product_version_id, check_id),
    FOREIGN KEY (product_version_id, initial_state_id)
        REFERENCES product_version_initial_states (product_version_id, state_id)
);

-- Source commits, implementation file fingerprints and the runtime image of a version.
CREATE TABLE product_version_pins (
    product_version_id uuid NOT NULL REFERENCES product_versions(id),
    kind text NOT NULL CHECK (kind IN ('source_commit', 'implementation_sha256', 'image_id')),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 500),
    digest text NOT NULL CHECK (char_length(digest) BETWEEN 1 AND 200),
    PRIMARY KEY (product_version_id, kind, name)
);

CREATE INDEX source_snapshots_candidate ON source_snapshots (run_id, repository_id);
CREATE INDEX extractions_snapshot ON extractions (snapshot_id);
CREATE INDEX proposal_preview_extractions_extraction ON proposal_preview_extractions (extraction_id);
CREATE INDEX product_version_pins_digest ON product_version_pins (kind, digest);

CREATE TRIGGER discovery_runs_append_only BEFORE UPDATE OR DELETE ON discovery_runs
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER discovery_candidates_append_only BEFORE UPDATE OR DELETE ON discovery_candidates
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER source_snapshots_append_only BEFORE UPDATE OR DELETE ON source_snapshots
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER extractions_append_only BEFORE UPDATE OR DELETE ON extractions
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER proposal_previews_append_only BEFORE UPDATE OR DELETE ON proposal_previews
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER proposal_preview_extractions_append_only
    BEFORE UPDATE OR DELETE ON proposal_preview_extractions
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER product_version_initial_states_append_only
    BEFORE UPDATE OR DELETE ON product_version_initial_states
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER product_version_checks_append_only BEFORE UPDATE OR DELETE ON product_version_checks
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
CREATE TRIGGER product_version_pins_append_only BEFORE UPDATE OR DELETE ON product_version_pins
    FOR EACH ROW EXECUTE FUNCTION reject_record_change();
