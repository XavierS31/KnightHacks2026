from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.features.evolution.analysis import analyze_fixture_sessions
from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.lifecycle import (
    LifecycleError,
    PatchLifecycle,
    fixed_checks_digest,
)
from backend.app.features.evolution.models import (
    ActorRequest,
    AnalysisReport,
    AnalysisRequest,
    BaseVersion,
    ComparisonReport,
    ComparisonSubmission,
    PatchRun,
    PatchRunCreate,
    PatchSubmission,
    RegressionSubmission,
    RetestRequest,
    RetestRequestCreate,
)
from backend.app.features.evolution.repository import ExperimentNotFound, SessionEvidenceRepository
from backend.app.features.evolution.retest import (
    RetestError,
    RetestRegistry,
    build_retest_request,
    compare_versions,
)
from backend.app.features.evolution.role_analysis import (
    AnalysisInputTooLarge,
    RoleOutputRejected,
    analyze_with_roles,
)
from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
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


lifecycle = PatchLifecycle()
LIFECYCLE_STATUS = {
    "PATCH_RUN_NOT_FOUND": 404,
    "ACTOR_NOT_ALLOWED": 403,
    "TRANSITION_NOT_ALLOWED": 409,
    "PATCH_OUTSIDE_SCOPE": 422,
    "REGRESSION_MISMATCH": 422,
}


def frozen_v1_base() -> BaseVersion:
    """Read A's frozen v1 manifest. The lifecycle keeps a copy and never writes it."""
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    return BaseVersion(
        version_id=handoff.version.id, label=handoff.version.label,
        fixed_check_ids=[check.id for check in handoff.checks],
        fixed_checks_sha256=fixed_checks_digest(
            [check.model_dump(mode="json") for check in handoff.checks]))


def lifecycle_call(step, *args, **kwargs) -> PatchRun:
    try:
        return step(*args, **kwargs)
    except LifecycleError as exc:
        raise HTTPException(status_code=LIFECYCLE_STATUS[exc.code], detail={
            "code": exc.code, "message": str(exc)}) from None


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


@router.post("/improvements/{improvement_id}/patch-runs", response_model=PatchRun, status_code=201)
def create_patch_run(improvement_id: UUID, request: PatchRunCreate):
    if request.improvement.id != improvement_id:
        raise HTTPException(status_code=422, detail={
            "code": "IMPROVEMENT_MISMATCH", "message": "Body improvement ID must match the route."})
    return lifecycle_call(lifecycle.propose, request.improvement, frozen_v1_base(), request.actor)


@router.get("/patch-runs/{patch_run_id}", response_model=PatchRun)
def get_patch_run(patch_run_id: UUID):
    return lifecycle_call(lifecycle.get, patch_run_id)


@router.post("/patch-runs/{patch_run_id}/review", response_model=PatchRun)
def review_patch_run(patch_run_id: UUID, request: ActorRequest):
    return lifecycle_call(lifecycle.review, patch_run_id, request.actor, request.note)


@router.post("/patch-runs/{patch_run_id}/patch", response_model=PatchRun)
def submit_patch(patch_run_id: UUID, request: PatchSubmission):
    return lifecycle_call(lifecycle.submit_patch, patch_run_id, request.actor, request.files)


@router.post("/patch-runs/{patch_run_id}/regression", response_model=PatchRun)
def record_regression(patch_run_id: UUID, request: RegressionSubmission):
    return lifecycle_call(lifecycle.record_regression, patch_run_id, request.actor,
                          request.patch_sha256, request.results)


@router.post("/patch-runs/{patch_run_id}/approve", response_model=PatchRun)
def approve_patch(patch_run_id: UUID, request: ActorRequest):
    return lifecycle_call(lifecycle.approve, patch_run_id, request.actor, request.note)


@router.post("/patch-runs/{patch_run_id}/reject", response_model=PatchRun)
def reject_patch(patch_run_id: UUID, request: ActorRequest):
    return lifecycle_call(lifecycle.reject, patch_run_id, request.actor, request.note)


@router.post("/patch-runs/{patch_run_id}/rollback", response_model=PatchRun)
def rollback_patch(patch_run_id: UUID, request: ActorRequest):
    return lifecycle_call(lifecycle.rollback, patch_run_id, request.actor, request.note)


retests = RetestRegistry()
RETEST_STATUS = {
    "RETEST_REQUEST_NOT_FOUND": 404,
    "RETEST_NOT_ALLOWED": 409,
    "RETEST_MISMATCH": 422,
}


def retest_call(settings: Settings, step, submitted: tuple = ()):
    """Submitted records are explicit fixtures; live retests need durable identity records."""
    if settings.app_mode != "fixture":
        raise failure(503, "DURABLE_TRIAL_RECORDS_REQUIRED",
                      "Live retests read persisted trial identities, which are not stored yet.")
    if any(run.experiment.status != "fixture" for run in submitted):
        raise failure(422, "SUBMITTED_SESSIONS_FORBIDDEN", "Submitted experiments must be fixtures.")
    try:
        return step()
    except RetestError as exc:
        raise failure(RETEST_STATUS[exc.code], exc.code, str(exc)) from None
    except LifecycleError as exc:
        raise failure(LIFECYCLE_STATUS[exc.code], exc.code, str(exc)) from None
    except EvidenceMismatch as exc:
        raise failure(422, "EVIDENCE_MISMATCH", str(exc)) from None


@router.post("/patch-runs/{patch_run_id}/retest-requests", response_model=RetestRequest,
             status_code=201)
def create_retest_request(patch_run_id: UUID, request: RetestRequestCreate,
                          settings: Annotated[Settings, Depends(get_settings)]):
    return retest_call(settings, lambda: retests.save(
        build_retest_request(lifecycle.get(patch_run_id), request.v1)), submitted=(request.v1,))


@router.get("/retest-requests/{retest_request_id}", response_model=RetestRequest)
def get_retest_request(retest_request_id: UUID, settings: Annotated[Settings, Depends(get_settings)]):
    return retest_call(settings, lambda: retests.get(retest_request_id))


@router.post("/retest-requests/{retest_request_id}/comparison", response_model=ComparisonReport)
def compare_retest(retest_request_id: UUID, request: ComparisonSubmission,
                   settings: Annotated[Settings, Depends(get_settings)]):
    return retest_call(settings, lambda: compare_versions(
        retests.get(retest_request_id), request.v1, request.v2), submitted=(request.v1, request.v2))
