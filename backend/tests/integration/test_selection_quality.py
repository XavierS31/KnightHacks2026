"""Selection, replacement, quota and extraction regressions for automatic studies."""
from datetime import UTC, datetime
from time import time
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from backend.app.features.integration import github
from backend.app.features.integration.discovery import DiscoveryRequest, DiscoveryRun
from backend.app.features.integration.proposals import IntegrationInference
from backend.app.features.integration.sources import GitHubSources, SourceRequest
from backend.app.features.integration.studies import StudyEngine
from backend.app.features.integration.study_models import IdeasOutput, StudyRequest
from backend.tests.integration.test_proposals import settings
from backend.tests.integration.test_sources import file_payload, repository, transport
from backend.tests.integration.test_studies import (
    FakeAlternatives,
    FakeSources,
    SequenceInference,
    brief,
)


async def test_large_readme_retains_late_api_evidence_and_verified_full_hash():
    import hashlib
    text = '# Engine\n\n' + ('Sponsor badges.\n\n' * 7500) + '## API usage\n\nImport the engine library; input a graph and output a programmable pipeline.'
    source = await GitHubSources().collect(repository(), SourceRequest(issue_limit=0), transport=transport({'/repos/example/parser/readme':file_payload(text)}))
    doc=source.documents[0]
    assert len(text.encode()) > 100_000
    assert doc.truncated and len(doc.text) <= 20_000
    assert 'programmable pipeline' in doc.text
    assert doc.content_sha256 == hashlib.sha256(text.encode()).hexdigest()


async def test_shared_cache_is_scoped_and_conditional_and_quota_stops_new_requests(monkeypatch):
    calls=[]
    reset=int(time())+120
    def handler(request):
        calls.append(request)
        if request.url.path=='/rate':
            return httpx.Response(403, headers={'x-ratelimit-remaining':'0','x-ratelimit-reset':str(reset),'x-ratelimit-resource':'core'},json={'message':'private rate limit details'})
        if request.headers.get('if-none-match'):
            return httpx.Response(304)
        return httpx.Response(200,headers={'etag':'"test"'},json={'value':1})
    mock=httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=mock) as client:
        await github.github_json(client,'/repos/example/parser/readme',{'ref':'a'*40})
        await github.github_json(client,'/repos/example/parser/readme',{'ref':'a'*40})
        assert len(calls)==1
        monkeypatch.setattr(github,'time',lambda:time()+4000)
        await github.github_json(client,'/repos/example/parser/readme',{'ref':'a'*40})
        assert len(calls)==2 and calls[-1].headers['if-none-match']=='"test"'
        monkeypatch.undo()
        with pytest.raises(HTTPException) as exc:
            await github.github_json(client,'/rate')
        assert exc.value.detail['retry_at']>=reset and 'private' not in str(exc.value.detail)
        with pytest.raises(HTTPException):
            await github.github_json(client,'/another')
        assert len(calls)==3
        # Configured authentication uses another quota scope, and cached unauthenticated content isn't reused.
        client.headers['Authorization']='Bearer test-scoped-token'
        await github.github_json(client,'/another')
        assert len(calls)==4


async def test_request_cap_is_hard_and_cache_does_not_consume_it():
    budget=github.RequestBudget(limit=1)
    context=github.request_budget.set(budget)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={}))) as client:
            await github.github_json(client,'/one')
            await github.github_json(client,'/one')
            with pytest.raises(HTTPException) as exc:
                await github.github_json(client,'/two')
            assert exc.value.detail['code']=='GITHUB_REQUEST_BUDGET'
            assert budget.used==1
    finally:
        github.request_budget.reset(context)


