"""Feature-local contracts for the evidence-backed offline analysis starter."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.shared.contracts import Contract, Session


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
