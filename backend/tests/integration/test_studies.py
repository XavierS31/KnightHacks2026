import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from backend.app.features.integration.automatic_sources import AutomaticSources, documentation_paths
from backend.app.features.integration.discovery import DiscoveryRequest, DiscoveryRun
from backend.app.features.integration.proposals import IntegrationInference
from backend.app.features.integration.studies import StudyEngine
from backend.app.features.integration.study_models import (
    AlternativeSearch,
    BriefCapability,
    BriefOutput,
    CritiqueOutput,
    IdeasOutput,
    ProductIdea,
    StudyRequest,
)
from backend.app.features.integration.study_research import critique_product, researched_brief
from backend.app.shared.inference import InferenceError
from backend.tests.integration.test_proposals import settings, snapshot
from backend.tests.integration.test_sources import SHA, file_payload, repository, transport


class SequenceInference:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(value=value, provenance={'model_id': 'offline fixture', 'role': kwargs['role']})

    async def close(self):
        pass


def brief():
    return BriefOutput(summary='A document parser that outputs structured text for automation.',
        original_purpose='Document conversion', distinctive_mechanism='Preserves structure', inputs='PDF', outputs='Text',
        interfaces='Python library', reuse_limits='Only bounded tested fixtures',
        capabilities=[BriefCapability(name='Parse', mechanism='Extract structured text', citation_ids=[0])])


def idea(name):
    return ProductIdea(title='Accessible lab preparation', anchor_repository=name, additional_repositories=[],
        audience='Students preparing lab sessions', problem='Lab instructions are difficult to navigate hands-free',
        new_use='Turn structured instructions into interactive preparation steps', original_use_difference='Guided preparation, not generic text conversion',
        capability_connection='Parser supplies steps; adapter creates the guided workflow', example_input='Lab instruction PDF',
        example_output='Reviewed preparation sequence', prototype_check='Known instruction order is preserved',
        alternative_queries=['interactive laboratory preparation', 'hands free lab instructions'], risk='Unverified audience relevance')


def critique(scope='substantial_repurpose', novelty='no_close_match'):
    return CritiqueOutput(scope=scope, novelty=novelty, reason='A distinct workflow in this fixture',
                          difference='Bounded search only', matching_references=[])


class FakeDiscovery:
    async def create(self, request, *args):
        now = datetime.now(UTC)
        return DiscoveryRun(id=uuid4(), mode=request.mode, status='completed', request=request,
            created_at=now, repositories=[repository()], source_collected_at=now,
            limitations=['Injected source fixture'], next_gate='Research')


class FakeSources:
    async def research(self, repo, token):
        return (await snapshot()).model_copy(update={'repository_id': repo.id, 'full_name': repo.full_name})


class FakeAlternatives:
    async def search(self, queries, excluded, token):
        return [AlternativeSearch(query=q, reference='https://api.github.com/search/repositories',
                                  collected_at=datetime.now(UTC), status='completed', matches=[]) for q in queries]


async def test_one_start_automatically_runs_research_generation_search_and_critic(tmp_path):
    outputs = [brief(), IdeasOutput(ideas=[idea(repository().full_name)], explanation='A different use'), critique()]
    model = SequenceInference(outputs)
    engine = StudyEngine(FakeDiscovery(), FakeSources(), lambda s: IntegrationInference(s, model), FakeAlternatives())
    study = engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live', limit=1)), settings(tmp_path))
    assert study.status == 'queued'
    await engine.tasks[study.id]
    assert study.status == 'completed'
    assert study.repositories[0].brief.summary != repository().description
    assert study.products[0].status == 'recommended_for_prototype'
    assert len(study.products[0].searches) == 2
    assert study.products[0].example_status == 'illustrative_not_executed'
    assert [call['role'] for call in model.calls] == ['repository_research', 'product_repurposing', 'repurposing_critic']
    assert 'routine issue fixes' in model.calls[1]['messages'][0]['content']


async def test_minor_feature_is_rejected_even_without_search_matches(tmp_path):
    model = SequenceInference([brief(), IdeasOutput(ideas=[idea(repository().full_name)], explanation='A suggestion'), critique('incremental_feature')])
    engine = StudyEngine(FakeDiscovery(), FakeSources(), lambda s: IntegrationInference(s, model), FakeAlternatives())
    study = engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')), settings(tmp_path))
    await engine.tasks[study.id]
    assert study.products[0].status == 'rejected'


async def test_model_can_abstain_instead_of_inventing_product(tmp_path):
    model = SequenceInference([brief(), IdeasOutput(ideas=[], explanation='No substantial transferable use supported')])
    engine = StudyEngine(FakeDiscovery(), FakeSources(), lambda s: IntegrationInference(s, model), FakeAlternatives())
    study = engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')), settings(tmp_path))
    await engine.tasks[study.id]
    assert study.status == 'completed' and not study.products and study.explanation


async def test_failed_summary_does_not_become_researched_or_generate_products(tmp_path):
    model = SequenceInference([InferenceError('INVALID_MODEL_OUTPUT')])
    engine = StudyEngine(FakeDiscovery(), FakeSources(), lambda s: IntegrationInference(s, model), FakeAlternatives())
    study = engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')), settings(tmp_path))
    await engine.tasks[study.id]
    assert study.status == 'failed' and study.repositories[0].status == 'failed'
    assert not study.products and len(model.calls) == 1


async def test_fixture_never_calls_sources_model_or_alternatives(tmp_path):
    def forbidden(settings):
        raise AssertionError('Fixture must not instantiate HF')
    engine = StudyEngine(inference_factory=forbidden)
    study = engine.start(StudyRequest(), settings(tmp_path))
    await engine.tasks[study.id]
    assert study.mode == 'fixture' and study.status == 'completed'
    assert not study.provenance and not list(tmp_path.iterdir())


