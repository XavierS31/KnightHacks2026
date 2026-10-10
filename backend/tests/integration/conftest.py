from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from backend.app.features.integration.discovery import DiscoveryRequest, DiscoveryRun
from backend.app.features.integration.discovery_repository import DiscoveryRepository
from backend.app.features.integration.proposals import (
    CapabilityFinding,
    Extraction,
    PairIdea,
    ProposalPreview,
)
from backend.app.features.integration.sources import SourceDocument, SourceSnapshot
from backend.app.shared.contracts import Evidence, Repository
from backend.migrations.runner import apply, discover

COLLECTED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
NAMES = ["example/parser", "example/exporter"]


@pytest.fixture
def database(isolated):
    """A fully migrated, empty schema."""
    _, database = isolated
    apply(database, discover())
    return database


@pytest.fixture
def records(database):
    return DiscoveryRepository(database)


@pytest.fixture
def run():
    """A live Popular run with two candidates, labelled for database storage."""
    return DiscoveryRun(
        id=uuid4(), mode="live", status="completed", request=DiscoveryRequest(mode="live", limit=2),
        created_at=COLLECTED, source_total=2, source_collected_at=COLLECTED, storage="database",
        repositories=[Repository(
            id=uuid5(NAMESPACE_URL, f"https://github.com/{name}"), full_name=name,
            url=f"https://github.com/{name}", stars=10, description="Parser", discovery_mode="popular",
            evidence=[Evidence(source="GitHub repository search API",
                               reference="https://api.github.com/search/repositories",
                               collected_at=COLLECTED, kind="source", note="Search metadata.")])
            for name in NAMES],
        limitations=["The run record is stored in the database."],
        next_gate="Inspect source interfaces.",
    )


@pytest.fixture
def snapshots(run):
    """One commit-pinned README snapshot for each candidate of the run."""
    return [SourceSnapshot(
        id=uuid4(), repository_id=repository.id, full_name=repository.full_name,
        commit_sha=f"{position}" * 40,
        commit_reference=f"https://github.com/{repository.full_name}/commit/{position * 40}",
        collected_at=COLLECTED, status="collected", license_spdx="MIT", storage="database",
        documents=[SourceDocument(
            kind="readme", reference=f"https://github.com/{repository.full_name}/blob/{position * 40}/README.md",
            request_reference="https://api.github.com/readme", collected_at=COLLECTED,
            text="# Tool\nReads PDF tables into rows.\nWrites validated CSV.",
            content_sha256="0" * 64, truncated=False)],
        limitations=["Source text is untrusted."], failures=[])
        for position, repository in zip(["1", "2"], run.repositories, strict=True)]


@pytest.fixture
def extractions(snapshots):
    """One cited interpretation of each snapshot."""
    return [Extraction(
        id=uuid4(), snapshot_id=snapshot.id, repository_id=snapshot.repository_id,
        full_name=snapshot.full_name, commit_sha=snapshot.commit_sha, collected_at=COLLECTED,
        capabilities=[CapabilityFinding(
            name="Table rows", documented_input="PDF", documented_output="Rows",
            source_reference=snapshot.documents[0].reference,
            source_quote="Reads PDF tables into rows.", uncertainty="Interface unknown.")],
        provenance={"model": "test-model", "cost": 0.0001}, reservation={"amount": 0.01},
        limitations=["HF interpretation."], storage="database")
        for snapshot in snapshots]


@pytest.fixture
def preview(extractions):
    return ProposalPreview(
        id=uuid4(), extraction_ids=[item.id for item in extractions],
        ideas=[PairIdea(title="Rows to CSV", first_extraction_id=extractions[0].id,
                        second_extraction_id=extractions[1].id, problem="Manual copying.",
                        adapter_boundary="Rows become CSV input.", audience="Analysts",
                        uncertainty="Unreviewed.")],
        provenance={"model": "test-model"}, reservation={"amount": 0.01},
        limitations=["Hypotheses only."], storage="database")
