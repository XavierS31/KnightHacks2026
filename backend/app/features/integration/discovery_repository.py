"""Durable I1 records: discovery runs, candidates, source snapshots, extractions and proposals.

Each record keeps its exact contract as JSONB. Relational columns repeat only the identities
that other rows reference, and reads reject any disagreement between the two. Records are
append-only: an identical retry is accepted, a different record under the same ID conflicts.
"""

from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from backend.app.features.integration.discovery import DiscoveryRun
from backend.app.features.integration.proposals import Extraction, ProposalPreview
from backend.app.features.integration.sources import SourceSnapshot
from backend.app.shared.database import (
    RecordConflict,
    RecordInvalid,
    RecordMissing,
    bound_transaction,
)


def _stored(record) -> None:
    if record.storage != "database":
        raise RecordInvalid("Label the record as database storage before saving it.")


def _insert_once(cursor, table: str, columns: tuple[str, ...], values: tuple, record) -> bool:
    """Insert a record once. Return False when an identical record already exists."""
    cursor.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
        f"ON CONFLICT (id) DO NOTHING RETURNING id", values)
    if cursor.fetchone() is not None:
        return True
    cursor.execute(f"SELECT record FROM {table} WHERE id = %s", (record.id,))
    if cursor.fetchone()["record"] != record.model_dump(mode="json"):
        raise RecordConflict("This identity already holds a different record; no rewrite occurred.")
    return False


