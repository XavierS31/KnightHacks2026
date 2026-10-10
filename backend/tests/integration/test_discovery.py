from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.features.integration.discovery import (
    DiscoveryRequest,
    DiscoveryStore,
    GitHubDiscovery,
)
from backend.app.main import create_app
from backend.app.shared.settings import Settings, get_settings


def response_payload():
    return {"total_count": 123, "incomplete_results": False, "items": [
        {"full_name": "example/parser", "stargazers_count": 42, "description": "Parser",
         "html_url": "https://untrusted.invalid/"},
        {"full_name": "example/exporter", "stargazers_count": 12, "description": None},
    ]}


@pytest.mark.asyncio
async def test_github_bounds_cache_and_source_provenance():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.github.com"
        assert request.url.params["per_page"] == "1"
        assert request.url.params["sort"] == "stars"
        assert request.headers["authorization"] == "Bearer server-secret"
        return httpx.Response(200, json=response_payload())

    service = GitHubDiscovery()
    request = DiscoveryRequest(mode="live", limit=1)
    first = await service.search(request, "server-secret", httpx.MockTransport(handler))
    second = await service.search(request, "server-secret", httpx.MockTransport(handler))
    assert len(calls) == 1
    assert len(first[0]) == 1
    repo = first[0][0]
    assert repo.url == "https://github.com/example/parser"
    assert repo.commit_sha is None
    assert repo.evidence[0].kind == "source"
    assert repo.evidence[0].collected_at == first[2] == second[2]
    assert "server-secret" not in repo.model_dump_json()
    assert first[1] == 123
    assert first[3] is False and second[3] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(429, "GITHUB_RATE_LIMIT"), (403, "GITHUB_FORBIDDEN"),
                                       (401, "GITHUB_AUTH_FAILED"), (500, "GITHUB_SOURCE_FAILED")])
async def test_github_errors_are_sanitized(status, code):
    service = GitHubDiscovery()
    with pytest.raises(HTTPException) as error:
        await service.search(DiscoveryRequest(mode="live"), transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="sensitive upstream details")))
    assert error.value.detail["code"] == code
    assert "sensitive" not in str(error.value.detail)
    assert not service.cache


@pytest.mark.asyncio
async def test_timeout_does_not_create_evidence():
    def handler(request):
        raise httpx.ReadTimeout("sensitive", request=request)

    service = GitHubDiscovery()
    with pytest.raises(HTTPException) as error:
        await service.search(DiscoveryRequest(mode="live"), transport=httpx.MockTransport(handler))
    assert error.value.detail["code"] == "GITHUB_UNAVAILABLE"
    assert not service.cache


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"total_count": 1, "incomplete_results": True, "items": []},
    {"total_count": -1, "incomplete_results": False, "items": []},
    {"total_count": 1, "incomplete_results": False, "items": [{"full_name": "bad/url/path"}]},
    {"total_count": 1, "incomplete_results": False, "items": [{"full_name": "ok/repo", "stargazers_count": -1}]},
])
async def test_malformed_or_incomplete_search_is_not_completed(payload):
    with pytest.raises(HTTPException) as error:
        await GitHubDiscovery().search(DiscoveryRequest(mode="live"), transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)))
    assert error.value.detail["code"] == "GITHUB_INVALID_RESPONSE"


def test_fixture_post_get_and_live_gate():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(app_mode="fixture", _env_file=None)
    client = TestClient(app)
    response = client.post("/api/v1/discovery-runs", json={"mode": "fixture", "limit": 1})
    assert response.status_code == 201
    run = response.json()
    assert run["mode"] == run["status"] == "fixture"
    assert run["storage"] == "in_memory"
    assert run["source_total"] is None
    assert len(run["repositories"]) == 1
    assert run["repositories"][0]["discovery_mode"] == "fixture"
    assert client.get(f'/api/v1/discovery-runs/{run["id"]}').json() == run
    assert client.get(f"/api/v1/discovery-runs/{uuid4()}").status_code == 404
    disabled = client.post("/api/v1/discovery-runs", json={"mode": "live"})
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "LIVE_DISCOVERY_DISABLED"


@pytest.mark.parametrize("fields", [{"limit": 31}, {"limit": 0}, {"discovery_mode": "unknown"},
                                    {"query": ""}, {"query": "   "}, {"query": "a\nb"}])
def test_invalid_search_requests(fields):
    with pytest.raises(ValidationError):
        DiscoveryRequest(**fields)


@pytest.mark.asyncio
async def test_memory_retention_is_bounded():
    store = DiscoveryStore()
    oldest = await store.create(DiscoveryRequest())
    for _ in range(100):
        await store.create(DiscoveryRequest())
    assert len(store.runs) == 100
    with pytest.raises(HTTPException) as error:
        store.get(oldest.id)
    assert error.value.status_code == 404
