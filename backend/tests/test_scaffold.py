import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import create_app
from backend.app.shared.contracts import (
    EvolutionSummary,
    ExperimentCounts,
    IntegrationSummary,
    PersonaSummary,
)


@pytest.fixture
def client():
    return TestClient(create_app())


def test_fixture_journey_has_shared_version_and_no_execution_claims(client):
    integration = IntegrationSummary.model_validate(client.get("/api/v1/integration/summary").json())
    personas = PersonaSummary.model_validate(client.get("/api/v1/personas/summary").json())
    evolution = EvolutionSummary.model_validate(client.get("/api/v1/evolution/summary").json())
    assert integration.mode == personas.mode == evolution.mode == "fixture"
    assert personas.experiments[0].product_version_id == integration.versions[0].id
    assert personas.experiments[0].counts.completed == 0
    assert personas.target_population == 500
    assert len(personas.personas) == personas.featured_count == 10
    assert all(s.outcome == "not_run" for s in personas.sessions)
    assert all(not c.validated for c in integration.versions[0].capabilities)
    assert evolution.matched_v1 == evolution.matched_v2 == 0


def test_impossible_counts_are_rejected():
    with pytest.raises(ValidationError):
        ExperimentCounts(configured=1, queued=1, running=1, completed=0, failed=0)


def test_schema_only_route_uses_error_envelope(client):
    result = client.get("/api/v1/contracts/stream-event")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "SCHEMA_ONLY"


def test_health_does_not_expose_secrets(client):
    result = client.get("/api/v1/health")
    assert result.status_code == 200
    assert "hf_token" not in result.json()
