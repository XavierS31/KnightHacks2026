"""Atomic immutable B lineage storage; no browser execution or fixture persistence.

The caller supplies B's independently validated snapshots. Operator attestation is
explicitly local and does not authenticate a human or establish a hosted review gate.
Snapshots contain curated excerpts/paraphrases, never original full source text,
screenshot bytes, credentials or hidden model reasoning.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.features.personas.population import ApprovedBehavior, FrozenPopulation
from backend.app.features.personas.review_corpus import FrozenCorpus
from backend.app.shared.database import NeonDatabase


class PopulationStorageError(RuntimeError):
    """Fixed safe errors; payloads and database credentials are never exposed."""


@dataclass(frozen=True)
class ReviewerIdentity:
    operator_ref: str
    independent_reviewer_ref: str

    def data(self) -> dict[str, Any]:
        if any(not isinstance(ref, str) or not 3 <= len(ref.strip()) <= 100
               for ref in (self.operator_ref, self.independent_reviewer_ref)):
            raise PopulationStorageError("INVALID_OPERATOR_ATTESTATION")
        return {"operator_ref": self.operator_ref,
                "independent_reviewer_ref": self.independent_reviewer_ref,
                "authentication": "local_operator_attestation",
                "authenticated_human_identity": False}


def _checked_version(snapshot: str, version: str) -> None:
    if (not isinstance(snapshot, str) or len(snapshot.encode()) > 32 * 1024 * 1024
            or hashlib.sha256(snapshot.encode()).hexdigest() != version):
        raise PopulationStorageError("INVALID_SNAPSHOT_VERSION")


def _reject_private_fields(value: Any) -> None:
    forbidden = {"source_text", "hf_token", "database_url", "api_key", "screenshot_bytes",
                 "hidden_reasoning", "chain_of_thought"}
    if isinstance(value, dict):
        if forbidden.intersection(str(key).lower() for key in value):
            raise PopulationStorageError("PRIVATE_FIELDS_NOT_PERSISTABLE")
        for item in value.values():
            _reject_private_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_fields(item)


# Table/column identifiers below are internal constants, never supplied source/model text.
def _insert_frozen(cursor, table: str, key: dict[str, Any], values: dict[str, Any]) -> None:
    row = {**key, **values}
    columns = ", ".join(row)
    params = tuple(Jsonb(value) if isinstance(value, dict) else value for value in row.values())
    cursor.execute(f"INSERT INTO {table} ({columns}) VALUES "
                   f"({', '.join(['%s'] * len(row))}) ON CONFLICT DO NOTHING", params)
    predicate = " AND ".join(f"{column} = %s" for column in key)
    cursor.execute(f"SELECT {columns} FROM {table} WHERE {predicate}", tuple(key.values()))
    if cursor.fetchone() != row:
        raise PopulationStorageError("IMMUTABLE_LINEAGE_CONFLICT")


def _insert_records(cursor, table: str, rows: list[dict[str, Any]]) -> None:
    """Bounded 50-record inserts/readbacks avoid one network trip per persona field."""
    for start in range(0, len(rows), 50):
        chunk = rows[start:start + 50]
        columns = ", ".join(chunk[0])
        placeholders = "(" + ", ".join(["%s"] * len(chunk[0])) + ")"
        params = tuple(Jsonb(value) if isinstance(value, dict) else value
                       for row in chunk for value in row.values())
        cursor.execute(f"INSERT INTO {table} ({columns}) VALUES "
                       f"{', '.join([placeholders] * len(chunk))} ON CONFLICT DO NOTHING", params)
        cursor.execute(f"SELECT {columns} FROM {table} WHERE id = ANY(%s)",
                       ([row["id"] for row in chunk],))
        actual = {row["id"]: row for row in cursor.fetchall()}
        if actual != {row["id"]: row for row in chunk}:
            raise PopulationStorageError("IMMUTABLE_LINEAGE_CONFLICT")


class PopulationRepository:
    def __init__(self, database: NeonDatabase):
        self.database = database

    def save_bundle(self, corpus: FrozenCorpus, approval: ApprovedBehavior,
                    population: FrozenPopulation, *, reviewer: ReviewerIdentity) -> UUID:
        """Commit all lineage together; identical retries are idempotent, edits conflict.

        Live-mode database configuration is enforced by NeonDatabase. A pilot may
        be stored but retains its configured count and zero executed trial count.
        """
        for snapshot in (corpus, approval, population):
            _checked_version(snapshot.snapshot_json, snapshot.version)
        corpus_data = corpus.data()
        approval_data = approval.data(corpus)
        population_data = population.data()
        attestation = reviewer.data()
        if (population_data["corpus_version"] != corpus.version
                or population_data["corpus_snapshot_json"] != corpus.snapshot_json
                or population_data["approval_version"] != approval.version
                or population_data["approved_behavior"] != approval_data
                or reviewer.independent_reviewer_ref != approval_data["review"]["reviewer_ref"]):
            raise PopulationStorageError("BUNDLE_LINEAGE_MISMATCH")
        for data in (corpus_data, approval_data, population_data, attestation):
            _reject_private_fields(data)
        population_id = uuid5(NAMESPACE_URL, "frozen-population:" + population.version)
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute("SET LOCAL lock_timeout = '2s'")
                _insert_frozen(cursor, "review_corpora", {"version": corpus.version},
                               {"snapshot_json": corpus.snapshot_json})
                for review in corpus_data["reviews"]:
                    evidence = review["evidence"]
                    review_id = UUID(evidence["id"])
                    _insert_frozen(cursor, "software_reviews", {"id": review_id},
                                   {"platform": evidence["platform"],
                                    "external_id": evidence["external_id"]})
                    _insert_frozen(cursor, "review_corpus_members",
                                   {"corpus_version": corpus.version, "review_id": review_id},
                                   {"payload": evidence})
                _insert_frozen(cursor, "behavior_approvals", {"version": approval.version},
                    {"corpus_version": corpus.version, "snapshot_json": approval.snapshot_json,
                     "reviewer_ref": reviewer.independent_reviewer_ref,
                     "operator_attestation": attestation})
                _insert_frozen(cursor, "populations", {"version": population.version},
                    {"id": population_id, "corpus_version": corpus.version,
                     "approval_version": approval.version,
                     "generation_version": population_data["generation_version"],
                     "configured_count": population_data["configured_count"],
                     "completed_trials": 0, "snapshot_json": population.snapshot_json})
                personas, scenarios, tasks = [], [], []
                for persona, task in zip(population_data["personas"], population_data["tasks"],
                                         strict=True):
                    persona_id = UUID(persona["id"])
                    scenario = persona["scenario"]
                    scenario_id = UUID(scenario["id"])
                    personas.append({"id": persona_id, "population_version": population.version,
                                     "payload": persona})
                    scenarios.append({"id": scenario_id, "persona_id": persona_id,
                                      "payload": scenario})
                    tasks.append({"id": UUID(task["id"]), "persona_id": persona_id,
                                  "scenario_id": scenario_id, "payload": task})
                _insert_records(cursor, "immutable_personas", personas)
                _insert_records(cursor, "immutable_scenarios", scenarios)
                _insert_records(cursor, "immutable_tasks", tasks)
        return population_id

    def load_population(self, version: str) -> FrozenPopulation:
        """Read a stable snapshot and revalidate every B identity/hash/citation gate."""
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute("SELECT snapshot_json FROM populations WHERE version = %s", (version,))
                row = cursor.fetchone()
                if row is None:
                    raise PopulationStorageError("POPULATION_NOT_FOUND")
                snapshot = row["snapshot_json"]
                _checked_version(snapshot, version)
                population = FrozenPopulation(snapshot, version)
                data = population.data()
                cursor.execute("SELECT c.snapshot_json AS corpus_snapshot, "
                    "a.snapshot_json AS approval_snapshot FROM review_corpora c "
                    "JOIN behavior_approvals a ON a.corpus_version = c.version "
                    "WHERE c.version = %s AND a.version = %s",
                    (data["corpus_version"], data["approval_version"]))
                lineage = cursor.fetchone()
                if (lineage is None or lineage["corpus_snapshot"] != data["corpus_snapshot_json"]
                        or json.loads(lineage["approval_snapshot"]) != data["approved_behavior"]):
                    raise PopulationStorageError("BUNDLE_LINEAGE_MISMATCH")
        return population
