from contextlib import contextmanager
from threading import Lock
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from backend.app.features.integration.discovery import (
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryStore,
    discovery_error,
)
from backend.app.features.integration.discovery_repository import DiscoveryRepository
from backend.app.features.integration.opportunities import (
    OpportunityDecision,
    OpportunityReport,
    OpportunityRequest,
    OpportunityStore,
    discover_opportunities,
    fixture_report,
)
from backend.app.features.integration.proposals import (
    Extraction,
    IntegrationInference,
    InterpretationStore,
    ProposalPreview,
    ProposalRequest,
)
from backend.app.features.integration.sources import SourceRequest, SourceSnapshot, SourceStore
from backend.app.features.integration.studies import StudyEngine
from backend.app.features.integration.study_models import ResearchStudy, StudyRequest
from backend.app.shared.contracts import IntegrationSummary
from backend.app.shared.database import (
    DatabaseUnavailable,
    NeonDatabase,
    RecordConflict,
    RecordInvalid,
    RecordMissing,
)
from backend.app.shared.fixtures import PROPOSAL, REPOSITORIES, VERSION
from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import Settings, get_settings

router = APIRouter(tags=["integration"])
store = DiscoveryStore()
source_store = SourceStore()
interpretations = InterpretationStore()
opportunities = OpportunityStore()
_databases: dict[str, NeonDatabase] = {}
_databases_lock = Lock()


def get_records(settings: Settings = Depends(get_settings)) -> DiscoveryRepository | None:
    """Durable I1 records in live mode with a configured database; otherwise memory only."""
    url = settings.database_url.get_secret_value()
    if settings.app_mode != "live" or not url:
        return None
    with _databases_lock:
        if url not in _databases:
            _databases[url] = NeonDatabase(settings)
        return DiscoveryRepository(_databases[url])


Records = Annotated[DiscoveryRepository | None, Depends(get_records)]


@contextmanager
def storage_errors():
    try:
        yield
    except DatabaseUnavailable:
        raise discovery_error(503, "DISCOVERY_STORAGE_UNAVAILABLE",
                              "Durable discovery storage is unavailable; nothing was stored.", True) from None
    except (RecordConflict, RecordInvalid, RecordMissing):
        raise discovery_error(409, "DISCOVERY_RECORD_REJECTED",
                              "Durable storage rejected the record; nothing was stored.") from None


studies = StudyEngine(discovery=store, snapshot_store=source_store)


@router.post("/research-studies", response_model=ResearchStudy, status_code=202)
async def start_research_study(request: StudyRequest, records: Records, settings: Settings = Depends(get_settings)):
    return studies.start(request, settings, records)


@router.get("/research-studies/{study_id}", response_model=ResearchStudy)
async def get_research_study(study_id: UUID):
    return studies.get(study_id).model_copy(deep=True)


@router.post("/research-studies/{study_id}/cancel", response_model=ResearchStudy)
async def cancel_research_study(study_id: UUID):
    return studies.cancel(study_id)


def inference_failure(code):
    messages = {
        "FIXTURE_INFERENCE_FORBIDDEN": "Set APP_MODE=live on the server to enable HF interpretation.",
        "INFERENCE_NOT_CONFIGURED": "Configure server-side HF model, provider and token before extraction.",
        "BUDGET_NOT_APPROVED": "A positive, approved inference allowance is required.",
        "INTEGRATION_BUDGET_EXHAUSTED": "Developer A's local inference allowance is exhausted.",
        "INTEGRATION_BUDGET_BUSY": "Another request is reserving the allowance; retry shortly.",
        "INTEGRATION_BUDGET_INVALID": "The local allowance ledger needs inspection before more calls.",
        "INTEGRATION_PRICING_UNVERIFIED": "This model/provider has no verified Developer A reservation rate.",
        "INTEGRATION_PROMPT_TOO_LARGE": "Source context exceeds the approved request bound.",
        "NO_DOCUMENTED_SOURCES": "No usable README or documentation excerpt was collected.",
        "DUPLICATE_EXTRACTION": "Select distinct extraction records.",
        "DUPLICATE_REPOSITORY": "Select distinct repositories for a proposal.",
        "UNSUPPORTED_OPPORTUNITY_EVIDENCE": "The model used unknown or mismatched evidence or repo roles. No opportunity was retained.",
    }
    return discovery_error(409 if code in messages else 502, code,
                           messages.get(code, "HF output did not pass the required checks; no result was retained."))


@router.post("/discovery-runs", response_model=DiscoveryRun, status_code=201)
async def create_discovery(request: DiscoveryRequest, records: Records,
                           settings: Settings = Depends(get_settings)):
    if request.mode == "live" and settings.app_mode != "live":
        raise discovery_error(409, "LIVE_DISCOVERY_DISABLED", "Set APP_MODE=live on the server to enable real GitHub reads.")
    with storage_errors():
        return await store.create(request, settings.github_token.get_secret_value(), settings.artifact_root, records)


@router.get("/discovery-runs/{run_id}", response_model=DiscoveryRun)
def get_discovery(run_id: UUID, records: Records):
    with storage_errors():
        return store.get(run_id, records)


