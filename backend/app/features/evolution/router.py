from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.app.features.evolution.analysis import EvidenceMismatch, analyze_fixture_sessions
from backend.app.features.evolution.models import AnalysisReport, AnalysisRequest
from backend.app.shared.contracts import EvolutionSummary
from backend.app.shared.fixtures import EXPERIMENT, IMPROVEMENT, SESSIONS

router = APIRouter(tags=["evolution"])


@router.get("/evolution/summary", response_model=EvolutionSummary)
def summary():
    return EvolutionSummary(mode="fixture", roles=["Analyst", "Prioritizer", "UX reviewer", "Implementer", "QA reviewer"],
                            improvements=[IMPROVEMENT], matched_v1=0, matched_v2=0,
                            next_gate="Aggregate real feedback before proposing a bounded patch.")


@router.post("/experiments/{experiment_id}/analysis", response_model=AnalysisReport)
def analyze(experiment_id: UUID, request: AnalysisRequest | None = None):
    if experiment_id != EXPERIMENT.id:
        raise HTTPException(status_code=404, detail={
            "code": "EXPERIMENT_NOT_FOUND", "message": "No stored fixture experiment has this ID."})
    sessions = SESSIONS if request is None or request.sessions is None else request.sessions
    try:
        return analyze_fixture_sessions(experiment_id, sessions)
    except EvidenceMismatch as exc:
        raise HTTPException(status_code=422, detail={
            "code": "EVIDENCE_MISMATCH", "message": str(exc)}) from None


@router.post("/patch-runs/{patch_run_id}/approve")
def approve_patch(patch_run_id: UUID):
    raise HTTPException(status_code=409, detail={
        "code": "REVIEW_REQUIRED",
        "message": "No patch can be promoted before persisted regressions and human review.",
    })
