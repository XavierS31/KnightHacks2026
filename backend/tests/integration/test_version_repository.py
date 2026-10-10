from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from backend.app.features.integration.version_repository import (
    VersionConflict,
    VersionRecordInvalid,
    VersionRepository,
    rewrite_rejected,
)
from backend.app.shared.database import NeonDatabase
from backend.app.shared.settings import Settings
from backend.tests.prototype_fixtures import handoff


@pytest.fixture
def frozen():
    return handoff()


@pytest.fixture
def admin(isolated):
    """A direct connection to the test schema that bypasses the repository."""
    settings, _ = isolated
    with psycopg.connect(settings.database_url.get_secret_value(), sslmode="require",
                         autocommit=True) as connection:
        yield connection


def test_save_is_idempotent_and_reads_back_with_exact_equality(database, admin, frozen):
    repository = VersionRepository(database)
    assert repository.save(frozen) == frozen.version.id
    assert repository.save(frozen) == frozen.version.id
    observed = repository.get(frozen.version.id)
    assert observed.model_dump(mode="json") == frozen.model_dump(mode="json")
    assert admin.execute("SELECT check_id, initial_state_id FROM product_version_checks "
                         "ORDER BY check_id").fetchall() == sorted(
        (check.id, check.initial_state) for check in frozen.checks)
    pins = dict(((kind, name), digest) for kind, name, digest in admin.execute(
        "SELECT kind, name, digest FROM product_version_pins").fetchall())
    assert pins[("image_id", "runtime")] == frozen.image_id
    assert {name: digest for (kind, name), digest in pins.items()
            if kind == "source_commit"} == frozen.source_commits
    assert {name: digest for (kind, name), digest in pins.items()
            if kind == "implementation_sha256"} == frozen.implementation_hashes


def test_different_manifest_under_frozen_identity_conflicts_without_rewrite(database, frozen):
    repository = VersionRepository(database)
    repository.save(frozen)
    changed = frozen.model_copy(deep=True)
    changed.limitations.append("Changed manifest")
    with pytest.raises(VersionConflict):
        repository.save(changed)
    assert repository.get(frozen.version.id) == frozen


@pytest.mark.parametrize("statement", [
    "UPDATE product_versions SET label = 'Synthetic prototype v1 rewrite'",
    "UPDATE product_versions SET manifest = '{}'",
    "DELETE FROM product_versions",
    "UPDATE product_version_checks SET definition = '{}'",
    "DELETE FROM product_version_initial_states",
    "UPDATE product_version_pins SET digest = 'rewritten'",
])
def test_database_refuses_to_rewrite_a_frozen_version(database, admin, frozen, statement):
    VersionRepository(database).save(frozen)
    with pytest.raises(psycopg.errors.RestrictViolation):
        admin.execute(statement)
    assert VersionRepository(database).get(frozen.version.id) == frozen


def test_rewrite_check_reports_refusal_and_changes_nothing(database, frozen):
    VersionRepository(database).save(frozen)
    assert rewrite_rejected(database, frozen.version.id) is True
    assert rewrite_rejected(database, uuid4()) is False
    assert VersionRepository(database).get(frozen.version.id) == frozen


def test_draft_versions_stay_editable(database, admin):
    identity = uuid4()
    admin.execute("INSERT INTO product_versions (id, label, status, manifest) "
                  "VALUES (%s, 'v2 draft', 'draft', '{}')", (identity,))
    admin.execute("UPDATE product_versions SET label = 'v2 draft edited' WHERE id = %s", (identity,))
    assert admin.execute("SELECT label FROM product_versions WHERE id = %s",
                         (identity,)).fetchone() == ("v2 draft edited",)


def test_extra_catalog_row_makes_the_stored_version_invalid(database, admin, frozen):
    VersionRepository(database).save(frozen)
    admin.execute("INSERT INTO product_version_pins (product_version_id, kind, name, digest) "
                  "VALUES (%s, 'source_commit', 'unknown/source', 'abc')", (frozen.version.id,))
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(database).get(frozen.version.id)
    with pytest.raises(VersionConflict):
        VersionRepository(database).save(frozen)


@pytest.mark.parametrize("column,value", [("fixture", True), ("status", "draft"),
                                          ("label", "Other label"), ("manifest", Jsonb({"invalid": True}))])
def test_inconsistent_stored_record_is_rejected(database, admin, frozen, column, value):
    version = frozen.version
    row = {"id": version.id, "label": version.label, "status": version.status,
           "commit_sha": version.commit_sha, "runtime_url": version.runtime_url,
           "manifest": Jsonb(frozen.model_dump(mode="json")), "fixture": False, column: value}
    admin.execute("INSERT INTO product_versions (id, label, status, commit_sha, runtime_url, manifest, "
                  "fixture) VALUES (%(id)s, %(label)s, %(status)s, %(commit_sha)s, %(runtime_url)s, "
                  "%(manifest)s, %(fixture)s)", row)
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(database).get(version.id)


def test_unknown_version_and_poisoned_manifest(database, admin, frozen):
    assert VersionRepository(database).get(uuid4()) is None
    manifest = frozen.model_dump(mode="json")
    manifest["version"]["label"] = "x'); DROP TABLE product_versions; --"
    version = frozen.version
    admin.execute("INSERT INTO product_versions (id, label, status, commit_sha, runtime_url, manifest) "
                  "VALUES (%s, %s, %s, %s, %s, %s)",
                  (version.id, version.label, version.status, version.commit_sha,
                   version.runtime_url, Jsonb(manifest)))
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(database).get(version.id)
    assert admin.execute("SELECT to_regclass('product_versions') IS NOT NULL").fetchone() == (True,)


def test_fixture_or_unvalidated_capability_rejected_before_connection(frozen):
    handoff = frozen.model_copy(deep=True)
    handoff.version.capabilities[0].validated = False
    offline = NeonDatabase(Settings(_env_file=None, app_mode="fixture"))
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(offline).save(handoff)
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(offline).save(frozen.model_copy(update={"mode": "fixture"}))