class DiscoveryRepository:
    def __init__(self, database):
        self.database = database

    def save_run(self, run: DiscoveryRun) -> UUID:
        """Store a live run and index its candidates in rank order."""
        _stored(run)
        if run.mode != "live":
            raise RecordInvalid("Fixture discovery runs stay in memory.")
        candidates = [repository.id for repository in run.repositories]
        if len(set(candidates)) != len(candidates):
            raise RecordInvalid("A run lists the same repository more than once.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                if _insert_once(cursor, "discovery_runs",
                                ("id", "discovery_mode", "source_collected_at", "record"),
                                (run.id, run.request.discovery_mode, run.source_collected_at,
                                 Jsonb(run.model_dump(mode="json"))), run):
                    cursor.executemany(
                        "INSERT INTO discovery_candidates (run_id, repository_id, position, "
                        "full_name) VALUES (%s, %s, %s, %s)",
                        [(run.id, repository.id, position, repository.full_name)
                         for position, repository in enumerate(run.repositories, start=1)])
        return run.id

    def get_run(self, run_id: UUID) -> DiscoveryRun | None:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT r.id, r.discovery_mode, r.source_collected_at, r.record, "
                    "ARRAY(SELECT repository_id FROM discovery_candidates WHERE run_id = r.id "
                    "ORDER BY position) AS candidates FROM discovery_runs r WHERE r.id = %s",
                    (run_id,))
                row = cursor.fetchone()
        if row is None:
            return None
        try:
            run = DiscoveryRun.model_validate(row["record"])
        except ValidationError:
            raise RecordInvalid("A stored discovery run no longer matches its contract.") from None
        if (run.id != row["id"] or run.request.discovery_mode != row["discovery_mode"]
                or run.source_collected_at != row["source_collected_at"]
                or [repository.id for repository in run.repositories] != row["candidates"]):
            raise RecordInvalid("A stored discovery run disagrees with its indexed columns.")
        return run

    def save_snapshot(self, run_id: UUID, snapshot: SourceSnapshot) -> UUID:
        """Store a snapshot of one candidate that the stored run returned."""
        _stored(snapshot)
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT full_name FROM discovery_candidates "
                               "WHERE run_id = %s AND repository_id = %s FOR SHARE",
                               (run_id, snapshot.repository_id))
                candidate = cursor.fetchone()
                if candidate is None:
                    raise RecordMissing("The snapshot's repository is not a stored candidate "
                                        "of this run.")
                if candidate["full_name"].lower() != snapshot.full_name.lower():
                    raise RecordInvalid("The snapshot names a different repository than its "
                                        "candidate.")
                _insert_once(cursor, "source_snapshots",
                             ("id", "run_id", "repository_id", "commit_sha", "record"),
                             (snapshot.id, run_id, snapshot.repository_id, snapshot.commit_sha,
                              Jsonb(snapshot.model_dump(mode="json"))), snapshot)
        return snapshot.id

    def get_snapshot(self, snapshot_id: UUID) -> SourceSnapshot | None:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id, repository_id, commit_sha, record FROM source_snapshots "
                               "WHERE id = %s", (snapshot_id,))
                row = cursor.fetchone()
        if row is None:
            return None
        try:
            snapshot = SourceSnapshot.model_validate(row["record"])
        except ValidationError:
            raise RecordInvalid("A stored source snapshot no longer matches its contract.") from None
        if (snapshot.id != row["id"] or snapshot.repository_id != row["repository_id"]
                or snapshot.commit_sha != row["commit_sha"]):
            raise RecordInvalid("A stored source snapshot disagrees with its indexed columns.")
        return snapshot

    def save_extraction(self, extraction: Extraction) -> UUID:
        """Store an interpretation. Its pin and every citation must resolve in its snapshot."""
        _stored(extraction)
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT record FROM source_snapshots WHERE id = %s FOR SHARE",
                               (extraction.snapshot_id,))
                row = cursor.fetchone()
                if row is None:
                    raise RecordMissing("The extraction's source snapshot is not stored.")
                try:
                    snapshot = SourceSnapshot.model_validate(row["record"])
                except ValidationError:
                    raise RecordInvalid("The stored source snapshot no longer matches its "
                                        "contract.") from None
                if (extraction.repository_id, extraction.full_name, extraction.commit_sha) != (
                        snapshot.repository_id, snapshot.full_name, snapshot.commit_sha):
                    raise RecordInvalid("The extraction's repository or commit differs from its "
                                        "snapshot.")
                documents = {document.reference: document.text for document in snapshot.documents
                             if document.kind in {"readme", "documentation"}}
                if any(finding.source_reference not in documents
                       or finding.source_quote not in documents[finding.source_reference]
                       for finding in extraction.capabilities):
                    raise RecordInvalid("An extraction citation does not resolve in its snapshot.")
                _insert_once(cursor, "extractions", ("id", "snapshot_id", "record"),
                             (extraction.id, extraction.snapshot_id,
                              Jsonb(extraction.model_dump(mode="json"))), extraction)
        return extraction.id

    def get_extraction(self, extraction_id: UUID) -> Extraction | None:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id, snapshot_id, record FROM extractions WHERE id = %s",
                               (extraction_id,))
                row = cursor.fetchone()
        if row is None:
            return None
        try:
            extraction = Extraction.model_validate(row["record"])
        except ValidationError:
            raise RecordInvalid("A stored extraction no longer matches its contract.") from None
        if extraction.id != row["id"] or extraction.snapshot_id != row["snapshot_id"]:
            raise RecordInvalid("A stored extraction disagrees with its indexed columns.")
        return extraction

    def save_preview(self, preview: ProposalPreview) -> UUID:
        """Store a proposal preview. Every idea must pair two of its stored extractions."""
        _stored(preview)
        identities = preview.extraction_ids
        if len(set(identities)) != len(identities):
            raise RecordInvalid("A preview lists the same extraction more than once.")
        if any(not {idea.first_extraction_id, idea.second_extraction_id} <= set(identities)
               for idea in preview.ideas):
            raise RecordInvalid("A proposal idea references an extraction outside its preview.")
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id FROM extractions WHERE id = ANY(%s) FOR SHARE",
                               (identities,))
                if {row["id"] for row in cursor.fetchall()} != set(identities):
                    raise RecordMissing("A preview extraction is not stored.")
                if _insert_once(cursor, "proposal_previews", ("id", "record"),
                                (preview.id, Jsonb(preview.model_dump(mode="json"))), preview):
                    cursor.executemany(
                        "INSERT INTO proposal_preview_extractions (preview_id, extraction_id, "
                        "position) VALUES (%s, %s, %s)",
                        [(preview.id, identity, position)
                         for position, identity in enumerate(identities, start=1)])
        return preview.id

    def get_preview(self, preview_id: UUID) -> ProposalPreview | None:
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT p.id, p.record, ARRAY(SELECT extraction_id FROM "
                    "proposal_preview_extractions WHERE preview_id = p.id ORDER BY position) "
                    "AS extraction_ids FROM proposal_previews p WHERE p.id = %s", (preview_id,))
                row = cursor.fetchone()
        if row is None:
            return None
        try:
            preview = ProposalPreview.model_validate(row["record"])
        except ValidationError:
            raise RecordInvalid("A stored proposal preview no longer matches its contract.") from None
        if preview.id != row["id"] or preview.extraction_ids != row["extraction_ids"]:
            raise RecordInvalid("A stored proposal preview disagrees with its indexed columns.")
        return preview
