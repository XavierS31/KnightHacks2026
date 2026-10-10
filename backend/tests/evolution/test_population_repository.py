"""Offline fake database/provider tests; no actual source collection or Neon claims."""

import copy
import re
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from backend.app.features.evolution.population_repository import (
    PopulationRepository,
    PopulationStorageError,
    ReviewerIdentity,
)
from backend.app.features.personas.population import approve_behavior, generate_population
from backend.app.features.personas.review_corpus import freeze_corpus
from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.settings import Settings
from backend.tests.personas.test_population import FakeHF, inputs


class MemoryDatabase:
    """Transactional SQL recorder; failures restore all rows, including prior inserts."""
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.result = None

    @contextmanager
    def connection(self):
        original = copy.deepcopy(self.rows)
        try:
            yield self
        except Exception:
            self.rows = original
            raise

    @contextmanager
    def cursor(self, **kwargs):
        yield self

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SET "):
            return
        if sql.startswith("INSERT"):
            match = re.match(r"INSERT INTO (\w+) \(([^)]+)\)", sql)
            table, columns = match.groups()
            names = columns.split(", ")
            for start in range(0, len(params), len(names)):
                row = dict(zip(names, [p.obj if isinstance(p, Jsonb) else p
                                      for p in params[start:start + len(names)]], strict=True))
                key_count = 2 if table == "review_corpus_members" else 1
                key = tuple(list(row.values())[:key_count])
                self.rows.setdefault(table, {}).setdefault(key, copy.deepcopy(row))
        elif "AS corpus_snapshot" in sql:
            corpus = self.rows.get("review_corpora", {}).get((params[0],))
            approval = self.rows.get("behavior_approvals", {}).get((params[1],))
            self.result = None if not corpus or not approval else {
                "corpus_snapshot": corpus["snapshot_json"],
                "approval_snapshot": approval["snapshot_json"]}
        else:
            match = re.match(r"SELECT (.+) FROM (\w+) WHERE ", sql)
            columns, table = match.groups()
            if "ANY(%s)" in sql:
                self.result = [{c: row[c] for c in columns.split(", ")}
                    for key, row in self.rows.get(table, {}).items() if key[0] in params[0]]
                return
            row = self.rows.get(table, {}).get(tuple(params))
            self.result = None if row is None else {c: row[c] for c in columns.split(", ")}

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


async def bundle():
    corpus, draft, review, task, quota = inputs()
    approval = approve_behavior(draft, corpus, review)
    population = await generate_population(corpus, approval, FakeHF(), quotas=[quota],
        task_templates=[task], generation_version="unit-test-only", purpose="pilot")
    identity = ReviewerIdentity("test-operator", review.reviewer_ref)
    return corpus, approval, population, identity


async def test_atomic_idempotent_round_trip_preserves_exact_snapshots_and_zero_trials():
    corpus, approval, population, identity = await bundle()
    database = MemoryDatabase()
    repository = PopulationRepository(database)
    first = repository.save_bundle(corpus, approval, population, reviewer=identity)
    before = copy.deepcopy(database.rows)
    assert repository.save_bundle(corpus, approval, population, reviewer=identity) == first
    assert database.rows == before
    assert repository.load_population(population.version) == population
    assert len(database.rows["immutable_personas"]) == 2
    stored = database.rows["populations"][(population.version,)]
    assert stored["completed_trials"] == 0
    attestation = database.rows["behavior_approvals"][(approval.version,)]["operator_attestation"]
    assert attestation["authenticated_human_identity"] is False


async def test_full_population_uses_bounded_bulk_storage_with_zero_executed_trials():
    corpus, draft, review, task, quota = inputs()
    quota.count = 500
    approval = approve_behavior(draft, corpus, review)
    population = await generate_population(corpus, approval, FakeHF(), quotas=[quota],
        task_templates=[task], generation_version="unit-test-only-500", purpose="complete")
    database = MemoryDatabase()
    repository = PopulationRepository(database)
    repository.save_bundle(corpus, approval, population,
        reviewer=ReviewerIdentity("test-operator", review.reviewer_ref))
    assert len(database.rows["immutable_personas"]) == 500
    assert len(database.rows["immutable_tasks"]) == 500
    assert len(database.calls) < 80
    assert repository.load_population(population.version).data()["completed_trials"] == 0


