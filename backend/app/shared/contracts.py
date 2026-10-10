"""Canonical contracts. Consumers generate types from the exported OpenAPI document."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Contract):
    source: str
    reference: str
    collected_at: datetime
    kind: Literal["source", "assumption", "fixture"]
    note: str


class Repository(Contract):
    id: UUID
    full_name: str
    url: str
    commit_sha: str | None = None
    discovery_mode: Literal["popular", "trending", "fixture"]
    stars: int = Field(ge=0)
    description: str
    evidence: list[Evidence]


class Capability(Contract):
    id: UUID
    key: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    validated: bool = False
    evidence: list[Evidence]


class Proposal(Contract):
    id: UUID
    title: str
    repository_ids: list[UUID] = Field(min_length=2, max_length=3)
    audience: str
    problem: str
    adapter_boundary: str
    novelty: Literal["unresolved", "overlap", "partial_overlap", "no_close_match"]
    feasibility: Literal["unreviewed", "feasible", "blocked"]
    status: Literal["proposed", "interfaces_inspected", "validated_on_samples", "fixture"]
    evidence: list[Evidence]


class ProductVersion(Contract):
    id: UUID
    label: str
    status: Literal["fixture", "draft", "validated", "approved"]
    commit_sha: str | None = None
    runtime_url: str | None = None
    briefing: str
    capabilities: list[Capability]
    limitations: list[str]


class IntegrationSummary(Contract):
    mode: Literal["fixture", "live"]
    repositories: list[Repository]
    proposals: list[Proposal]
    versions: list[ProductVersion]
    next_gate: str


class Scenario(Contract):
    id: UUID
    persona_id: UUID
    active_role: str
    location_id: Literal["library", "classroom", "home", "office"]
    activity: str
    goal: str
    device: Literal["laptop", "phone"]
    time_budget_minutes: int = Field(ge=1, le=60)
    assumptions: list[str]


class SoftwareReviewEvidence(Contract):
    """A review report, not a measured user action or a demographic observation."""

    id: UUID
    kind: Literal["source", "fixture"]
    platform: Literal[
        "reddit", "hacker_news", "github_issue", "app_store", "review_site", "forum", "other", "fixture"
    ]
    external_id: str = Field(min_length=1)
    source_url: HttpUrl | None
    published_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    software_context: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=2000)
    report_type: Literal["self_report", "opinion", "fixture"]
    collection_method: Literal["api", "permitted_export", "manual", "fixture"]
    content_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    selection_context: str = Field(min_length=1)
    extraction_version: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_source_provenance(self):
        fixture_fields = (
            self.platform == "fixture", self.report_type == "fixture", self.collection_method == "fixture"
        )
        if self.kind == "source":
            if any(fixture_fields) or self.source_url is None or self.content_sha256 is None:
                raise ValueError("Source reviews require a URL, content hash and non-fixture provenance")
        elif not all(fixture_fields) or self.source_url is not None or self.content_sha256 is not None:
            raise ValueError("Fixture reviews must be explicit illustrations without real source claims")
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise ValueError("Review publication cannot follow retrieval")
        return self


class SoftwareBehaviorPattern(Contract):
    id: UUID
    dimension: Literal[
        "onboarding", "navigation", "workflow", "error_recovery", "trust", "privacy",
        "pricing", "collaboration", "accessibility", "adoption"
    ]
    tendency: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    agent_policy: str = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    interpretation_confidence: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=1)


class SoftwareBehaviorProfile(Contract):
    status: Literal["review_informed", "fixture"]
    corpus_id: UUID
    corpus_version: str = Field(min_length=1)
    generation_version: str = Field(min_length=1)
    patterns: list[SoftwareBehaviorPattern] = Field(min_length=1)
    evidence: list[SoftwareReviewEvidence] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def behavior_has_resolvable_review_evidence(self):
        evidence_ids = {item.id for item in self.evidence}
        source_keys = {(item.platform, item.external_id) for item in self.evidence}
        if len(evidence_ids) != len(self.evidence) or len(source_keys) != len(self.evidence):
            raise ValueError("Review evidence IDs and external source identities must be unique")
        if len({pattern.id for pattern in self.patterns}) != len(self.patterns):
            raise ValueError("Behavior pattern IDs must be unique")
        expected_kind = "source" if self.status == "review_informed" else "fixture"
        if any(item.kind != expected_kind for item in self.evidence):
            raise ValueError("Behavior status must match every review's provenance")
        for pattern in self.patterns:
            if len(set(pattern.evidence_ids)) != len(pattern.evidence_ids):
                raise ValueError("A behavior pattern cannot count the same review twice")
            if not set(pattern.evidence_ids) <= evidence_ids:
                raise ValueError("Every behavior pattern must reference reviews in its profile")
        return self


class Persona(Contract):
    id: UUID
    synthetic_name: str
    cohort: Literal["undergraduate", "graduate", "faculty", "staff", "resident"]
    roles: list[str]
    skills: list[str]
    goals: list[str]
    constraints: list[str]
    attribute_provenance: dict[str, Literal["sourced_distribution", "scenario_assumption", "fictional_detail"]]
    software_behavior: SoftwareBehaviorProfile
    scenario: Scenario


class Task(Contract):
    id: UUID
    scenario_id: UUID
    capability_ids: list[UUID]
    goal: str
    initial_state_ref: str
    check_id: str
    task_version: str
    action_budget: int = Field(ge=1, le=8)


class ExperimentCounts(Contract):
    configured: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def counts_do_not_exceed_population(self):
        total = self.queued + self.running + self.completed + self.failed + self.cancelled
        if total > self.configured:
            raise ValueError("Session counts exceed configured population")
        return self


class Experiment(Contract):
    id: UUID
    population_id: UUID
    product_version_id: UUID
    status: Literal["fixture", "queued", "running", "completed", "failed", "cancelled"]
    counts: ExperimentCounts
    inference_profile: dict[str, Any]


class Feedback(Contract):
    id: UUID
    persona_id: UUID
    session_id: UUID
    initial_relevance: Literal["low", "medium", "high"]
    post_trial_relevance: Literal["low", "medium", "high"]
    decision: Literal["stop", "continue"]
    useful_parts: list[str]
    barriers: list[str]
    suggested_changes: list[str]
    evidence_action_ids: list[UUID]
    reason: str
    synthetic: Literal[True] = True


class Action(Contract):
    id: UUID
    session_id: UUID
    sequence: int = Field(ge=1)
    timestamp: datetime
    kind: Literal["click", "type", "select", "scroll", "navigate", "stop", "check"]
    target: str | None = None
    result: str
    artifact_ref: str | None = None


class Session(Contract):
    id: UUID
    experiment_id: UUID
    persona_id: UUID
    product_version_id: UUID
    status: Literal["fixture", "queued", "running", "completed", "failed", "cancelled"]
    outcome: Literal["not_run", "success", "application_failure", "infrastructure_failure", "irrelevant"]
    stop_reason: str | None = None
    actions: list[Action]
    feedback: Feedback | None = None
    stream_mode: Literal["unavailable", "live", "replay", "fixture"]


class PersonaSummary(Contract):
    mode: Literal["fixture", "live"]
    target_population: Literal[500] = 500
    featured_count: Literal[10] = 10
    personas: list[Persona]
    experiments: list[Experiment]
    sessions: list[Session]
    next_gate: str

    @model_validator(mode="after")
    def live_personas_have_review_informed_behavior(self):
        if self.mode == "live" and any(
            persona.software_behavior.status != "review_informed" for persona in self.personas
        ):
            raise ValueError("Live personas require review-informed software behavior")
        return self


class Improvement(Contract):
    id: UUID
    title: str
    issue: str
    supporting_session_ids: list[UUID]
    severity: int = Field(ge=1, le=5)
    affected_share: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    estimated_effort_hours: float = Field(gt=0)
    acceptance_check: str
    allowed_paths: list[str]
    status: Literal["fixture", "proposed", "reviewed", "patched", "approved", "rejected"]


class EvolutionSummary(Contract):
    mode: Literal["fixture", "live"]
    roles: list[str]
    improvements: list[Improvement]
    matched_v1: int = Field(ge=0)
    matched_v2: int = Field(ge=0)
    next_gate: str


class Job(Contract):
    id: UUID
    kind: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "fixture"]
    fixture: bool


class ErrorDetail(Contract):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(Contract):
    error: ErrorDetail
    request_id: str


class StreamEvent(Contract):
    session_id: UUID
    sequence: int = Field(ge=0)
    timestamp: datetime
    type: Literal["state", "action", "frame", "heartbeat", "error"]
    mode: Literal["live", "replay", "fixture"]
    payload: dict[str, Any]
