"""Feature-local contracts for evidence-backed feedback analysis and the improvement lifecycle."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.app.shared.contracts import Contract, Experiment, Improvement, Session

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


# Matched v2 retest (E3). C freezes v1 identities; B runs them on v2; C compares.
TrialOutcome = Literal["success", "application_failure", "infrastructure_failure", "irrelevant", "not_run"]
TIME_BASIS = "agent wall clock between first and last recorded action; not human time"


class TrialIdentity(Contract):
    """Everything that must stay fixed between a persona's v1 and v2 attempts."""

    persona_id: UUID
    population_version: str = Field(min_length=1)
    behavior_generation_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    scenario_id: UUID
    task_id: UUID
    task_version: str = Field(min_length=1)
    check_id: str = Field(min_length=1)
    initial_state_ref: str = Field(min_length=1)
    action_budget: int = Field(ge=1, le=8)
    time_budget_minutes: int = Field(ge=1, le=60)


class TrialAttempt(Contract):
    """One executed (or attempted) session with the identity it ran under.

    Mandatory attempts form the 500-person comparison. A continuation attempt is optional
    and follows a mandatory attempt whose feedback chose to continue.
    """

    identity: TrialIdentity
    phase: Literal["mandatory", "continuation"]
    session: Session


class ExperimentRun(Contract):
    experiment: Experiment
    attempts: list[TrialAttempt] = Field(max_length=1000)


class RetestRequest(Contract):
    """C's handoff to B: run each frozen v1 identity once on the approved v2."""

    id: UUID
    mode: Literal["fixture", "live"]
    patch_run_id: UUID
    base_version_id: UUID
    candidate_version_id: UUID
    candidate_patch_sha256: str = Field(pattern=SHA256)
    fixed_check_ids: list[str] = Field(min_length=1)
    fixed_checks_sha256: str = Field(pattern=SHA256)
    population_id: UUID
    v1_experiment_id: UUID
    v1_records_sha256: str = Field(pattern=SHA256)
    target_population: Literal[500] = 500
    identities: list[TrialIdentity]
    identity_shortfall: int = Field(ge=0)
    inference_profile: dict[str, Any]
    instructions: list[str]


class RetestRequestCreate(Contract):
    v1: ExperimentRun


class ComparisonSubmission(Contract):
    v1: ExperimentRun
    v2: ExperimentRun


class Rate(Contract):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None = Field(default=None, ge=0, le=1)


class OutcomeCounts(Contract):
    """Every expected identity lands in exactly one bucket; the buckets sum to the target."""

    success: int = Field(ge=0)
    application_failure: int = Field(ge=0)
    infrastructure_failure: int = Field(ge=0)
    irrelevant: int = Field(ge=0)
    not_run: int = Field(ge=0)
    identity_mismatch: int = Field(default=0, ge=0)
    no_attempt: int = Field(ge=0)


class FeedbackCounts(Contract):
    present: int = Field(ge=0)
    missing: int = Field(ge=0)
    chose_continue: int = Field(ge=0)
    post_trial_relevance: dict[Literal["low", "medium", "high"], int]


class ModelTime(Contract):
    """Elapsed agent time. It is never an estimate of how long a human would take."""

    basis: Literal[TIME_BASIS] = TIME_BASIS
    sessions_measured: int = Field(ge=0)
    median_seconds: float | None = Field(default=None, ge=0)


class VersionResult(Contract):
    version_id: UUID
    experiment_id: UUID
    outcomes: OutcomeCounts
    infrastructure_stop_reasons: dict[str, int]
    success_over_target: Rate
    feedback: FeedbackCounts
    model_time: ModelTime


class PairResult(Contract):
    persona_id: UUID
    status: Literal["matched", "missing_v2", "identity_mismatch"]
    mismatched_fields: list[str]
    v1_session_id: UUID
    v2_session_id: UUID | None
    v1_outcome: TrialOutcome
    v2_outcome: TrialOutcome | None


class Transition(Contract):
    v1_outcome: TrialOutcome
    v2_outcome: TrialOutcome
    count: int = Field(ge=1)


class ConfigurationChange(Contract):
    key: str
    v1_value: Any
    v2_value: Any


class ContinuationResult(Contract):
    """Optional continuation attempts. They never enter the mandatory denominators."""

    v1_eligible: int = Field(ge=0)
    v1_attempted: int = Field(ge=0)
    v1_outcomes: OutcomeCounts
    v2_eligible: int = Field(ge=0)
    v2_attempted: int = Field(ge=0)
    v2_outcomes: OutcomeCounts


class ComparisonReport(Contract):
    retest_request_id: UUID
    mode: Literal["fixture", "live"]
    target_population: Literal[500] = 500
    expected_identities: int = Field(ge=0)
    matched_pairs: int = Field(ge=0)
    completed_pairs: int = Field(ge=0)
    missing_v2: int = Field(ge=0)
    identity_mismatches: int = Field(ge=0)
    unexpected_v2_session_ids: list[UUID]
    matched_complete: bool
    v1: VersionResult
    v2: VersionResult
    success_over_completed_pairs: dict[Literal["v1", "v2"], Rate]
    transitions: list[Transition]
    inference_configuration_changed: bool
    inference_changes: list[ConfigurationChange]
    continuation: ContinuationResult
    pairs: list[PairResult]
    limitations: list[str]
    next_gate: str
