from uuid import UUID

from fastapi import APIRouter, Depends

from backend.app.features.integration.discovery import (
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryStore,
    discovery_error,
)
from backend.app.features.integration.product.handoff import ProductReadiness, readiness
from backend.app.features.integration.proposals import (
    Extraction,
    IntegrationInference,
    InterpretationStore,
    ProposalPreview,
    ProposalRequest,
)
from backend.app.features.integration.sources import SourceRequest, SourceSnapshot, SourceStore
from backend.app.shared.contracts import IntegrationSummary
from backend.app.shared.fixtures import PROPOSAL, REPOSITORIES, VERSION
from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import Settings, get_settings

router = APIRouter(tags=["integration"])
store = DiscoveryStore()
source_store = SourceStore()
interpretations = InterpretationStore()


@router.get('/integration/product-readiness', response_model=ProductReadiness)
def product_readiness(settings: Settings = Depends(get_settings)):
    return readiness(settings.artifact_root)


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
    }
    return discovery_error(409 if code in messages else 502, code,
                           messages.get(code, "HF output did not pass the required checks; no result was retained."))


@router.post("/discovery-runs", response_model=DiscoveryRun, status_code=201)
async def create_discovery(request: DiscoveryRequest, settings: Settings = Depends(get_settings)):
    if request.mode == "live" and settings.app_mode != "live":
        raise discovery_error(409, "LIVE_DISCOVERY_DISABLED", "Set APP_MODE=live on the server to enable real GitHub reads.")
    return await store.create(request, settings.github_token.get_secret_value())


@router.get("/discovery-runs/{run_id}", response_model=DiscoveryRun)
def get_discovery(run_id: UUID):
    return store.get(run_id)


@router.get("/integration/summary", response_model=IntegrationSummary)
def summary(settings: Settings = Depends(get_settings)):
    product = readiness(settings.artifact_root)
    return IntegrationSummary(mode="fixture", repositories=REPOSITORIES,
                              proposals=[PROPOSAL], versions=[VERSION],
                              next_gate=("Use SourceTable's separate validated handoff with B and connect C's durable storage."
                                         if product.version else "Build and verify the separate SourceTable product; these candidate records remain fixtures."))


@router.post("/discovery-runs/{run_id}/repositories/{repository_id}/sources",
             response_model=SourceSnapshot, status_code=201)
async def collect_sources(run_id: UUID, repository_id: UUID, request: SourceRequest,
                          settings: Settings = Depends(get_settings)):
    run = store.get(run_id)
    if settings.app_mode != "live" or run.mode != "live":
        raise discovery_error(409, "LIVE_SOURCES_DISABLED", "Source collection requires a live discovery run and server mode.")
    repository = next((repo for repo in run.repositories if repo.id == repository_id), None)
    if repository is None:
        raise discovery_error(404, "REPOSITORY_NOT_FOUND", "Repository does not belong to this discovery run.")
    return await source_store.create(repository, request, settings.github_token.get_secret_value())


@router.get("/source-snapshots/{snapshot_id}", response_model=SourceSnapshot)
def get_sources(snapshot_id: UUID):
    return source_store.get(snapshot_id)


@router.post("/source-snapshots/{snapshot_id}/extractions", response_model=Extraction, status_code=201)
async def extract_sources(snapshot_id: UUID, settings: Settings = Depends(get_settings)):
    snapshot = source_store.get(snapshot_id)
    service = IntegrationInference(settings)
    try:
        result = await service.extract(snapshot)
        interpretations.retain(interpretations.extractions, result)
        return result
    except InferenceError as exc:
        raise inference_failure(exc.code) from None
    finally:
        await service.close()


@router.get("/extractions/{extraction_id}", response_model=Extraction)
def get_extraction(extraction_id: UUID):
    if extraction_id not in interpretations.extractions:
        raise discovery_error(404, "EXTRACTION_NOT_FOUND", "Extraction is unknown or no longer retained.")
    return interpretations.extractions[extraction_id]


@router.post("/proposal-previews", response_model=ProposalPreview, status_code=201)
async def preview_proposals(request: ProposalRequest, settings: Settings = Depends(get_settings)):
    extractions = [get_extraction(identity) for identity in request.extraction_ids]
    service = IntegrationInference(settings)
    try:
        result = await service.propose(extractions)
        interpretations.retain(interpretations.previews, result)
        return result
    except InferenceError as exc:
        raise inference_failure(exc.code) from None
    finally:
        await service.close()


@router.get("/proposal-previews/{preview_id}", response_model=ProposalPreview)
def get_preview(preview_id: UUID):
    if preview_id not in interpretations.previews:
        raise discovery_error(404, "PROPOSAL_PREVIEW_NOT_FOUND", "Proposal preview is unknown or no longer retained.")
    return interpretations.previews[preview_id]