async def test_source_rank_beats_stars_and_replaces_failed_deep_read(tmp_path):
    repos=[]
    for name,stars in [('skin',10000),('weak',900),('strong',1),('spare',2)]:
        repos.append(repository().model_copy(update={'id':uuid4(),'full_name':'example/'+name,'description':'Engine library','stars':stars}))
    class Discovery:
        async def create(self,request,*args):
            now=datetime.now(UTC)
            return DiscoveryRun(id=uuid4(),mode='live',status='completed',request=request,created_at=now,source_collected_at=now,repositories=repos,limitations=[],next_gate='Research')
    class Sources(FakeSources):
        async def screen(self,repo,token):
            source=await super().research(repo,token)
            source.documents[0].text = {
                'skin':'# A theme skin for a desktop client. Color wallpaper.',
                'weak':'API library usage example.',
                'strong':'Parser engine compiler pipeline runtime SDK API library CLI protocol. Usage example input output architecture reference. Automation integrate embed custom plugin.',
                'spare':'Parser engine SDK API library CLI. Usage example input output. Integration custom plugin.',
            }[repo.full_name.split('/')[1]]
            return source
        async def research(self,repo,token):
            if repo.full_name.endswith('/strong'):
                raise HTTPException(502,detail={'code':'GITHUB_UNAVAILABLE'})
            return await super().research(repo,token)
    model=SequenceInference([brief(),IdeasOutput(ideas=[],explanation='No strong opportunity supported')])
    engine=StudyEngine(Discovery(),Sources(),lambda s:IntegrationInference(s,model),FakeAlternatives())
    study=engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live',limit=4),research_limit=1),settings(tmp_path))
    await engine.tasks[study.id]
    states={r.repository.full_name:r for r in study.repositories}
    assert states['example/skin'].status=='unsuitable'
    assert states['example/strong'].status=='failed'
    assert states['example/spare'].status=='researched'
    assert states['example/weak'].status=='screened'
    assert study.counts['research_failures']==1 and study.counts['unsuitable']==1
    assert study.status=='partial' and not study.products
    assert study.inference_calls==2


async def test_readable_source_with_doc_rate_failure_is_counted(tmp_path):
    class Sources(FakeSources):
        async def research(self,repo,token):
            source=await super().research(repo,token)
            source.failures=['Documentation index: GITHUB_RATE_LIMIT; retry_at=123']
            return source
    from backend.tests.integration.test_studies import FakeDiscovery
    model=SequenceInference([brief(),IdeasOutput(ideas=[],explanation='Abstain')])
    engine=StudyEngine(FakeDiscovery(),Sources(),lambda s:IntegrationInference(s,model),FakeAlternatives())
    study=engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')),settings(tmp_path))
    await engine.tasks[study.id]
    assert study.counts['researched']==1 and study.counts['source_gaps']==1
    assert study.counts['run_failures']>=1 and study.status=='partial'


def test_automatic_anchor_request_normalizes_to_emerging():
    assert StudyRequest(discovery=DiscoveryRequest(discovery_mode='popular')).discovery.discovery_mode=='emerging'


async def test_documented_api_reuse_is_not_rejected_for_being_a_complete_app(tmp_path):
    from backend.tests.integration.test_studies import FakeDiscovery
    candidate_brief=brief().model_copy(update={'reuse_assessment':'unsuitable', 'interfaces':'Python API and CLI', 'selection_reason':'Complete app with provider dependencies, not a standalone library'})
    model=SequenceInference([candidate_brief, IdeasOutput(ideas=[],explanation='No distinct product supported')])
    engine=StudyEngine(FakeDiscovery(),FakeSources(),lambda s:IntegrationInference(s,model),FakeAlternatives())
    study=engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')),settings(tmp_path))
    await engine.tasks[study.id]
    assert study.repositories[0].status=='researched'
    assert study.repositories[0].brief.reuse_assessment=='uncertain'
    assert study.counts['researched']==1 and study.counts['unsuitable']==0
    assert study.status=='completed' and not study.products


async def test_invalid_standalone_only_abstention_is_an_evaluation_failure(tmp_path):
    from backend.tests.integration.test_studies import FakeDiscovery
    model=SequenceInference([brief().model_copy(update={'interfaces':'Python API and CLI'}),IdeasOutput(ideas=[],explanation='All are full applications with no reusable libraries or embeddable interfaces')])
    engine=StudyEngine(FakeDiscovery(),FakeSources(),lambda s:IntegrationInference(s,model),FakeAlternatives())
    study=engine.start(StudyRequest(discovery=DiscoveryRequest(mode='live')),settings(tmp_path))
    await engine.tasks[study.id]
    assert study.status=='partial'
    assert 'INVALID_ABSTENTION_CRITERION' in study.failures
    assert study.counts['research_failures']==0 and study.counts['run_failures']==1
    assert 'not a valid rejection criterion' in study.explanation
