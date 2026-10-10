from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.features.evolution.analysis import analyze_fixture_sessions
from backend.app.features.evolution.analysis_repository import AnalysisRepository
from backend.app.features.evolution.boundary import (
    PATCHABLE_PATHS,
    BoundaryDrift,
    frozen_v1_sources,
)
from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.implementer import apply_edits, propose_edits
from backend.app.features.evolution.improvement_intake import validate_improvement
from backend.app.features.evolution.lifecycle import (
    LifecycleError,
    PatchLifecycle,
    fixed_checks_digest,
)
from backend.app.features.evolution.models import (
    Actor,
    ActorRequest,
    AnalysisReport,
    AnalysisRequest,
    BaseVersion,
    BoundedEdit,
    ComparisonReport,
    ComparisonSubmission,
    EditSubmission,
    PatchRun,
    PatchRunCreate,
    PatchSubmission,
    ReleaseCreate,
    RetestRequest,
    RetestRequestCreate,
    RoleRun,
)
from backend.app.features.evolution.qa import QaUnavailable, frozen_image_id, run_regression
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
from backend.app.shared.database import (
    DatabaseUnavailable,
    NeonDatabase,
    RecordConflict,
    RecordInvalid,
    RecordMissing,
)
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


def get_analysis_repository(
    database: Annotated[NeonDatabase, Depends(get_database)],
) -> AnalysisRepository:
    return AnalysisRepository(database)


def failure(status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "code": code, "message": message, "retryable": retryable})


lifecycle = PatchLifecycle(PATCHABLE_PATHS)
LIFECYCLE_STATUS = {
    "PATCH_RUN_NOT_FOUND": 404,
    "ACTOR_NOT_ALLOWED": 403,
    "TRANSITION_NOT_ALLOWED": 409,
    "PATCH_OUTSIDE_SCOPE": 422,
    "EDIT_CONFLICT": 422,
    "REGRESSION_MISMATCH": 422,
}


def get_qa_image(settings: Annotated[Settings, Depends(get_settings)]) -> str:
    """QA runs only against the frozen v1 product image."""
    try:
        return frozen_image_id(settings.artifact_root)
    except QaUnavailable as exc:
        raise failure(503, "QA_UNAVAILABLE", str(exc), retryable=True) from None


def frozen_v1_base() -> BaseVersion:
    """Read A's frozen v1 manifest. The lifecycle keeps a copy and never writes it."""
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    return BaseVersion(
        version_id=handoff.version.id, label=handoff.version.label,
        fixed_check_ids=[check.id for check in handoff.checks],
        fixed_checks_sha256=fixed_checks_digest(
            [check.model_dump(mode="json") for check in handoff.checks]))


def lifecycle_call(step, *args, **kwargs):
    try:
        return step(*args, **kwargs)
    except LifecycleError as exc:
        raise HTTPException(status_code=LIFECYCLE_STATUS[exc.code], detail={
            "code": exc.code, "message": str(exc)}) from None
    except BoundaryDrift as exc:
        raise failure(409, "V1_DRIFT", str(exc)) from None


def submit_edits(run: PatchRun, actor: Actor, edits: list[BoundedEdit],
                 implementer_run: RoleRun | None = None) -> PatchRun:
    files = lifecycle_call(apply_edits, edits, run.allowed_paths, lifecycle_call(frozen_v1_sources))
    return lifecycle_call(lifecycle.submit_patch, run.id, actor, files, edits, implementer_run)


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
    analyses: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
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
        report = await analyze_with_roles(experiment_id, sessions, inference)
        analyses.save_report(report, sessions)
        return report
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
    except (RecordInvalid, RecordConflict, RecordMissing) as exc:
        raise failure(409, "ANALYSIS_STORAGE_REJECTED", str(exc)) from None