async def test_busy_and_cancellation_preserve_terminal_state(tmp_path):
    event = asyncio.Event()
    class WaitingDiscovery:
        async def create(self, *args):
            await event.wait()
    engine = StudyEngine(discovery=WaitingDiscovery())
    study = engine.start(StudyRequest(), settings(tmp_path))
    with pytest.raises(HTTPException) as exc:
        engine.start(StudyRequest(), settings(tmp_path))
    assert exc.value.detail['code'] == 'STUDY_ALREADY_RUNNING'
    engine.cancel(study.id)
    await asyncio.gather(engine.tasks[study.id], return_exceptions=True)
    assert study.status == 'cancelled'


def test_automatic_docs_ignore_external_links_commands_traversal_and_routine_issues():
    from backend.app.features.integration.sources import SourceDocument
    source = SimpleNamespace(documents=[SourceDocument(kind='readme', reference='https://github.com/example/readme',
        request_reference='https://api.github.com/example', collected_at=datetime.now(UTC), content_sha256='a'*64,
        truncated=False, text='[usage](docs/usage.md) [bad](../secret.md) [remote](https://bad.invalid/a.md) [install](x.sh) [duplicate](docs/usage.md)')])
    assert documentation_paths(source) == ['docs/usage.md']


async def test_automatic_collector_prioritizes_interface_docs_and_never_fetches_issues():
    calls = []
    source = await AutomaticSources().research(repository(), 'private-token', transport=transport({
        '/repos/example/parser/readme': file_payload('[install](docs/install.md)'),
        '/repos/example/parser/contents': [{'type': 'dir', 'name': 'docs'}, {'type': 'file', 'name': 'pyproject.toml'}],
        '/repos/example/parser/contents/docs': [{'type': 'file', 'name': 'api.md'}, {'type': 'file', 'name': 'architecture.md'}, {'type': 'file', 'name': 'install.md'}],
        '/repos/example/parser/contents/docs/api.md': file_payload('Library API', 'docs/api.md'),
        '/repos/example/parser/contents/docs/architecture.md': file_payload('Engine architecture', 'docs/architecture.md'),
        '/repos/example/parser/contents/pyproject.toml': file_payload('[project]', 'pyproject.toml'),
    }, calls))
    assert {doc.path for doc in source.documents if doc.kind == 'documentation'} == {'docs/api.md', 'docs/architecture.md', 'pyproject.toml'}
    assert not any('/issues' in str(call.url) or 'install.md' in str(call.url) for call in calls)
    assert all(call.url.params['ref'] == SHA for call in calls if '/contents' in call.url.path)
    assert 'private-token' not in source.model_dump_json()


async def test_automatic_collector_stops_at_quota_failure():
    calls = []
    source = await AutomaticSources().research(repository(), transport=transport({
        '/repos/example/parser/readme': httpx.Response(429),
    }, calls))
    assert len(calls) == 3 and source.status == 'partial'


async def test_invented_brief_citation_fails_before_any_product(tmp_path):
    model = SequenceInference([brief().model_copy(update={'capabilities': [BriefCapability(name='invented', mechanism='fake', citation_ids=[999]) ]})])
    with pytest.raises(InferenceError, match='UNSUPPORTED_RESEARCH_CITATION'):
        await researched_brief(IntegrationInference(settings(tmp_path), model), await snapshot())


async def test_missing_alternative_evidence_never_passes_novelty(tmp_path):
    model = SequenceInference([critique()])
    search = AlternativeSearch(query='fixture', reference='https://api.github.com/search/repositories',
        collected_at=datetime.now(UTC), status='failed', failure='GITHUB_RATE_LIMIT')
    result, _ = await critique_product(IntegrationInference(settings(tmp_path), model), idea(repository().full_name), [], [search])
    assert result.novelty == 'inconclusive'


async def test_api_start_and_poll_are_automatic(tmp_path, monkeypatch):
    from backend.app.features.integration import router
    from backend.app.main import create_app
    from backend.app.shared.settings import get_settings
    engine = StudyEngine()
    monkeypatch.setattr(router, 'studies', engine)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/research-studies', json={})
        assert response.status_code == 202
        identity = next(iter(engine.tasks))
        await engine.tasks[identity]
        result = await client.get(f'/api/v1/research-studies/{identity}')
        assert result.json()['status'] == 'completed'
        assert (await client.get(f'/api/v1/research-studies/{uuid4()}')).status_code == 404


async def test_automatic_study_preserves_discovery_parent_for_durable_snapshot(tmp_path):
    from backend.app.features.integration.sources import SourceStore

    saved = []
    durable = SimpleNamespace(save_snapshot=lambda run_id, source: saved.append((run_id, source)))

    class RecordingDiscovery(FakeDiscovery):
        async def create(self, request, token, artifact_root, records):
            assert records is durable
            return await super().create(request)

    model = SequenceInference([brief(), IdeasOutput(ideas=[], explanation='No supported new use')])
    engine = StudyEngine(RecordingDiscovery(), FakeSources(), lambda s: IntegrationInference(s, model),
                         FakeAlternatives(), SourceStore())
    study = engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')), settings(tmp_path), durable)
    await engine.tasks[study.id]
    assert study.status == 'completed'
    assert len(saved) == 1
    assert saved[0][0] == study.discovery.id
    assert saved[0][1].repository_id == study.discovery.repositories[0].id
    assert saved[0][1].storage == 'database'
