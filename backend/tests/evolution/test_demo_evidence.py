from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from backend.app.features.evolution.demo_evidence import (
    database_snapshot,
    fixture_analysis_check,
    live_checks,
    neon_host,
    neon_usage_check,
    replay_label_check,
    v1_source_check,
    versions_check,
)
from backend.app.features.integration.product.freeze import implementation_hashes
from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
from backend.app.shared.database import NeonDatabase
from backend.app.shared.fixtures import EXPERIMENT, SESSIONS
from backend.app.shared.settings import Settings

HANDOFF = ProductHandoff.model_validate_json(MANIFEST.read_text())


def test_frozen_v1_sources_match_the_working_tree():
    check = v1_source_check(HANDOFF, implementation_hashes())
    assert check.status == "pass"
    assert check.facts["label"] == "SourceTable v1"
    assert check.facts["commit_sha"] == HANDOFF.version.commit_sha


def test_changed_missing_or_added_v1_sources_fail():
    current = dict(HANDOFF.implementation_hashes)
    changed, removed = sorted(current)[:2]
    current[changed] = "0" * 64
    del current[removed]
    current["frontend/src/features/integration/product/extra.js"] = "1" * 64
    check = v1_source_check(HANDOFF, current)
    assert check.status == "fail"
    assert check.facts["drifted"] == [changed]
    assert check.facts["missing"] == [removed]
    assert check.facts["added"] == ["frontend/src/features/integration/product/extra.js"]


def test_unvalidated_v1_manifest_fails():
    draft = HANDOFF.model_copy(update={"version": HANDOFF.version.model_copy(update={"status": "draft"})})
    assert v1_source_check(draft, implementation_hashes()).status == "fail"


def test_fixture_analysis_is_labeled_and_claims_nothing():
    check = fixture_analysis_check(EXPERIMENT.id, SESSIONS)
    assert check.status == "pass"
    assert check.facts == {"mode": "fixture", "method": "deterministic_evidence_grouping",
                           "inference_used": False, "sessions_seen": len(SESSIONS),
                           "feedback_present": 0, "clusters": 0}


def test_fixture_sessions_from_another_experiment_fail():
    check = fixture_analysis_check(uuid4(), SESSIONS)
    assert check.status == "fail"


@pytest.mark.parametrize("mode, url", [("fixture", "postgresql://u:secret@127.0.0.1:1/db"),
                                       ("live", "")])
def test_live_checks_without_configuration_attempt_no_connection(mode, url):
    settings = Settings(_env_file=None, app_mode=mode, database_url=SecretStr(url))
    database = NeonDatabase(settings)
    checks = live_checks(settings, database, HANDOFF)
    assert [check.name for check in checks] == ["neon_usage", "v1_registered", "v2_registered",
                                                "replay_labeled"]
    assert {check.status for check in checks} == {"not_established"}
    assert database._pool is None


def test_unreachable_database_fails_without_leaking_the_url():
    settings = Settings(_env_file=None, app_mode="live",
                        database_url=SecretStr("postgresql://u:secret-value@127.0.0.1:1/db"))
    database = NeonDatabase(settings)
    checks = live_checks(settings, database, HANDOFF)
    database.close()
    assert {check.status for check in checks} == {"fail"}
    assert all("secret-value" not in check.model_dump_json() for check in checks)


@pytest.mark.parametrize("url, expected", [
    ("postgresql://u:p@ep-quiet-sun-123.us-east-2.aws.neon.tech/app?sslmode=require", True),
    ("host=ep-quiet-sun-123-pooler.us-east-2.aws.neon.tech dbname=app", True),
    ("postgresql://u:p@neon.tech.example.com/app", False),
    ("postgresql://u:p@notneon.tech/app", False),
    ("postgresql://u:p@127.0.0.1:5432/app", False),
    ("not a url ===", False),
])
def test_only_neon_tech_hosts_count_as_neon(url, expected):
    assert neon_host(Settings(_env_file=None, database_url=SecretStr(url))) is expected


@pytest.fixture
def stored_pipeline(migrated_settings):
    """A migrated schema holding the frozen v1, an approved v2 and two labeled sessions."""
    url = migrated_settings.database_url.get_secret_value()
    v2_id, experiment_id = uuid4(), uuid4()
    sessions = [(uuid4(), "live"), (uuid4(), "replay")]
    with psycopg.connect(url, sslmode="require", autocommit=True) as connection:
        connection.execute("INSERT INTO schema_migrations (version, checksum) VALUES ('001', %s)",
                           ("a" * 64,))
        connection.execute(
            "INSERT INTO product_versions (id, label, status, commit_sha, manifest) "
            "VALUES (%s, %s, 'validated', %s, %s), (%s, 'SourceTable v2', 'approved', %s, %s)",
            (HANDOFF.version.id, HANDOFF.version.label, HANDOFF.version.commit_sha, Jsonb({}),
             v2_id, "b" * 40, Jsonb({})))
        connection.execute(
            "INSERT INTO experiments (id, population_id, product_version_id, task_set_id, "
            "configuration, status) VALUES (%s, %s, %s, %s, %s, 'completed')",
            (experiment_id, uuid4(), HANDOFF.version.id, uuid4(), Jsonb({})))
        for session_id, stream_mode in sessions:
            connection.execute(
                "INSERT INTO sessions (id, experiment_id, persona_id, task_id, product_version_id, "
                "attempt, status, outcome, provenance) "
                "VALUES (%s, %s, %s, %s, %s, 1, 'completed', 'success', %s)",
                (session_id, experiment_id, uuid4(), uuid4(), HANDOFF.version.id,
                 Jsonb({"stream_mode": stream_mode, "stop_reason": "task ended"})))
            connection.execute(
                "INSERT INTO actions (id, session_id, sequence, occurred_at, payload) "
                "VALUES (%s, %s, 1, now(), %s)",
                (uuid4(), session_id, Jsonb({"kind": "click", "result": "Recorded"})))
        connection.execute("INSERT INTO feedback (id, session_id, payload) VALUES (%s, %s, %s)",
                           (uuid4(), sessions[0][0], Jsonb({})))
    return {"url": url, "v2_id": v2_id, "experiment_id": experiment_id}


