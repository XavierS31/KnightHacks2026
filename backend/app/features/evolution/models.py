"""Feature-local contracts for evidence-backed feedback analysis."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.app.shared.contracts import Contract, Session

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
