import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.features.integration.budget import IntegrationBudget
from backend.app.features.integration.proposals import (
    ExtractionOutput,
    IndexedFinding,
    IntegrationInference,
    PairIdea,
    PairOutput,
)
from backend.app.features.integration.sources import GitHubSources, SourceRequest
from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import Settings
from backend.tests.integration.test_sources import repository, transport


def settings(tmp_path, **updates):
    return Settings(_env_file=None, app_mode='live', hf_token='fixture-token',
                    hf_model_id='Qwen/Qwen3-32B', hf_provider='deepinfra',
                    experiment_budget_limit=2, artifact_root=tmp_path, **updates)


class FakeInference:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return SimpleNamespace(value=self.output, provenance={'model_id': 'fixture'})

    async def close(self):
        pass


async def snapshot():
    return await GitHubSources().collect(repository(), SourceRequest(), transport=transport())


def finding(source):
    return IndexedFinding(name='Sample', documented_input='Unknown', documented_output='Unknown',
                             citation_id=0,
                             uncertainty='Fixture-only interpretation')


def test_budget_survives_restart_and_enforces_limit(tmp_path):
    s = settings(tmp_path)
    for _ in range(100):
        IntegrationBudget(s).reserve([], {})
    with pytest.raises(InferenceError, match='EXHAUSTED'):
        IntegrationBudget(s).reserve([], {})
    ledger = json.loads((tmp_path / 'integration-hf-budget.json').read_text())
    assert ledger['calls'] == 100 and ledger['reserved_cents'] == 200


@pytest.mark.parametrize('updates,code', [
    ({'app_mode': 'fixture'}, 'FIXTURE_INFERENCE_FORBIDDEN'),
    ({'experiment_budget_limit': 0}, 'BUDGET_NOT_APPROVED'),
    ({'hf_model_id': 'unknown'}, 'INTEGRATION_PRICING_UNVERIFIED'),
    ({'hf_provider': 'auto'}, 'INTEGRATION_PRICING_UNVERIFIED'),
])
def test_budget_rejects_unapproved_mode_or_pricing(tmp_path, updates, code):
    s = settings(tmp_path).model_copy(update=updates)
    with pytest.raises(InferenceError, match=code):
        IntegrationBudget(s).reserve([], {})
    assert not list(tmp_path.iterdir())


def test_budget_lock_and_corruption_fail_closed(tmp_path):
    budget = IntegrationBudget(settings(tmp_path))
    lock = tmp_path / 'integration-hf-budget.lock'
    lock.touch()
    with pytest.raises(InferenceError, match='BUSY'):
        budget.reserve([], {})
    lock.unlink()
    budget.path.write_text('{broken')
    with pytest.raises(InferenceError, match='INVALID'):
        budget.reserve([], {})
    budget.path.write_text('[]')
    with pytest.raises(InferenceError, match='INVALID'):
        budget.reserve([], {})
    assert not lock.exists()
    budget.path.write_text(json.dumps({'calls': 1, 'reserved_cents': 0}))
    with pytest.raises(InferenceError, match='INVALID'):
        budget.reserve([], {})


def test_oversized_input_rejected_before_reservation(tmp_path):
    with pytest.raises(InferenceError, match='PROMPT_TOO_LARGE'):
        IntegrationBudget(settings(tmp_path)).reserve([{'content': 'x' * 20_000}], {})
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_extraction_cites_pinned_source_without_validating(tmp_path):
    source = await snapshot()
    model = FakeInference(ExtractionOutput(capabilities=[finding(source)]))
    service = IntegrationInference(settings(tmp_path), model)
    result = await service.extract(source)
    assert result.snapshot_id == source.id and result.commit_sha == source.commit_sha
    assert result.validated is False
    assert result.capabilities[0].source_reference == source.documents[0].reference
    assert result.capabilities[0].source_quote in source.documents[0].text
    assert result.reservation['reserved_cents'] == 2
    assert model.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('update', [
    {'citation_id': 1000}, {'citation_id': -1},
])
async def test_unsupported_model_citations_fail_and_stay_reserved(tmp_path, update):
    source = await snapshot()
    value = finding(source).model_copy(update=update)
    model = FakeInference(ExtractionOutput(capabilities=[value]))
    service = IntegrationInference(settings(tmp_path), model)
    with pytest.raises(InferenceError, match='UNSUPPORTED_CAPABILITY_CITATION'):
        await service.extract(source)
    assert json.loads(service.budget.path.read_text())['reserved_cents'] == 2


