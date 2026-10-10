"""Feature-local contracts for the offline analysis starter and the improvement lifecycle."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.shared.contracts import Contract, Improvement, Session


class AnalysisRequest(Contract):
    mode: Literal["fixture"] = "fixture"
    sessions: list[Session] | None = None


class FeedbackCluster(Contract):
    id: UUID
    category: Literal["product", "infrastructure", "relevance"]
    issue: str
    supporting_session_ids: list[UUID]
    evidence_action_ids: list[UUID]
    severity: int = Field(ge=1, le=5)
    affected_share: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    estimated_effort_hours: float = Field(gt=0)
    priority_score: float = Field(ge=0)
    patch_eligible: bool


class AnalysisReport(Contract):
    experiment_id: UUID
    mode: Literal["fixture"] = "fixture"
    method: Literal["deterministic_evidence_grouping"] = "deterministic_evidence_grouping"
    inference_used: Literal[False] = False
    sessions_seen: int = Field(ge=0)
    feedback_present: int = Field(ge=0)
    denominator: int = Field(ge=0)
    clusters: list[FeedbackCluster]
    limitations: list[str]
    next_gate: str


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
