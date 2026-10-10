import base64
import hashlib
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.features.integration import router
from backend.app.features.integration.discovery import GitHubDiscovery
from backend.app.features.integration.sources import GitHubSources, SourceRequest, SourceStore
from backend.app.main import create_app
from backend.app.shared.settings import Settings, get_settings

SHA = 'a' * 40


def repository():
    from datetime import UTC, datetime
    return GitHubDiscovery._repository(
        {'full_name': 'example/parser', 'stargazers_count': 1},
        'https://api.github.com/search/repositories', datetime.now(UTC),
    )


def file_payload(text='Example', path='README.md'):
    raw = text.encode()
    return {'type': 'file', 'encoding': 'base64', 'path': path, 'size': len(raw),
            'sha': hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest(),
            'content': base64.b64encode(raw).decode()}


def transport(overrides=None, calls=None):
    responses = {
        '/repos/example/parser': {'full_name': 'example/parser', 'license': {'spdx_id': 'MIT'}},
        '/repos/example/parser/commits': [{'sha': SHA}],
        '/repos/example/parser/readme': file_payload(),
        '/repos/example/parser/license': file_payload('MIT license', 'LICENSE'),
        '/repos/example/parser/issues': [
            {'number': 3, 'title': 'Bug', 'body': 'Reported behavior'},
            {'number': 4, 'title': 'PR', 'body': '', 'pull_request': {}},
        ],
    }
    responses.update(overrides or {})

    def handler(request):
        assert request.url.host == 'api.github.com'
        if calls is not None:
            calls.append(request)
        result = responses.get(request.url.path, httpx.Response(404))
        if isinstance(result, Exception):
            raise result
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_pinned_files_issue_snapshot_and_secret_redaction():
    calls = []
    snapshot = await GitHubSources().collect(repository(), SourceRequest(), 'secret', transport(calls=calls))
    assert snapshot.status == 'collected'
    assert snapshot.commit_sha == SHA
    assert snapshot.license_spdx == 'MIT'
    assert [doc.kind for doc in snapshot.documents] == ['readme', 'license', 'issue']
    assert len(calls) == 5
    for call in calls:
        assert call.headers['authorization'] == 'Bearer secret'
        if call.url.path.endswith(('/readme', '/license')):
            assert call.url.params['ref'] == SHA
    assert SHA in snapshot.documents[0].reference
    assert snapshot.documents[2].reference.endswith('/issues/3')
    assert 'secret' not in snapshot.model_dump_json()
    assert snapshot.documents[0].content_sha256 == hashlib.sha256(b'Example').hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [httpx.Response(404), httpx.Response(500),
                                   {'path': 'README.md'}, file_payload('Bad', '../README.md')])
async def test_optional_file_failure_retains_commit_and_other_evidence(result):
    snapshot = await GitHubSources().collect(repository(), SourceRequest(), transport=transport({
        '/repos/example/parser/readme': result,
    }))
    assert snapshot.status == 'partial'
    assert snapshot.commit_sha == SHA
    assert snapshot.failures
    assert [doc.kind for doc in snapshot.documents] == ['license', 'issue']


@pytest.mark.asyncio
async def test_quota_stops_optional_reads():
    calls = []
    snapshot = await GitHubSources().collect(repository(), SourceRequest(), transport=transport({
        '/repos/example/parser/readme': httpx.Response(429, text='private error'),
    }, calls))
    assert len(calls) == 3
    assert snapshot.status == 'partial'
    assert not snapshot.documents
    assert 'private error' not in snapshot.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [[], [{'sha': 'branch-name'}], httpx.Response(500),
                                   httpx.Response(200, text='not json')])
async def test_cannot_complete_without_valid_commit(result):
    with pytest.raises(HTTPException):
        await GitHubSources().collect(repository(), SourceRequest(), transport=transport({
            '/repos/example/parser/commits': result,
        }))


