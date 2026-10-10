from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.features.integration import router
from backend.app.features.integration.discovery import DiscoveryRequest, DiscoveryStore
from backend.app.features.integration.momentum import MomentumHistory, Observation, signal
from backend.app.features.integration.opportunities import (
    OpportunityHypothesis,
    OpportunityOutput,
    OpportunityRequest,
    discover_opportunities,
    evidence_pack,
)
from backend.app.features.integration.proposals import IntegrationInference
from backend.app.features.integration.sources import SourceDocument
from backend.app.main import create_app
from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import get_settings
from backend.tests.integration.test_proposals import FakeInference, settings, snapshot


def observation(hours=0, stars=10, forks=2):
    return Observation(full_name="example/reader", stars=stars, forks=forks,
                       observed_at=datetime(2026, 10, 10, tzinfo=UTC) + timedelta(hours=hours))


def test_growth_persists_counts_and_never_turns_cached_reads_into_growth(tmp_path):
    history = MomentumHistory(tmp_path)
    first = observation()
    assert history.observe([first])[0].status == "insufficient_history"
    assert MomentumHistory(tmp_path).observe([first])[0].status == "insufficient_history"
    result = MomentumHistory(tmp_path).observe([observation(24, 25, 5)])[0]
    assert result.status == "measured"
    assert result.stars_delta == 15 and result.forks_delta == 3 and result.elapsed_hours == 24
    assert result.baseline == first
    assert len(__import__('json').loads(history.path.read_text())) == 2


def test_negative_counts_unknown_forks_and_invalid_history_are_honest(tmp_path):
    assert signal(observation(24, 5, None), [observation()]).stars_delta == -5
    assert signal(observation(24, 5, None), [observation()]).forks_delta is None
    assert signal(observation(24 * 32), [observation()]).status == "insufficient_history"
    history = MomentumHistory(tmp_path)
    history.path.write_text("broken")
    assert history.observe([observation()])[0].status == "history_unavailable"
    assert history.path.read_text() == "broken"
    history.path.with_suffix('.lock').touch()
    assert history.observe([observation()])[0].status == "history_unavailable"
    assert history.path.with_suffix('.lock').exists()
    blocked_root = tmp_path / 'not-a-directory'
    blocked_root.write_text('fixture')
    assert MomentumHistory(blocked_root).observe([observation()])[0].status == 'history_unavailable'


async def test_emerging_defaults_fixture_does_not_write_history(tmp_path):
    run = await DiscoveryStore().create(DiscoveryRequest(discovery_mode="emerging"), artifact_root=tmp_path)
    assert run.request.created_after and run.request.pushed_after
    assert run.request.created_after < run.request.pushed_after
    assert all(item.status == "fixture" and item.stars_delta is None for item in run.momentum)
    assert not list(tmp_path.iterdir())


def hypothesis(source, **updates):
    citations, _ = evidence_pack([source])
    documentation = next(identity for identity, item in citations.items() if item.kind != 'issue')
    fields = dict(title="Review changes", kind="feature_extension", need_basis="inferred_workflow",
                  audience="Club organizers", problem="Manual comparison of schedules",
                  current_value="Read document text", proposed_value="Review changed dates",
                  why_now="Capability documented; growth not established",
                  capability_citation_ids=[documentation], need_citation_ids=[documentation],
                  supporting_snapshot_ids=[], implementation_boundary="Add review workflow",
                  example_input="Two dates", example_output="A proposed change",
                  acceptance_check="Flag the expected changed date", risk="Unverified relevance")
    return OpportunityHypothesis(**(fields | updates))


async def test_single_anchor_extension_and_abstention_are_supported(tmp_path):
    source = await snapshot()
    model = FakeInference(OpportunityOutput(opportunities=[hypothesis(source)]))
    service = IntegrationInference(settings(tmp_path), model)
    request = OpportunityRequest(anchor_snapshot_id=source.id)
    report = await discover_opportunities(service, request, [source])
    card = report.opportunities[0]
    assert card.kind == "feature_extension" and not card.supporting_snapshot_ids
    assert card.example_status == "illustrative_not_executed" and card.status == 'hypothesis'
    assert card.evidence[0].quote in source.documents[0].text
    assert report.reservation['reserved_cents'] == 2
    model.output = OpportunityOutput(opportunities=[], no_opportunity_reason="No specific unmet need supported")
    report = await discover_opportunities(service, request, [source])
    assert not report.opportunities and report.no_opportunity_reason