@router.get("/integration/summary", response_model=IntegrationSummary)
def summary(settings: Settings = Depends(get_settings)):
    return IntegrationSummary(mode="fixture", repositories=REPOSITORIES,
                              proposals=[PROPOSAL], versions=[VERSION],
                              next_gate="Discover opportunities around an anchor repo; No prototype is selected; validate a new opportunity before persona trials.")


@router.post("/discovery-runs/{run_id}/repositories/{repository_id}/sources",
             response_model=SourceSnapshot, status_code=201)
async def collect_sources(run_id: UUID, repository_id: UUID, request: SourceRequest, records: Records,
                          settings: Settings = Depends(get_settings)):
    run = await run_in_threadpool(get_discovery, run_id, records)
    if settings.app_mode != "live" or run.mode != "live":
        raise discovery_error(409, "LIVE_SOURCES_DISABLED", "Source collection requires a live discovery run and server mode.")
    repository = next((repo for repo in run.repositories if repo.id == repository_id), None)
    if repository is None:
        raise discovery_error(404, "REPOSITORY_NOT_FOUND", "Repository does not belong to this discovery run.")
    with storage_errors():
        return await source_store.create(run_id, repository, request,
                                         settings.github_token.get_secret_value(), records)


@router.get("/source-snapshots/{snapshot_id}", response_model=SourceSnapshot)
def get_sources(snapshot_id: UUID, records: Records):
    with storage_errors():
        return source_store.get(snapshot_id, records)


@router.post("/source-snapshots/{snapshot_id}/extractions", response_model=Extraction, status_code=201)
async def extract_sources(snapshot_id: UUID, records: Records, settings: Settings = Depends(get_settings)):
    snapshot = await run_in_threadpool(get_sources, snapshot_id, records)
    service = IntegrationInference(settings)
    try:
        result = await service.extract(snapshot)
        with storage_errors():
            return await run_in_threadpool(interpretations.add_extraction, result, records)
    except InferenceError as exc:
        raise inference_failure(exc.code) from None
    finally:
        await service.close()


@router.get("/extractions/{extraction_id}", response_model=Extraction)
def get_extraction(extraction_id: UUID, records: Records):
    with storage_errors():
        extraction = interpretations.get_extraction(extraction_id, records)
    if extraction is None:
        raise discovery_error(404, "EXTRACTION_NOT_FOUND", "Extraction is unknown or no longer retained.")
    return extraction


@router.post("/proposal-previews", response_model=ProposalPreview, status_code=201)
async def preview_proposals(request: ProposalRequest, records: Records,
                            settings: Settings = Depends(get_settings)):
    extractions = [await run_in_threadpool(get_extraction, identity, records)
                   for identity in request.extraction_ids]
    service = IntegrationInference(settings)
    try:
        result = await service.propose(extractions)
        with storage_errors():
            return await run_in_threadpool(interpretations.add_preview, result, records)
    except InferenceError as exc:
        raise inference_failure(exc.code) from None
    finally:
        await service.close()


@router.get("/proposal-previews/{preview_id}", response_model=ProposalPreview)
def get_preview(preview_id: UUID, records: Records):
    with storage_errors():
        preview = interpretations.get_preview(preview_id, records)
    if preview is None:
        raise discovery_error(404, "PROPOSAL_PREVIEW_NOT_FOUND", "Proposal preview is unknown or no longer retained.")
    return preview


@router.post("/opportunity-reports", response_model=OpportunityReport, status_code=201)
async def create_opportunity_report(request: OpportunityRequest, settings: Settings = Depends(get_settings)):
    snapshots = [source_store.get(identity) for identity in [request.anchor_snapshot_id, *request.supporting_snapshot_ids]]
    # More substantial structured proposals need time; keep B's shared defaults unchanged.
    service = IntegrationInference(settings.model_copy(update={
        "hf_request_timeout_seconds": max(60, settings.hf_request_timeout_seconds),
    }))
    try:
        report = await discover_opportunities(service, request, snapshots)
        opportunities.retain(report)
        return report
    except InferenceError as exc:
        raise inference_failure(exc.code) from None
    finally:
        await service.close()


@router.post("/integration/opportunity-demo", response_model=OpportunityReport, status_code=201)
def opportunity_demo():
    report = fixture_report()
    opportunities.retain(report)
    return report


@router.get("/opportunity-reports/{report_id}", response_model=OpportunityReport)
def get_opportunity_report(report_id: UUID):
    if report_id not in opportunities.reports:
        raise discovery_error(404, "OPPORTUNITY_REPORT_NOT_FOUND", "Report is unknown or no longer retained.")
    return opportunities.reports[report_id]


@router.post("/opportunity-reports/{report_id}/cards/{card_id}/decision", response_model=OpportunityReport)
def decide_opportunity(report_id: UUID, card_id: UUID, request: OpportunityDecision):
    report = get_opportunity_report(report_id)
    card = next((item for item in report.opportunities if item.id == card_id), None)
    if card is None:
        raise discovery_error(404, "OPPORTUNITY_CARD_NOT_FOUND", "Card does not belong to this report.")
    card.decision = request.decision
    card.decision_note = request.note
    return report
