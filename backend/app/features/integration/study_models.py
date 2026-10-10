"""Automatic discovery/research contracts, separate from validated product manifests."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, computed_field, field_validator, model_validator

from backend.app.features.integration.discovery import DiscoveryRequest, DiscoveryRun
from backend.app.features.integration.opportunities import OpportunityCitation
from backend.app.shared.contracts import Contract, Repository


class StudyRequest(Contract):
    discovery: DiscoveryRequest = Field(default_factory=lambda: DiscoveryRequest(discovery_mode="emerging", query="stars:>=20", limit=12))
    research_limit: int = Field(default=3, ge=1, le=6)
    interests: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def emerging_anchors(self):
        self.discovery = self.discovery.model_copy(update={"discovery_mode": "emerging"})
        return self


class BriefCapability(Contract):
    name: str = Field(min_length=1, max_length=120)
    mechanism: str = Field(min_length=1, max_length=300)
    citation_ids: list[int] = Field(min_length=1, max_length=3)


class BriefOutput(Contract):
    summary: str = Field(min_length=1, max_length=600)
    original_purpose: str = Field(min_length=1, max_length=400)
    distinctive_mechanism: str = Field(min_length=1, max_length=400)
    inputs: str = Field(min_length=1, max_length=300)
    outputs: str = Field(min_length=1, max_length=300)
    interfaces: str = Field(min_length=1, max_length=300)
    reuse_limits: str = Field(min_length=1, max_length=400)
    reuse_assessment: Literal["promising", "unsuitable", "uncertain"]
    selection_reason: str = Field(min_length=1, max_length=500)
    capabilities: list[BriefCapability] = Field(min_length=1, max_length=3)


class RepositoryResearch(Contract):
    repository: Repository
    origin: Literal["discovery", "supporting_tool"] = "discovery"
    status: Literal["queued", "researching", "researched", "failed", "not_researched", "screened", "unsuitable"]
    selection_score: int | None = None
    selection_reasons: list[str] = Field(default_factory=list)
    source_gaps: list[str] = Field(default_factory=list)
    snapshot_id: UUID | None = None
    commit_sha: str | None = None
    brief: BriefOutput | None = None
    evidence: list[OpportunityCitation] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    coverage: list[str] = Field(default_factory=list)
    failure: str | None = None


class ProductIdea(Contract):
    title: str = Field(min_length=1, max_length=120)
    anchor_repository: str = Field(min_length=1, max_length=100)
    additional_repositories: list[str] = Field(default_factory=list, max_length=2)
    audience: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, max_length=400)
    new_use: str = Field(min_length=1, max_length=500)
    original_use_difference: str = Field(min_length=1, max_length=500)
    capability_connection: str = Field(min_length=1, max_length=500)
    example_input: str = Field(min_length=1, max_length=300)
    example_output: str = Field(min_length=1, max_length=400)
    prototype_check: str = Field(min_length=1, max_length=400)
    alternative_queries: list[str] = Field(min_length=2, max_length=2)
    risk: str = Field(min_length=1, max_length=400)

    @field_validator("anchor_repository", "additional_repositories")
    @classmethod
    def identities(cls, value):
        import re
        for name in value if isinstance(value, list) else [value]:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
                raise ValueError("Use owner/repository identities")
        return value

    @field_validator("alternative_queries")
    @classmethod
    def queries(cls, values):
        if len(set(values)) != 2 or any(not value.strip() or len(value) > 100 or any(ord(c) < 32 for c in value) for value in values):
            raise ValueError("Supply two distinct bounded purpose-based search queries")
        return values


class IdeasOutput(Contract):
    ideas: list[ProductIdea] = Field(default_factory=list, max_length=2)
    explanation: str = Field(min_length=1, max_length=500)


class Alternative(Contract):
    repository: str
    url: str
    description: str
    readme: str | None = None
    readme_reference: str | None = None


class AlternativeSearch(Contract):
    query: str
    reference: str
    collected_at: datetime
    status: Literal["completed", "failed"]
    matches: list[Alternative] = Field(default_factory=list)
    failure: str | None = None


class CritiqueOutput(Contract):
    scope: Literal["substantial_repurpose", "incremental_feature", "already_present", "unsupported"]
    technical_support: Literal["supported", "uncertain", "unsupported"]
    novelty: Literal["close_equivalent", "partial_overlap", "no_close_match", "inconclusive"]
    reason: str = Field(min_length=1, max_length=600)
    difference: str = Field(min_length=1, max_length=500)
    matching_references: list[str] = Field(default_factory=list, max_length=4)


class EvaluatedProduct(Contract):
    id: UUID
    idea: ProductIdea
    status: Literal["recommended_for_prototype", "research_needed", "rejected"]
    critique: CritiqueOutput | None = None
    searches: list[AlternativeSearch] = Field(default_factory=list)
    evidence: list[OpportunityCitation] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    failure: str | None = None
    example_status: Literal["illustrative_not_executed"] = "illustrative_not_executed"


class ResearchStudy(Contract):
    id: UUID
    request: StudyRequest
    mode: Literal["fixture", "live"]
    status: Literal["queued", "running", "completed", "partial", "failed", "cancelled", "interrupted"]
    stage: str
    created_at: datetime
    updated_at: datetime
    discovery: DiscoveryRun | None = None
    repositories: list[RepositoryResearch] = Field(default_factory=list)
    products: list[EvaluatedProduct] = Field(default_factory=list)
    explanation: str = ""
    failures: list[str] = Field(default_factory=list)
    api_requests: int = 0
    inference_calls: int = 0
    limits: dict[str, int] = Field(default_factory=lambda: {"seconds": 900, "api_requests": 90, "screened_candidates": 12, "replacement_attempts": 3, "inference_calls": 13})
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    storage: Literal["in_memory"] = "in_memory"
    limitations: list[str] = Field(default_factory=lambda: [
        "Automatic research is bounded; statuses show which candidates were actually researched.",
        "GitHub repository/README search returns at most two projects per query and uses up to 2,200 characters of selected README sections per match; commercial products and the wider web are not covered.",
        "No close match in a bounded search is not a guarantee of uniqueness or demand.",
        "Proposed uses and examples are hypotheses; no prototype or persona trial has executed them.",
        "Studies persist only in this API process. Browser reload can reconnect; server restart loses job state.",
    ])

    @computed_field
    @property
    def counts(self) -> dict[str, int]:
        return {
            "researched": sum(r.brief is not None for r in self.repositories),
            "suitable_researched": sum(r.status == "researched" for r in self.repositories),
            "research_failures": sum(r.status == "failed" for r in self.repositories),
            "unsuitable": sum(r.status == "unsuitable" for r in self.repositories),
            "source_gaps": sum(len(r.source_gaps) for r in self.repositories),
            "rejected_ideas": sum(p.status == "rejected" for p in self.products),
            "evaluation_failures": sum(bool(p.failure) or any(s.status == "failed" for s in p.searches) for p in self.products),
            "recommended": sum(p.status == "recommended_for_prototype" for p in self.products),
            "run_failures": len(set([*self.failures, *[f"{r.repository.full_name}: {gap}" for r in self.repositories for gap in r.source_gaps], *[f"{p.idea.title}: {p.failure}" for p in self.products if p.failure], *[f"{s.query}: {s.failure}" for p in self.products for s in p.searches if s.failure]])),
        }