@pytest.mark.parametrize('updates', [
    {'capability_citation_ids': [999]}, {'need_citation_ids': [999]},
    {'kind': 'integration'}, {'need_basis': 'issue_report'},
    {'supporting_snapshot_ids': [uuid4()]},
])
async def test_bad_evidence_or_forced_pair_is_rejected(tmp_path, updates):
    source = await snapshot()
    model = FakeInference(OpportunityOutput(opportunities=[hypothesis(source, **updates)]))
    with pytest.raises(InferenceError, match='UNSUPPORTED_OPPORTUNITY_EVIDENCE'):
        await discover_opportunities(IntegrationInference(settings(tmp_path), model),
                                     OpportunityRequest(anchor_snapshot_id=source.id), [source])


async def test_integration_requires_cited_complementary_capability(tmp_path):
    first = await snapshot()
    second = first.model_copy(update={'id': uuid4(), 'repository_id': uuid4(), 'full_name': 'example/exporter'})
    citations, _ = evidence_pack([first, second])
    support = next(identity for identity, item in citations.items() if item.snapshot_id == second.id and item.kind != 'issue')
    idea = hypothesis(first, kind='integration', supporting_snapshot_ids=[second.id])
    model = FakeInference(OpportunityOutput(opportunities=[idea]))
    request = OpportunityRequest(anchor_snapshot_id=first.id, supporting_snapshot_ids=[second.id])
    service = IntegrationInference(settings(tmp_path), model)
    with pytest.raises(InferenceError, match='UNSUPPORTED_OPPORTUNITY_EVIDENCE'):
        await discover_opportunities(service, request, [first, second])
    model.output = OpportunityOutput(opportunities=[idea.model_copy(update={
        'capability_citation_ids': [*idea.capability_citation_ids, support]})])
    assert (await discover_opportunities(service, request, [first, second])).opportunities[0].kind == 'integration'


async def test_issue_heavy_anchor_preserves_each_supporting_repository():
    anchor = await snapshot()
    issues = [SourceDocument(kind='issue', reference=f'https://github.com/example/reader/issues/{i+1}',
                             request_reference='https://api.github.com/repos/example/reader/issues',
                             collected_at=datetime.now(UTC), text='Request\nDetail\nReproduction',
                             content_sha256='a' * 64, truncated=False, issue_state='open') for i in range(10)]
    anchor = anchor.model_copy(update={'documents': [*anchor.documents, *issues]})
    supporting = [anchor.model_copy(update={'id': uuid4(), 'repository_id': uuid4(), 'full_name': f'example/support-{i}'}) for i in range(2)]
    citations, _ = evidence_pack([anchor, *supporting])
    assert len(citations) <= 36
    for source in [anchor, *supporting]:
        assert any(item.snapshot_id == source.id and item.kind != 'issue' for item in citations.values())
        assert any(item.snapshot_id == source.id and item.kind == 'issue' for item in citations.values())


def test_abstention_and_duplicate_anchor_contracts():
    with pytest.raises(ValidationError):
        OpportunityOutput()
    identity = uuid4()
    with pytest.raises(ValidationError):
        OpportunityRequest(anchor_snapshot_id=identity, supporting_snapshot_ids=[identity])


def test_fixture_preview_decision_export_and_unknown_scope(tmp_path):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings(tmp_path).model_copy(update={'app_mode': 'fixture'})
    client = TestClient(app)
    report = client.post('/api/v1/integration/opportunity-demo').json()
    assert report['mode'] == 'fixture' and not report['reservation']
    identity, card = report['id'], report['opportunities'][0]
    route = f"/api/v1/opportunity-reports/{identity}/cards/{card['id']}/decision"
    result = client.post(route, json={'decision': 'rejected', 'note': 'Not useful for our workflow'})
    assert result.status_code == 200
    assert result.json()['opportunities'][0]['decision'] == 'rejected'
    assert result.json()['opportunities'][0]['example_status'] == 'illustrative_not_executed'
    assert client.get(f'/api/v1/opportunity-reports/{identity}').json() == result.json()
    assert client.post(route, json={'decision': 'shortlisted', 'note': ''}).status_code == 422
    assert client.get(f'/api/v1/opportunity-reports/{uuid4()}').status_code == 404
    assert not list(tmp_path.iterdir())


async def test_api_hf_path_fixture_gate_and_report_roundtrip(tmp_path, monkeypatch):
    source = await snapshot()
    router.source_store.snapshots[source.id] = source
    model = FakeInference(OpportunityOutput(opportunities=[hypothesis(source)]))
    monkeypatch.setattr(router, 'IntegrationInference', lambda s: IntegrationInference(s, model))
    app = create_app()
    s = settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: s
    client = TestClient(app)
    response = client.post('/api/v1/opportunity-reports', json={'anchor_snapshot_id': str(source.id)})
    assert response.status_code == 201
    assert client.get(f"/api/v1/opportunity-reports/{response.json()['id']}").json() == response.json()
    s.app_mode = 'fixture'
    response = client.post('/api/v1/opportunity-reports', json={'anchor_snapshot_id': str(source.id)})
    assert response.status_code == 409 and model.calls == 1
