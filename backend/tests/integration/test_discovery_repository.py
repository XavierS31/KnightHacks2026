from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from backend.app.features.integration import router
from backend.app.features.integration.discovery import DiscoveryStore
from backend.app.features.integration.discovery_repository import DiscoveryRepository
from backend.app.features.integration.proposals import InterpretationStore
from backend.app.features.integration.sources import SourceStore
from backend.app.main import create_app
from backend.app.shared.database import (
    NeonDatabase,
    RecordConflict,
    RecordInvalid,
    RecordMissing,
)
from backend.app.shared.settings import Settings, get_settings


@pytest.fixture
def offline():
    return DiscoveryRepository(NeonDatabase(Settings(_env_file=None, app_mode="fixture")))


@pytest.fixture
def stored(records, run, snapshots, extractions, preview):
    """Every I1 record saved once, in dependency order."""
    records.save_run(run)
    for snapshot in snapshots:
        records.save_snapshot(run.id, snapshot)
    for extraction in extractions:
        records.save_extraction(extraction)
    records.save_preview(preview)
    return records


def test_records_round_trip_with_exact_equality_and_idempotent_retry(
        stored, run, snapshots, extractions, preview):
    assert stored.get_run(run.id) == run
    assert stored.get_snapshot(snapshots[0].id) == snapshots[0]
    assert stored.get_extraction(extractions[1].id) == extractions[1]
    assert stored.get_preview(preview.id) == preview
    assert stored.save_run(run) == run.id
    assert stored.save_snapshot(run.id, snapshots[0]) == snapshots[0].id
    assert stored.save_extraction(extractions[0]) == extractions[0].id
    assert stored.save_preview(preview) == preview.id
    assert stored.get_run(uuid4()) is None and stored.get_preview(uuid4()) is None


def test_different_record_under_a_stored_identity_conflicts_and_nothing_changes(
        stored, run, snapshots, extractions, preview):
    with pytest.raises(RecordConflict):
        stored.save_run(run.model_copy(update={"next_gate": "Changed."}))
    with pytest.raises(RecordConflict):
        stored.save_snapshot(run.id, snapshots[0].model_copy(update={"license_spdx": "GPL-3.0"}))
    with pytest.raises(RecordConflict):
        stored.save_extraction(extractions[0].model_copy(update={"limitations": []}))
    with pytest.raises(RecordConflict):
        stored.save_preview(preview.model_copy(update={"limitations": []}))
    assert stored.get_run(run.id) == run
    assert stored.get_snapshot(snapshots[0].id) == snapshots[0]
    assert stored.get_extraction(extractions[0].id) == extractions[0]
    assert stored.get_preview(preview.id) == preview


@pytest.mark.parametrize("update", [{"mode": "fixture"}, {"storage": "in_memory"}])
def test_fixture_or_unlabelled_runs_are_rejected_before_any_connection(offline, run, update):
    with pytest.raises(RecordInvalid):
        offline.save_run(run.model_copy(update=update))


def test_unlabelled_or_inconsistent_records_are_rejected_before_any_connection(
        offline, run, snapshots, extractions, preview):
    with pytest.raises(RecordInvalid):
        offline.save_run(run.model_copy(update={"repositories": run.repositories * 2}))
    with pytest.raises(RecordInvalid):
        offline.save_snapshot(run.id, snapshots[0].model_copy(update={"storage": "in_memory"}))
    with pytest.raises(RecordInvalid):
        offline.save_extraction(extractions[0].model_copy(update={"storage": "in_memory"}))
    with pytest.raises(RecordInvalid):
        offline.save_preview(preview.model_copy(update={"extraction_ids": [extractions[0].id]}))


def test_snapshot_must_belong_to_a_stored_candidate_of_its_run(records, run, snapshots):
    with pytest.raises(RecordMissing):
        records.save_snapshot(run.id, snapshots[0])
    records.save_run(run)
    with pytest.raises(RecordMissing):
        records.save_snapshot(uuid4(), snapshots[0])
    with pytest.raises(RecordMissing):
        records.save_snapshot(run.id, snapshots[0].model_copy(update={"repository_id": uuid4()}))
    with pytest.raises(RecordInvalid):
        records.save_snapshot(run.id, snapshots[0].model_copy(update={"full_name": "other/name"}))
    assert records.get_snapshot(snapshots[0].id) is None


