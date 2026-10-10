import hashlib
from urllib.parse import urlsplit

import pytest

from backend.migrations.roundtrip import read, run
from backend.migrations.runner import DIRECTORY, MigrationError, apply, discover, recorded


def test_discover_orders_repository_migrations_with_exact_checksums():
    migrations = discover()
    assert [item.version for item in migrations] == ["001_initial", "002_persistence_checks",
                                                       "003_records_and_job_leases",
                                                       "004_integration_records"]
    for item in migrations:
        content = (DIRECTORY / f"{item.version}.sql").read_bytes()
        assert item.checksum == hashlib.sha256(content).hexdigest()
        assert item.sql == content.decode("utf-8")
        assert "BEGIN;" not in item.sql and "COMMIT;" not in item.sql


def test_discover_rejects_number_gaps(tmp_path):
    (tmp_path / "001_first.sql").write_text("SELECT 1;")
    (tmp_path / "003_third.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="contiguous"):
        discover(tmp_path)


def test_discover_rejects_unordered_names(tmp_path):
    (tmp_path / "1_first.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="NNN_name"):
        discover(tmp_path)


def test_apply_records_checksums_and_is_idempotent(isolated):
    _, database = isolated
    migrations = discover()
    assert recorded(database) == []
    assert apply(database, migrations) == ["001_initial", "002_persistence_checks",
                                         "003_records_and_job_leases", "004_integration_records"]
    assert apply(database, migrations) == []
    assert recorded(database) == [(item.version, item.checksum) for item in migrations]


def test_edited_applied_migration_is_rejected_without_changes(isolated):
    _, database = isolated
    migrations = discover()
    apply(database, migrations[:1])
    with database.connection() as connection:
        connection.execute("UPDATE schema_migrations SET checksum = 'edited'")
    with pytest.raises(MigrationError, match="differs"):
        apply(database, migrations)
    assert recorded(database) == [("001_initial", "edited")]


def test_failed_migration_rolls_back_every_pending_migration(isolated, tmp_path):
    _, database = isolated
    (tmp_path / "001_valid.sql").write_text("CREATE TABLE gate_valid (id integer);")
    (tmp_path / "002_invalid.sql").write_text("CREATE TABLE gate_invalid (id missing_type);")
    with pytest.raises(MigrationError, match="002_invalid failed with SQLSTATE 42704"):
        apply(database, discover(tmp_path))
    assert recorded(database) == []
    with database.connection() as connection:
        assert connection.execute("SELECT to_regclass('gate_valid')").fetchone() == (None,)


def test_roundtrip_persists_write_and_discards_aborted_write(isolated):
    settings, database = isolated
    apply(database, discover())
    evidence = run(settings)
    assert read(database, evidence["durable_id"])[1] == "durable write/read gate"
    assert read(database, evidence["rollback_id"]) is None
    assert evidence["migrations"] == recorded(database)
    # True only when TEST_DATABASE_URL is a Neon branch; a local database must never claim Neon.
    assert evidence["neon_host"] is urlsplit(settings.database_url.get_secret_value()).hostname.endswith(".neon.tech")
