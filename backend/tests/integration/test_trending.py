import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.features.integration.discovery import DiscoveryRequest, GitHubDiscovery
from backend.app.features.integration.trending import trending_snapshot

HTML = '<article class="Box-row"><h2><a href="/example/parser">Parser</a></h2><a href="/evil/other">Other</a></article>'


@pytest.mark.asyncio
async def test_trending_provenance_metadata_and_token_host_boundary():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == 'github.com':
            assert 'authorization' not in request.headers
            assert request.url.params['since'] == 'weekly'
            assert request.url.path == '/trending/python'
            return httpx.Response(200, text=HTML)
        assert request.url.host == 'api.github.com'
        assert request.headers['authorization'] == 'Bearer secret'
        return httpx.Response(200, json={'full_name': 'example/parser', 'stargazers_count': 5,
                                        'fork': False, 'archived': False})
    repos, total, collected, hit = await trending_snapshot(
        DiscoveryRequest(mode='live', discovery_mode='trending', trending_language='python', limit=1),
        'secret', httpx.MockTransport(handler),
    )
    assert len(calls) == 2 and total == 1 and hit is False
    assert repos[0].discovery_mode == 'trending'
    assert repos[0].evidence[0].collected_at == collected
    assert 'weekly snapshot rank 1' in repos[0].evidence[0].note
    assert 'secret' not in repos[0].model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize('response,code', [
    (httpx.Response(200, text='<h1>Changed page</h1>'), 'TRENDING_INVALID_RESPONSE'),
    (httpx.Response(302, headers={'location': 'https://evil.invalid'}), 'TRENDING_UNAVAILABLE'),
    (httpx.Response(429), 'TRENDING_RATE_LIMIT'),
    (httpx.Response(200, content=b'x' * 1_000_001), 'TRENDING_TOO_LARGE'),
])
async def test_invalid_changed_oversized_and_quota_pages_fail_visibly(response, code):
    with pytest.raises(HTTPException) as error:
        await trending_snapshot(DiscoveryRequest(discovery_mode='trending'), transport=httpx.MockTransport(
            lambda request: response))
    assert error.value.detail['code'] == code


@pytest.mark.asyncio
async def test_trending_metadata_failure_is_not_success():
    def handler(request):
        return httpx.Response(200, text=HTML) if request.url.host == 'github.com' else httpx.Response(429)
    with pytest.raises(HTTPException):
        await trending_snapshot(DiscoveryRequest(discovery_mode='trending'), transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_recent_dates_are_explicit_search_filters():
    def handler(request):
        query = request.url.params['q']
        assert 'created:>=2026-04-10' in query and 'pushed:>=2026-09-10' in query
        assert request.url.params['sort'] == 'stars'
        return httpx.Response(200, json={'items': [], 'total_count': 0, 'incomplete_results': False})
    await GitHubDiscovery().search(DiscoveryRequest(created_after='2026-04-10', pushed_after='2026-09-10'),
                                   transport=httpx.MockTransport(handler))


@pytest.mark.parametrize('fields', [{'trending_language': '../secret'}, {'trending_period': 'year'},
                                    {'created_after': 'bad'}, {'discovery_mode': 'trending', 'created_after': '2026-01-01'}])
def test_discovery_filter_validation(fields):
    with pytest.raises(ValidationError):
        DiscoveryRequest(**fields)