@pytest.mark.asyncio
async def test_provider_failure_does_not_refund_unknown_spend(tmp_path):
    service = IntegrationInference(settings(tmp_path), FakeInference(InferenceError('INFERENCE_REQUEST_FAILED')))
    with pytest.raises(InferenceError):
        await service.extract(await snapshot())
    assert json.loads(service.budget.path.read_text())['reserved_cents'] == 2


@pytest.mark.asyncio
async def test_missing_document_does_not_spend(tmp_path):
    source = (await snapshot()).model_copy(update={'documents': []})
    model = FakeInference(None)
    service = IntegrationInference(settings(tmp_path), model)
    with pytest.raises(InferenceError, match='NO_DOCUMENTED_SOURCES'):
        await service.extract(source)
    assert model.calls == 0 and not service.budget.path.exists()


@pytest.mark.asyncio
async def test_pair_references_and_duplicate_repositories(tmp_path):
    source = await snapshot()
    service = IntegrationInference(settings(tmp_path), FakeInference(ExtractionOutput(capabilities=[finding(source)])))
    first = await service.extract(source)
    second = first.model_copy(update={'id': uuid4(), 'repository_id': uuid4()})
    idea = PairIdea(title='Sample combination', first_extraction_id=first.id,
                    second_extraction_id=second.id, problem='Sample problem',
                    adapter_boundary='Sample boundary', audience='Sample audience', uncertainty='Unreviewed')
    service.inference = FakeInference(PairOutput(ideas=[idea]))
    result = await service.propose([first, second])
    assert result.novelty == 'unresolved' and result.feasibility == 'unreviewed'
    with pytest.raises(InferenceError, match='DUPLICATE_REPOSITORY'):
        await service.propose([first, first.model_copy(update={'id': uuid4()})])
    with pytest.raises(InferenceError, match='DUPLICATE_EXTRACTION'):
        await service.propose([first, first])
    service.inference = FakeInference(PairOutput(ideas=[idea.model_copy(update={'second_extraction_id': uuid4()})]))
    with pytest.raises(InferenceError, match='INVALID_PROPOSAL_REFERENCES'):
        await service.propose([first, second])


def test_api_fixture_gate_and_unknown_ids(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.features.integration import router
    from backend.app.main import create_app
    from backend.app.shared.settings import get_settings

    app = create_app()
    s = settings(tmp_path).model_copy(update={'app_mode': 'fixture'})
    app.dependency_overrides[get_settings] = lambda: s
    client = TestClient(app)
    identity = uuid4()
    assert client.get(f'/api/v1/extractions/{identity}').status_code == 404
    assert client.get(f'/api/v1/proposal-previews/{identity}').status_code == 404
    assert client.post(f'/api/v1/source-snapshots/{identity}/extractions').status_code == 404
    assert client.post('/api/v1/proposal-previews', json={'extraction_ids': [str(identity)]}).status_code == 422

    import asyncio
    source = asyncio.run(snapshot())
    router.source_store.snapshots[source.id] = source
    response = client.post(f'/api/v1/source-snapshots/{source.id}/extractions')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'FIXTURE_INFERENCE_FORBIDDEN'
    assert not (tmp_path / 'integration-hf-budget.json').exists()


def test_api_extraction_and_proposals_roundtrip(tmp_path, monkeypatch):
    import asyncio

    from fastapi.testclient import TestClient

    from backend.app.features.integration import router
    from backend.app.main import create_app
    from backend.app.shared.settings import get_settings

    source = asyncio.run(snapshot())
    router.source_store.snapshots[source.id] = source
    model = FakeInference(ExtractionOutput(capabilities=[finding(source)]))
    monkeypatch.setattr(router, 'IntegrationInference', lambda s: IntegrationInference(s, model))
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings(tmp_path)
    client = TestClient(app)
    response = client.post(f'/api/v1/source-snapshots/{source.id}/extractions')
    assert response.status_code == 201
    result = response.json()
    assert client.get(f"/api/v1/extractions/{result['id']}").json() == result
    first = router.interpretations.extractions[next(key for key in router.interpretations.extractions if str(key) == result['id'])]
    second = first.model_copy(update={'id': uuid4(), 'repository_id': uuid4()})
    router.interpretations.extractions[second.id] = second
    model.output = PairOutput(ideas=[PairIdea(title='Example', first_extraction_id=first.id,
                                           second_extraction_id=second.id, problem='Example',
                                           adapter_boundary='Example', audience='Example', uncertainty='Unreviewed')])
    response = client.post('/api/v1/proposal-previews', json={'extraction_ids': [str(first.id), str(second.id)]})
    assert response.status_code == 201
    assert client.get(f"/api/v1/proposal-previews/{response.json()['id']}").json() == response.json()
