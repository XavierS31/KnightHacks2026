from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.features.evolution.analysis import analyze_fixture_sessions
from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.models import AnalysisReport, AnalysisRequest
from backend.app.features.evolution.repository import ExperimentNotFound, SessionEvidenceRepository
from backend.app.features.evolution.role_analysis import (
    AnalysisInputTooLarge,
    RoleOutputRejected,
    analyze_with_roles,
)
from backend.app.shared.contracts import EvolutionSummary
from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.fixtures import EXPERIMENT, IMPROVEMENT, SESSIONS
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings, get_settings

router = APIRouter(tags=["evolution"])
UNCONFIGURED_INFERENCE = {"INFERENCE_NOT_CONFIGURED", "BUDGET_NOT_APPROVED", "INVALID_MODEL_ID"}


@lru_cache
def get_inference() -> HuggingFaceInference:
    """One adapter per process, as the shared adapter requires."""
    return HuggingFaceInference(get_settings())


@lru_cache
def get_database() -> NeonDatabase:
    return NeonDatabase(get_settings())


def get_evidence_repository(
    database: Annotated[NeonDatabase, Depends(get_database)],
) -> SessionEvidenceRepository:
    return SessionEvidenceRepository(database)


def failure(status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "code": code, "message": message, "retryable": retryable})


@router.get("/evolution/summary", response_model=EvolutionSummary)
def summary():
    return EvolutionSummary(mode="fixture", roles=["Analyst", "Prioritizer", "UX reviewer", "Implementer", "QA reviewer"],
                            improvements=[IMPROVEMENT], matched_v1=0, matched_v2=0,
                            next_gate="Aggregate real feedback before proposing a bounded patch.")


@router.post("/experiments/{experiment_id}/analysis", response_model=AnalysisReport)
async def analyze(
    experiment_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    inference: Annotated[HuggingFaceInference, Depends(get_inference)],
    repository: Annotated[SessionEvidenceRepository, Depends(get_evidence_repository)],
    request: AnalysisRequest | None = None,
):
    submitted = None if request is None else request.sessions
    try:
        if settings.app_mode == "fixture":
            if experiment_id != EXPERIMENT.id:
                raise failure(404, "EXPERIMENT_NOT_FOUND", "No stored fixture experiment has this ID.")
            return analyze_fixture_sessions(experiment_id, SESSIONS if submitted is None else submitted)
        if submitted is not None:
            raise failure(422, "SUBMITTED_SESSIONS_FORBIDDEN",
                          "Live analysis reads persisted sessions only.")
        sessions = repository.load(experiment_id)
        return await analyze_with_roles(experiment_id, sessions, inference)
    except EvidenceMismatch as exc:
        raise failure(422, "EVIDENCE_MISMATCH", str(exc)) from None
    except ExperimentNotFound as exc:
        raise failure(404, "EXPERIMENT_NOT_FOUND", str(exc)) from None
    except AnalysisInputTooLarge as exc:
        raise failure(422, "ANALYSIS_INPUT_TOO_LARGE", str(exc)) from None
    except DatabaseUnavailable as exc:
        raise failure(503, "DATABASE_UNAVAILABLE", str(exc), retryable=True) from None
    except InferenceError as exc:
        status = 503 if exc.code in UNCONFIGURED_INFERENCE else 502
        raise failure(status, exc.code, "A structured analysis role could not complete.",
                      retryable=exc.retryable) from None
    except RoleOutputRejected as exc:
        raise failure(502, "ROLE_OUTPUT_REJECTED", f"{exc.code}: {exc}") from None


@router.post("/patch-runs/{patch_run_id}/approve")
def approve_patch(patch_run_id: UUID):
    raise HTTPException(status_code=409, detail={
        "code": "REVIEW_REQUIRED",
        "message": "No patch can be promoted before persisted regressions and human review.",
    })