def test_extraction_pin_and_citations_must_resolve_in_its_snapshot(records, run, snapshots, extractions):
    extraction = extractions[0]
    with pytest.raises(RecordMissing):
        records.save_extraction(extraction)
    records.save_run(run)
    records.save_snapshot(run.id, snapshots[0])
    with pytest.raises(RecordInvalid):
        records.save_extraction(extraction.model_copy(update={"commit_sha": "f" * 40}))
    with pytest.raises(RecordInvalid):
        records.save_extraction(extraction.model_copy(update={"capabilities": [
            extraction.capabilities[0].model_copy(update={"source_quote": "Invented quote."})]}))
    with pytest.raises(RecordInvalid):
        records.save_extraction(extraction.model_copy(update={"capabilities": [
            extraction.capabilities[0].model_copy(update={"source_reference": "https://x.invalid"})]}))
    assert records.get_extraction(extraction.id) is None


def test_preview_needs_every_extraction_stored(records, run, snapshots, extractions, preview):
    records.save_run(run)
    records.save_snapshot(run.id, snapshots[0])
    records.save_extraction(extractions[0])
    with pytest.raises(RecordMissing):
        records.save_preview(preview)
    assert records.get_preview(preview.id) is None


@pytest.mark.parametrize("statement", [
    "UPDATE discovery_runs SET record = record || '{\"next_gate\": \"x\"}'",
    "DELETE FROM discovery_candidates",
    "UPDATE source_snapshots SET commit_sha = repeat('f', 40)",
    "DELETE FROM extractions",
    "UPDATE proposal_previews SET record = record",
    "DELETE FROM proposal_preview_extractions",
])
def test_database_refuses_to_change_stored_records(isolated, stored, statement):
    settings, _ = isolated
    with psycopg.connect(settings.database_url.get_secret_value(), sslmode="require") as connection:
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute(statement)


def test_database_refuses_fixture_run_records(isolated, database, run):
    settings, _ = isolated
    with psycopg.connect(settings.database_url.get_secret_value(), sslmode="require") as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO discovery_runs (id, discovery_mode, source_collected_at, record) "
                "VALUES (%s, 'popular', now(), %s)",
                (run.id, Jsonb(run.model_copy(update={"mode": "fixture"}).model_dump(mode="json"))))


def test_stores_write_through_and_a_fresh_process_reads_records_back(
        records, run, snapshots, extractions, preview):
    unlabelled = {"storage": "in_memory", "limitations": []}
    saved_run = DiscoveryStore().add(run.model_copy(update=unlabelled), records)
    saved_snapshot = SourceStore().add(run.id, snapshots[0].model_copy(update=unlabelled), records)
    SourceStore().add(run.id, snapshots[1], records)
    interpretations = InterpretationStore()
    saved_extraction = interpretations.add_extraction(
        extractions[0].model_copy(update=unlabelled), records)
    interpretations.add_extraction(extractions[1], records)
    saved_preview = interpretations.add_preview(preview.model_copy(update=unlabelled), records)
    assert {saved_run.storage, saved_snapshot.storage, saved_extraction.storage,
            saved_preview.storage} == {"database"}
    assert DiscoveryStore().get(run.id, records) == saved_run
    assert SourceStore().get(snapshots[0].id, records) == saved_snapshot
    assert InterpretationStore().get_extraction(extractions[0].id, records) == saved_extraction
    assert InterpretationStore().get_preview(preview.id, records) == saved_preview


def test_fixture_runs_stay_in_memory_when_records_exist(records, run):
    fixture = DiscoveryStore().add(run.model_copy(update={"mode": "fixture", "storage": "in_memory"}),
                                   records)
    assert fixture.storage == "in_memory"
    assert records.get_run(run.id) is None


def test_api_reads_stored_records_after_memory_is_lost(stored, run, snapshots, extractions, preview):
    app = create_app()
    app.dependency_overrides[router.get_records] = lambda: stored
    client = TestClient(app)
    assert client.get(f"/api/v1/discovery-runs/{run.id}").json() == run.model_dump(mode="json")
    assert client.get(f"/api/v1/source-snapshots/{snapshots[1].id}").json() == snapshots[1].model_dump(mode="json")
    assert client.get(f"/api/v1/extractions/{extractions[0].id}").json() == extractions[0].model_dump(mode="json")
    assert client.get(f"/api/v1/proposal-previews/{preview.id}").json() == preview.model_dump(mode="json")
    response = client.get(f"/api/v1/discovery-runs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DISCOVERY_RUN_NOT_FOUND"


@pytest.mark.parametrize("mode,url", [("fixture", "postgresql://fixture:secret@invalid/test"),
                                      ("live", "")])
def test_records_are_disabled_without_live_mode_and_a_database(mode, url):
    assert router.get_records(Settings(_env_file=None, app_mode=mode, database_url=SecretStr(url))) is None


def test_unreachable_database_reports_storage_unavailable():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, app_mode="live",
        database_url=SecretStr("postgresql://nobody@127.0.0.1:9/none"))
    response = TestClient(app).get(f"/api/v1/discovery-runs/{uuid4()}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DISCOVERY_STORAGE_UNAVAILABLE"
