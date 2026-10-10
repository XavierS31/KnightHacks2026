"""Single-process automatic studies; bounded paid calls, visible progress and cancellation."""
import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

from backend.app.features.integration.automatic_sources import AutomaticSources
from backend.app.features.integration.discovery import DiscoveryStore, discovery_error
from backend.app.features.integration.proposals import IntegrationInference
from backend.app.features.integration.study_models import (
    BriefCapability,
    BriefOutput,
    EvaluatedProduct,
    RepositoryResearch,
    ResearchStudy,
)
from backend.app.features.integration.study_research import (
    AlternativesResearch,
    critique_product,
    generate_products,
    researched_brief,
)
from backend.app.shared.contracts import Repository
from backend.app.shared.inference import InferenceError


def failure_code(exc):
    if isinstance(exc, InferenceError):
        return exc.code
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return exc.detail.get("code", "RESEARCH_FAILED")
    return "RESEARCH_FAILED"


class StudyEngine:
    def __init__(self, discovery=None, sources=None, inference_factory=IntegrationInference,
                 alternatives=None, snapshot_store=None):
        self.discovery = discovery or DiscoveryStore()
        self.sources = sources or AutomaticSources()
        self.inference_factory = inference_factory
        self.alternatives = alternatives or AlternativesResearch()
        self.snapshot_store = snapshot_store
        self.records = OrderedDict()
        self.tasks = {}

    def get(self, identity):
        if identity not in self.records:
            raise discovery_error(404, "STUDY_NOT_FOUND", "Study is unknown or no longer retained in this API process.")
        return self.records[identity]

    def start(self, request, settings):
        if any(not task.done() for task in self.tasks.values()):
            raise discovery_error(409, "STUDY_ALREADY_RUNNING", "One automatic study is already running. Wait or cancel it before starting another.")
        if request.discovery.mode == "live":
            if settings.app_mode != "live":
                raise discovery_error(409, "LIVE_DISCOVERY_DISABLED", "Set APP_MODE=live on the server for automatic GitHub/HF research.")
            if not (settings.hf_token.get_secret_value() and settings.hf_model_id and settings.hf_provider):
                raise discovery_error(409, "INFERENCE_NOT_CONFIGURED", "Automatic live research requires server-side HF configuration.")
            if settings.experiment_budget_limit <= 0:
                raise discovery_error(409, "BUDGET_NOT_APPROVED", "A positive approved inference allowance is required.")
        now = datetime.now(UTC)
        study = ResearchStudy(id=uuid4(), request=request, mode=request.discovery.mode,
                              status="queued", stage="Waiting to discover repositories", created_at=now, updated_at=now)
        self.records[study.id] = study
        while len(self.records) > 100:
            self.records.popitem(last=False)
        self.tasks = {identity: task for identity, task in self.tasks.items() if not task.done()}
        self.tasks[study.id] = asyncio.create_task(self.run(study, settings))
        return study

    def cancel(self, identity):
        study = self.get(identity)
        task = self.tasks.get(identity)
        if task and not task.done():
            # Update immediately: cancellation before the first coroutine turn still has a terminal record.
            study.status, study.stage = "cancelled", "Cancelled; completed evidence retained"
            study.updated_at = datetime.now(UTC)
            task.cancel()
        return study

    @staticmethod
    def stage(study, message):
        study.stage, study.updated_at = message, datetime.now(UTC)

    async def research_record(self, study, repository, service, token):
        record = next((item for item in study.repositories if item.repository.full_name.lower() == repository.full_name.lower()), None)
        if record is None:
            record = RepositoryResearch(repository=repository, status="queued", origin="supporting_tool")
            study.repositories.append(record)
        record.status = "researching"
        self.stage(study, f"Reading capabilities and interfaces: {repository.full_name}")
        try:
            snapshot = await self.sources.research(repository, token)
            if self.snapshot_store is not None:
                self.snapshot_store.snapshots[snapshot.id] = snapshot
                while len(self.snapshot_store.snapshots) > 100:
                    self.snapshot_store.snapshots.popitem(last=False)
            record.snapshot_id, record.commit_sha = snapshot.id, snapshot.commit_sha
            record.coverage = [f"{doc.kind}: {doc.path}" for doc in snapshot.documents] + snapshot.failures
            brief, evidence, provenance = await researched_brief(service, snapshot)
            record.brief, record.evidence, record.provenance = brief, evidence, provenance
            record.status = "researched"
            study.provenance.append(provenance)
        except (InferenceError, HTTPException, OSError, ValueError) as exc:
            record.status, record.failure = "failed", failure_code(exc)
            study.failures.append(f"{repository.full_name}: {record.failure}")
        return record

    async def run(self, study, settings):
        service = None
        try:
            async with asyncio.timeout(900):
                study.status = "running"
                self.stage(study, "Discovering repository candidates")
                study.discovery = await self.discovery.create(study.request.discovery,
                    settings.github_token.get_secret_value(), settings.artifact_root)
                selected = study.discovery.repositories[:study.request.research_limit]
                study.repositories = [RepositoryResearch(repository=repo,
                    status="queued" if repo in selected else "not_researched") for repo in study.discovery.repositories]
                if study.mode == "fixture":
                    self.fixture(study)
                    return
                token = settings.github_token.get_secret_value()
                service = self.inference_factory(settings.model_copy(update={
                    "hf_request_timeout_seconds": max(60, settings.hf_request_timeout_seconds),
                }))
                for repo in selected:
                    record = await self.research_record(study, repo, service, token)
                    if record.failure in {"GITHUB_RATE_LIMIT", "INTEGRATION_BUDGET_EXHAUSTED", "BUDGET_NOT_APPROVED", "INTEGRATION_PRICING_UNVERIFIED"}:
                        break
                good = [record for record in study.repositories if record.status == "researched"]
                if not good:
                    study.status = "failed"
                    study.explanation = "No repository had sufficient usable research. Failures are shown; no product was invented."
                    return
                self.stage(study, "Evaluating substantial new uses across researched technologies")
                ideas, provenance = await generate_products(service, good, study.request.interests)
                study.provenance.append(provenance)
                study.explanation = ideas.explanation if not ideas.ideas else "Draft products are being checked against source capabilities and existing solutions."
                for idea in ideas.ideas:
                    product = EvaluatedProduct(id=uuid4(), idea=idea, status="research_needed")
                    study.products.append(product)
                    supporting = []
                    for name in [idea.anchor_repository, *idea.additional_repositories]:
                        record = next((item for item in study.repositories if item.repository.full_name.lower() == name.lower()), None)
                        if record is None or record.status == "not_researched":
                            repo = record.repository if record else Repository(
                                id=uuid5(NAMESPACE_URL, f"https://github.com/{name.lower()}"), full_name=name,
                                url=f"https://github.com/{name}", stars=0, description="Suggested supporting tool; metadata not yet discovered",
                                discovery_mode="popular", evidence=[])
                            record = await self.research_record(study, repo, service, token)
                        if record.status != "researched":
                            product.failure = "SUPPORTING_CAPABILITY_NOT_RESEARCHED"
                            break
                        supporting.append(record)
                    product.evidence = [citation for record in supporting for citation in record.evidence]
                    if product.failure:
                        continue
                    self.stage(study, f"Searching existing equivalents: {idea.title}")
                    product.searches = await self.alternatives.search(idea.alternative_queries,
                        {record.repository.full_name.lower() for record in supporting}, token)
                    self.stage(study, f"Critiquing originality and product scope: {idea.title}")
                    try:
                        critique, provenance = await critique_product(service, idea, supporting, product.searches)
                        product.critique, product.provenance = critique, provenance
                        study.provenance.append(provenance)
                        if critique.scope != "substantial_repurpose" or critique.novelty == "close_equivalent":
                            product.status = "rejected"
                        elif critique.novelty == "inconclusive":
                            product.status = "research_needed"
                        else:
                            product.status = "recommended_for_prototype"
                    except (InferenceError, HTTPException, OSError, ValueError) as exc:
                        product.failure = failure_code(exc)
                        study.failures.append(f"{idea.title}: {product.failure}")
                if study.products:
                    recommended = sum(product.status == 'recommended_for_prototype' for product in study.products)
                    rejected = sum(product.status == 'rejected' for product in study.products)
                    unresolved = sum(product.status == 'research_needed' for product in study.products)
                    study.explanation = (f"Researched {len(good)} discovered repositories. {recommended} product(s) passed the substantial-use and bounded existing-solution checks; "
                                         f"{rejected} rejected and {unresolved} need more research. These findings are hypotheses, not guaranteed unique or validated products.")
                study.status = "partial" if study.failures or any(product.status == "research_needed" for product in study.products) else "completed"
        except asyncio.CancelledError:
            study.status = "cancelled"
            raise
        except TimeoutError:
            study.status = "partial" if study.repositories else "failed"
            study.failures.append("STUDY_TIME_LIMIT")
        except Exception as exc:
            study.status = "partial" if any(record.brief for record in study.repositories) else "failed"
            study.failures.append(failure_code(exc))
        finally:
            for record in study.repositories:
                if record.status in {"queued", "researching"}:
                    record.status, record.failure = "not_researched", "STOPPED_BEFORE_RESEARCH_FINISHED"
            self.stage(study, "Research finished" if study.status == "completed" else f"Research {study.status}; see retained results and gaps")
            if service:
                await service.close()

    @staticmethod
    def fixture(study):
        for record in study.repositories:
            if record.status != "queued":
                continue
            record.status = "researched"
            record.brief = BriefOutput(summary="Fictional document reader used to demonstrate automatic research. No source was fetched.",
                original_purpose="Extract text from simple documents", distinctive_mechanism="Fictional structured document extraction",
                inputs="Fictional document", outputs="Fictional text", interfaces="Illustrative API", reuse_limits="No real runtime or source evidence",
                capabilities=[BriefCapability(name="Illustrative document extraction", mechanism="Synthetic teaching fixture", citation_ids=[0])])
            record.coverage = ["Fictional fixture only; no GitHub/HF research"]
        study.explanation = "Fictional automatic-workflow example. A real study reads source documents, proposes substantial new uses, searches alternatives and critiques them automatically."
        study.status = "completed"