@router.post("/improvements/{improvement_id}/patch-runs", response_model=PatchRun, status_code=201)
def create_patch_run(
    improvement_id: UUID, request: PatchRunCreate,
    settings: Annotated[Settings, Depends(get_settings)],
    analyses: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    repository: Annotated[SessionEvidenceRepository, Depends(get_evidence_repository)],
):
    if request.improvement.id != improvement_id:
        raise HTTPException(status_code=422, detail={
            "code": "IMPROVEMENT_MISMATCH", "message": "Body improvement ID must match the route."})
    base = frozen_v1_base()
    analysis_record_id = None
    if settings.app_mode == "live":
        try:
            record, report = analyses.report_for_proposal(improvement_id)
            sessions = repository.load(report.experiment_id)
            analyses.validate_report_evidence(record, sessions)
            validate_improvement(request.improvement, report, sessions, base.version_id)
            analysis_record_id = record.id
        except RecordMissing as exc:
            raise failure(409, "E1_PROPOSAL_REQUIRED", str(exc)) from None
        except (RecordInvalid, EvidenceMismatch, ValueError) as exc:
            raise failure(422, "E1_EVIDENCE_MISMATCH", str(exc)) from None
        except ExperimentNotFound as exc:
            raise failure(409, "E1_PROPOSAL_REQUIRED", str(exc)) from None
        except DatabaseUnavailable as exc:
            raise failure(503, "DATABASE_UNAVAILABLE", str(exc), retryable=True) from None
    return lifecycle_call(lifecycle.propose, request.improvement, base, request.actor,
                          analysis_record_id)


@router.get("/patch-runs/{patch_run_id}", response_model=PatchRun)
def get_patch_run(patch_run_id: UUID):
    return lifecycle_call(lifecycle.get, patch_run_id)


@router.post("/patch-runs/{patch_run_id}/review", response_model=PatchRun)
def review_patch_run(patch_run_id: UUID, request: ActorRequest):
    return lifecycle_call(lifecycle.review, patch_run_id, request.actor, request.note)


@router.post("/patch-runs/{patch_run_id}/patch", response_model=PatchRun)
def submit_patch(patch_run_id: UUID, request: PatchSubmission):
    return lifecycle_call(lifecycle.submit_patch, patch_run_id, request.actor, request.files)


@router.post("/patch-runs/{patch_run_id}/edits", response_model=PatchRun)
def submit_patch_edits(patch_run_id: UUID, request: EditSubmission):
    run = lifecycle_call(lifecycle.ready_for_patch, patch_run_id, request.actor)
    return submit_edits(run, request.actor, request.edits)


@router.post("/patch-runs/{patch_run_id}/implement", response_model=PatchRun)
async def implement_patch(
    patch_run_id: UUID, request: ActorRequest,
    inference: Annotated[HuggingFaceInference, Depends(get_inference)],
):
    """The HF implementer proposes bounded edits; the deterministic tool applies them."""
    run = lifecycle_call(lifecycle.ready_for_patch, patch_run_id, request.actor)
    if run.component_run_ids:
        raise failure(409, "TRANSITION_NOT_ALLOWED", "A release composes its components' edits.")
    try:
        edits, role_run = await propose_edits(inference, run, lifecycle_call(frozen_v1_sources))
    except InferenceError as exc:
        status = 503 if exc.code in UNCONFIGURED_INFERENCE else 502
        raise failure(status, exc.code, "The implementer role could not complete.",
                      retryable=exc.retryable) from None
    return submit_edits(run, request.actor, edits, role_run)


@router.post("/releases", response_model=PatchRun, status_code=201)
def create_release(request: ReleaseCreate):
    return lifecycle_call(lifecycle.propose_release, request.run_ids, request.actor)


@router.post("/patch-runs/{patch_run_id}/compose", response_model=PatchRun)
def compose_release(patch_run_id: UUID, request: ActorRequest):
    """The implementer applies each component's edits, in order, to frozen v1."""
    run = lifecycle_call(lifecycle.ready_for_patch, patch_run_id, request.actor)
    return submit_edits(run, request.actor, lifecycle_call(lifecycle.release_edits, run.id))


@router.post("/patch-runs/{patch_run_id}/qa", response_model=PatchRun)
async def run_patch_qa(patch_run_id: UUID, request: ActorRequest,
                       image_id: Annotated[str, Depends(get_qa_image)]):
    """Run the fixed checks in an isolated workspace and record their results."""
    run = lifecycle_call(lifecycle.ready_for_regression, patch_run_id, request.actor)
    try:
        results = await run_regression(run.base, run.patch, image_id)
    except QaUnavailable as exc:
        raise failure(503, "QA_UNAVAILABLE", str(exc), retryable=True) from None
    except BoundaryDrift as exc:
        raise failure(409, "V1_DRIFT", str(exc)) from None
    return lifecycle_call(lifecycle.record_regression, patch_run_id, request.actor,
                          run.patch.sha256, results)


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