def test_stored_pipeline_off_a_neon_host_is_not_neon_evidence(stored_pipeline, migrated_settings):
    database = NeonDatabase(migrated_settings)
    checks = {check.name: check for check in live_checks(migrated_settings, database, HANDOFF)}
    snapshot = database_snapshot(database)
    database.close()
    assert checks["neon_usage"].facts["neon_host"] is neon_host(migrated_settings)
    assert checks["v1_registered"].status == "pass"
    assert checks["v2_registered"].status == "pass"
    assert checks["replay_labeled"].status == "pass"
    check = neon_usage_check(snapshot, on_neon_host=False)
    assert check.status == "fail"
    assert check.facts["neon_host"] is False


def test_stored_pipeline_on_a_neon_host_is_usage_evidence(stored_pipeline, migrated_settings):
    database = NeonDatabase(migrated_settings)
    snapshot = database_snapshot(database)
    database.close()
    check = neon_usage_check(snapshot, on_neon_host=True)
    assert check.status == "pass"
    assert check.facts["migrations"][0]["version"] == "001"
    assert check.facts["rows"]["sessions"] == {"total": 2, "fixture": 0}
    assert check.facts["rows"]["actions"] == {"total": 2, "fixture": 0}
    assert check.facts["rows"]["feedback"] == {"total": 1, "fixture": 0}
    assert check.detail == "Neon holds 2 non-fixture sessions, 2 actions and 1 feedback records."
    assert migrated_settings.database_url.get_secret_value() not in check.model_dump_json()


def test_migrated_schema_without_pipeline_rows_is_not_established(migrated_settings):
    url = migrated_settings.database_url.get_secret_value()
    database = NeonDatabase(migrated_settings)
    unrecorded = neon_usage_check(database_snapshot(database), on_neon_host=True)
    with psycopg.connect(url, sslmode="require", autocommit=True) as connection:
        connection.execute("INSERT INTO schema_migrations (version, checksum) VALUES ('001', %s)",
                           ("a" * 64,))
    snapshot = database_snapshot(database)
    database.close()
    assert unrecorded.status == "fail"
    assert neon_usage_check(snapshot, on_neon_host=True).status == "not_established"
    assert [check.status for check in versions_check(snapshot, HANDOFF)] == [
        "not_established", "not_established"]
    assert replay_label_check(snapshot).status == "not_established"


def test_changed_v1_row_fails_and_blocks_v2(stored_pipeline, migrated_settings):
    with psycopg.connect(stored_pipeline["url"], sslmode="require", autocommit=True) as connection:
        connection.execute("UPDATE product_versions SET commit_sha = %s WHERE id = %s",
                           ("c" * 40, HANDOFF.version.id))
    database = NeonDatabase(migrated_settings)
    snapshot = database_snapshot(database)
    database.close()
    v1, v2 = versions_check(snapshot, HANDOFF)
    assert v1.status == "fail"
    assert v2.status == "fail"
    assert v2.facts["approved"][0]["id"] == str(stored_pipeline["v2_id"])


@pytest.mark.parametrize("provenance, fixture, unlabeled, mislabeled", [
    ({"stop_reason": "task ended"}, False, 1, 0),
    ({"stream_mode": "streaming"}, False, 1, 0),
    ({"stream_mode": "fixture"}, False, 0, 1),
    ({"stream_mode": "live"}, True, 0, 1),
])
def test_unlabeled_or_mislabeled_sessions_fail(stored_pipeline, migrated_settings, provenance, fixture,
                                               unlabeled, mislabeled):
    with psycopg.connect(stored_pipeline["url"], sslmode="require", autocommit=True) as connection:
        connection.execute(
            "INSERT INTO sessions (id, experiment_id, persona_id, task_id, product_version_id, "
            "attempt, status, outcome, provenance, fixture) "
            "VALUES (%s, %s, %s, %s, %s, 1, 'completed', 'success', %s, %s)",
            (uuid4(), stored_pipeline["experiment_id"], uuid4(), uuid4(), HANDOFF.version.id,
             Jsonb(provenance), fixture))
    database = NeonDatabase(migrated_settings)
    snapshot = database_snapshot(database)
    database.close()
    check = replay_label_check(snapshot)
    assert check.status == "fail"
    assert check.detail == (f"{unlabeled} stored sessions have no valid stream label and "
                            f"{mislabeled} disagree with their fixture flag.")