async def test_stable_source_identity_can_have_distinct_immutable_corpus_curation():
    corpus, draft, review, task, quota = inputs()
    approval = approve_behavior(draft, corpus, review)
    first = await generate_population(corpus, approval, FakeHF(), quotas=[quota],
        task_templates=[task], generation_version="unit-test-only", purpose="pilot")
    changed_reviews = corpus.reviews()
    changed_reviews[0].evidence.retrieved_at += timedelta(days=1)
    changed_reviews[0].evidence.summary = "Revised bounded paraphrase of the same test report"
    second_corpus = freeze_corpus(changed_reviews, software_context=corpus.data()["software_context"],
                                  selection_limits=corpus.data()["selection_limits"])
    second_draft = type(draft)(second_corpus.version, draft.output_json, draft.provenance_json)
    second_approval = approve_behavior(second_draft, second_corpus, review)
    second = await generate_population(second_corpus, second_approval, FakeHF(), quotas=[quota],
        task_templates=[task], generation_version="unit-test-only", purpose="pilot")
    database = MemoryDatabase()
    repository = PopulationRepository(database)
    identity = ReviewerIdentity("test-operator", review.reviewer_ref)
    repository.save_bundle(corpus, approval, first, reviewer=identity)
    repository.save_bundle(second_corpus, second_approval, second, reviewer=identity)
    assert len(database.rows["software_reviews"]) == 1
    assert len(database.rows["review_corpus_members"]) == 2
    assert len(database.rows["review_corpora"]) == 2
    assert repository.load_population(first.version) == first
    assert repository.load_population(second.version) == second
    evidence_id = changed_reviews[0].evidence.id
    first_payload = database.rows["review_corpus_members"][(corpus.version, evidence_id)]["payload"]
    second_payload = database.rows["review_corpus_members"][(second_corpus.version,
                                                            evidence_id)]["payload"]
    assert first_payload != second_payload


async def test_conflicting_late_persona_rolls_back_new_corpus_and_population_rows():
    corpus, approval, population, identity = await bundle()
    database = MemoryDatabase()
    persona_id = population.personas()[0].id
    database.rows = {"immutable_personas": {(persona_id,): {"id": persona_id,
        "population_version": "other", "payload": {"conflicting": True}}}}
    original = copy.deepcopy(database.rows)
    with pytest.raises(PopulationStorageError, match="IMMUTABLE_LINEAGE_CONFLICT"):
        PopulationRepository(database).save_bundle(corpus, approval, population, reviewer=identity)
    assert database.rows == original


async def test_operator_and_reviewer_are_separate_and_mismatch_never_opens_database():
    corpus, approval, population, _ = await bundle()
    database = MemoryDatabase()
    with pytest.raises(PopulationStorageError, match="BUNDLE_LINEAGE_MISMATCH"):
        PopulationRepository(database).save_bundle(corpus, approval, population,
            reviewer=ReviewerIdentity("test-operator", "different-reviewer"))
    assert not database.calls


async def test_fixture_mode_cannot_persist_even_valid_source_shaped_test_data():
    corpus, approval, population, identity = await bundle()
    database = NeonDatabase(Settings(_env_file=None, app_mode="fixture"))
    with pytest.raises(DatabaseUnavailable, match="fixture mode"):
        PopulationRepository(database).save_bundle(corpus, approval, population, reviewer=identity)


async def test_readback_detects_tampered_snapshot_and_missing_lineage():
    corpus, approval, population, identity = await bundle()
    database = MemoryDatabase()
    repository = PopulationRepository(database)
    repository.save_bundle(corpus, approval, population, reviewer=identity)
    database.rows["review_corpora"].clear()
    with pytest.raises(PopulationStorageError, match="BUNDLE_LINEAGE_MISMATCH"):
        repository.load_population(population.version)
    database.rows["populations"][(population.version,)]["snapshot_json"] += " "
    with pytest.raises(PopulationStorageError, match="INVALID_SNAPSHOT_VERSION"):
        repository.load_population(population.version)


def test_missing_population_reports_fixed_error():
    with pytest.raises(PopulationStorageError, match="POPULATION_NOT_FOUND"):
        PopulationRepository(MemoryDatabase()).load_population("missing")


async def test_postgresql_migration_and_population_round_trip(migrated_settings):
    """Optional disposable TLS DB integration; skips without TEST_DATABASE_URL."""
    corpus, approval, population, identity = await bundle()
    database = NeonDatabase(migrated_settings)
    migration = Path(__file__).parents[2] / "migrations" / "005_review_populations.sql"
    try:
        with database.connection() as connection:
            connection.execute(migration.read_text())
        repository = PopulationRepository(database)
        repository.save_bundle(corpus, approval, population, reviewer=identity)
        repository.save_bundle(corpus, approval, population, reviewer=identity)
        assert repository.load_population(population.version) == population
    finally:
        database.close()
