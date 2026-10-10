from uuid import UUID

from fastapi import APIRouter, Depends

from backend.app.features.integration.discovery import (
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryStore,
    discovery_error,
)
from backend.app.shared.contracts import IntegrationSummary
from backend.app.shared.fixtures import PROPOSAL, REPOSITORIES, VERSION
from backend.app.shared.settings import Settings, get_settings

router = APIRouter(tags=["integration"])
store = DiscoveryStore()


@router.post("/discovery-runs", response_model=DiscoveryRun, status_code=201)
async def create_discovery(request: DiscoveryRequest, settings: Settings = Depends(get_settings)):
    if request.mode == "live" and settings.app_mode != "live":
        raise discovery_error(409, "LIVE_DISCOVERY_DISABLED", "Set APP_MODE=live on the server to enable real GitHub reads.")
    return await store.create(request, settings.github_token.get_secret_value())


@router.get("/discovery-runs/{run_id}", response_model=DiscoveryRun)
def get_discovery(run_id: UUID):
    return store.get(run_id)


@router.get("/integration/summary", response_model=IntegrationSummary)
def summary():
    return IntegrationSummary(mode="fixture", repositories=REPOSITORIES,
                              proposals=[PROPOSAL], versions=[VERSION],
                              next_gate="Select a real pair and run both repositories independently.")
