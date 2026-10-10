from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.app.features.evolution.analysis import EvidenceMismatch, analyze_fixture_sessions
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
    PatchRun,
    PatchRunCreate,
    PatchSubmission,
    RegressionSubmission,
)
from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
from backend.app.shared.contracts import EvolutionSummary
from backend.app.shared.fixtures import EXPERIMENT, IMPROVEMENT, SESSIONS

router = APIRouter(tags=["evolution"])
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
