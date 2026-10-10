"""Feature-local contracts for evidence-backed feedback analysis and the improvement lifecycle."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.app.shared.contracts import Contract, Improvement, Session

HeuristicSource = Literal["kickoff_default", "prioritizer_role"]
PRIORITY_FORMULA = "severity × affected_share × evidence_strength ÷ estimated_effort_hours"


class AnalysisRequest(Contract):
    """Submitted sessions are accepted only in fixture mode; live analysis reads persisted rows."""

    sessions: list[Session] | None = None


class FeedbackCluster(Contract):
    id: UUID
    category: Literal["product", "infrastructure", "relevance"]
    issue: str
    supporting_session_ids: list[UUID]
    supporting_feedback_ids: list[UUID]
    evidence_action_ids: list[UUID]
    severity: int = Field(ge=1, le=5)
    severity_source: HeuristicSource
    affected_share: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    estimated_effort_hours: float = Field(gt=0)
    effort_source: HeuristicSource
    priority_score: float = Field(ge=0)
    patch_eligible: bool
    analyst_rationale: str | None = None
    priority_rationale: str | None = None


class ProposalDraft(Contract):
    """A UX reviewer draft. Only supported drafts may enter later lifecycle review."""

    id: UUID
    cluster_id: UUID
    title: str
    problem: str
    change: str
    acceptance_check: str
    supporting_session_ids: list[UUID]
    evidence_action_ids: list[UUID]
    supported: bool
    support_note: str


class RoleRun(Contract):
    """Provenance returned by the shared HF adapter for one structured role call."""

    role: Literal["analyst", "prioritizer", "ux_reviewer"]
    request_id: str
    model_id: str
    provider: str
    prompt_version: str
    configuration_hash: str
    latency_ms: int = Field(ge=0)
    retry_count: int = Field(ge=0)


class AnalysisReport(Contract):
    experiment_id: UUID
    mode: Literal["fixture", "live"]
    method: Literal["deterministic_evidence_grouping", "structured_hf_roles"]
    inference_used: bool
    sessions_seen: int = Field(ge=0)
    feedback_present: int = Field(ge=0)
    denominator: int = Field(ge=0)
    priority_formula: Literal[PRIORITY_FORMULA]
    clusters: list[FeedbackCluster]
    unclustered_feedback_ids: list[UUID]
    proposals: list[ProposalDraft]
    role_runs: list[RoleRun]
    limitations: list[str]
    next_gate: str

    @model_validator(mode="after")
    def method_matches_mode(self):
        if self.mode == "fixture" and (
            self.method != "deterministic_evidence_grouping" or self.inference_used
            or self.role_runs or self.proposals
        ):
            raise ValueError("Fixture analysis cannot claim inference, role runs or proposals")
        if self.mode == "live" and self.method != "structured_hf_roles":
            raise ValueError("Live analysis must use the structured HF roles")
        if self.inference_used != bool(self.role_runs):
            raise ValueError("Inference use must match the recorded role runs")
        return self


# Improvement lifecycle. Order: proposed -> reviewed -> patched -> regression -> approved.
LifecycleState = Literal[
    "proposed", "reviewed", "patched", "regression_passed", "regression_failed",
    "approved", "rejected", "rolled_back",
]
SHA256 = r"^[a-f0-9]{64}$"


class Actor(Contract):
    """Caller-asserted identity; production must bind it to authentication."""

    id: str = Field(min_length=1, max_length=120)
    role: Literal["prioritizer", "implementer", "qa_reviewer", "human_reviewer"]


class BaseVersion(Contract):
    """Frozen v1 identity and its fixed checks. A patch run never changes it."""

    version_id: UUID
    label: str
    fixed_check_ids: list[str] = Field(min_length=1)
    fixed_checks_sha256: str = Field(pattern=SHA256)


class PatchFile(Contract):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=200_000)


class IsolatedPatch(Contract):
    """A changeset held in the run record. It is not written to the v1 tree."""

    files: list[PatchFile]
    sha256: str = Field(pattern=SHA256)


class CheckResult(Contract):
    check_id: str
    passed: bool
    evidence: str = Field(min_length=1, max_length=2000)


class CandidateVersion(Contract):
    id: UUID
    label: str
    base_version_id: UUID
    patch_sha256: str = Field(pattern=SHA256)
    fixed_checks_sha256: str = Field(pattern=SHA256)


class LifecycleEvent(Contract):
    state: LifecycleState
    actor: Actor
    at: datetime
    note: str


class PatchRun(Contract):
    id: UUID
    storage: Literal["memory"] = "memory"
    improvement_id: UUID
    allowed_paths: list[str]
    acceptance_check: str
    base: BaseVersion
    state: LifecycleState
    implementer_id: str | None = None
    patch: IsolatedPatch | None = None
    regression: list[CheckResult] = Field(default_factory=list)
    candidate: CandidateVersion | None = None
    events: list[LifecycleEvent]


class PatchRunCreate(Contract):
    actor: Actor
    improvement: Improvement


class ActorRequest(Contract):
    actor: Actor
    note: str = Field(default="", max_length=2000)


class PatchSubmission(Contract):
    actor: Actor
    files: list[PatchFile] = Field(min_length=1, max_length=20)


class RegressionSubmission(Contract):
    actor: Actor
    patch_sha256: str = Field(pattern=SHA256)
    results: list[CheckResult] = Field(min_length=1)