@pytest.mark.asyncio
async def test_byte_limit_and_text_truncation():
    snapshot = await GitHubSources().collect(repository(), SourceRequest(issue_limit=0), transport=transport({
        '/repos/example/parser/readme': file_payload('x' * 25_000),
        '/repos/example/parser/license': httpx.Response(200, content=b'x' * 512_001),
    }))
    assert snapshot.status == 'partial'
    assert snapshot.documents[0].truncated
    assert len(snapshot.documents[0].text) == 20_000
    assert snapshot.documents[0].content_sha256 == hashlib.sha256(b'x' * 25_000).hexdigest()


@pytest.mark.asyncio
async def test_doc_paths_are_pinned_and_escaped():
    calls = []
    snapshot = await GitHubSources().collect(repository(), SourceRequest(
        documentation_paths=['docs/my guide.md'], issue_limit=0,
    ), transport=transport({'/repos/example/parser/contents/docs/my guide.md': file_payload(
        'Usage', 'docs/my guide.md',
    )}, calls))
    assert snapshot.status == 'collected'
    assert len(calls) == 5
    assert calls[-1].url.params['ref'] == SHA
    assert snapshot.documents[-1].reference.endswith('/docs/my%20guide.md')


@pytest.mark.parametrize('paths', [['../secret.md'], ['/docs.md'], ['https://evil/a.md'],
                                 ['a.md', 'a.md'], ['a.py'], ['a.md'] * 4, ['a//b.md']])
def test_reject_unsafe_or_unbounded_paths(paths):
    with pytest.raises(ValidationError):
        SourceRequest(documentation_paths=paths)


@pytest.mark.asyncio
async def test_blob_integrity_and_timeout_are_visible():
    bad = file_payload()
    bad['sha'] = 'b' * 40
    snapshot = await GitHubSources().collect(repository(), SourceRequest(), transport=transport({
        '/repos/example/parser/readme': bad,
        '/repos/example/parser/license': httpx.ReadTimeout('sensitive details'),
    }))
    assert snapshot.status == 'partial'
    assert [doc.kind for doc in snapshot.documents] == ['issue']
    assert 'sensitive' not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_store_retention():
    snapshot = await GitHubSources().collect(repository(), SourceRequest(), transport=transport())
    store = SourceStore()
    first = store.add(uuid4(), snapshot)
    assert first.storage == 'in_memory' and first.limitations[-1].startswith('In-memory')
    for _ in range(100):
        store.add(uuid4(), snapshot.model_copy(update={'id': uuid4()}))
    assert len(store.snapshots) == 100
    with pytest.raises(HTTPException):
        store.get(first.id)


def test_api_gates_membership_and_roundtrip(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(app_mode='fixture', _env_file=None)
    client = TestClient(app)
    run = client.post('/api/v1/discovery-runs', json={}).json()
    url = f"/api/v1/discovery-runs/{run['id']}/repositories/{run['repositories'][0]['id']}/sources"
    assert client.post(url, json={}).status_code == 409
    app.dependency_overrides[get_settings] = lambda: Settings(app_mode='live', _env_file=None)
    assert client.post(url, json={}).status_code == 409  # Fixture run cannot make network requests.
    router.store.runs[next(key for key in router.store.runs if str(key) == run['id'])].mode = 'live'
    assert client.post(url.replace(run['repositories'][0]['id'], str(uuid4())), json={}).status_code == 404

    async def collect(repo, request, token):
        return await GitHubSources().collect(repository(), request, transport=transport())

    monkeypatch.setattr(router.source_store.github, 'collect', collect)
    response = client.post(url, json={})
    assert response.status_code == 201
    snapshot = response.json()
    assert client.get(f"/api/v1/source-snapshots/{snapshot['id']}").json() == snapshot
    assert client.get(f'/api/v1/source-snapshots/{uuid4()}').status_code == 404
    assert client.post(url, json={'issue_limit': 11}).status_code == 422
