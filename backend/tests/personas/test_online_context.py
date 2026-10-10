"""Offline SourceTable binding and cited-context checks; no Neon or paid inference."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.features.integration.product.checks import EXPECTED_ROWS
from backend.app.features.integration.product.handoff import ProductHandoff
from backend.app.features.personas.inference_budget import BudgetedInference
from backend.app.features.personas.live_trial_worker import (
    JOB_KIND,
    product_callbacks,
    validate_job,
)
from backend.app.features.personas.online_context import (
    ContextChoice,
    context_messages,
    probe_context,
)
from backend.app.features.personas.online_population import (
    OnlinePopulationError,
    bind_population,
    load_neon_population,
)
from backend.app.features.personas.population import approve_behavior, generate_population
from backend.app.features.personas.product_handoff import consume_sourcetable_handoff
from backend.app.features.personas.session_execution import TrialGateError, TrialPlan
from backend.app.shared.inference import InferenceResult
from backend.app.shared.jobs import JobRecord, Lease
from backend.app.shared.settings import Settings
from backend.tests.personas.test_population import FakeHF, inputs


class FakeGuarded(BudgetedInference):
    def __init__(self, choice):
        self.choice = choice
        self.calls = []

    async def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return InferenceResult(self.choice, {"model_id": "fake/model", "provider": "fake"})


async def test_real_catalog_binds_500_fake_generated_records_before_hf_context():
    corpus, draft, support, _, _ = inputs()
    binding = consume_sourcetable_handoff()
    population = await generate_population(
        corpus, approve_behavior(draft, corpus, support), FakeHF(),
        quotas=binding.quotas(), task_templates=binding.tasks(),
        generation_version="invented-test-only-v1", purpose="complete",
    )
    bound = bind_population(population, expected_version=population.version)
    assert bound.population.data()["configured_count"] == 500
    assert bound.population.data()["completed_trials"] == 0
    persona, task = bound.persona_task(0)
    context = json.loads(context_messages(bound, 0)[1]["content"])
    assert context["persona_id"] == str(persona.id)
    assert context["task_id"] == str(task.id)
    assert context["patterns"][0]["evidence_ids"] == [
        str(item) for item in persona.software_behavior.patterns[0].evidence_ids]
    assert "source_text" not in context

    pattern = persona.software_behavior.patterns[0]
    choice = ContextChoice(persona_id=persona.id, task_id=task.id, pattern_id=pattern.id,
                           review_id=pattern.evidence_ids[0],
                           simulated_initial_relevance="medium", reason="Invented test choice")
    guarded = FakeGuarded(choice)
    result = await probe_context(bound, 0, guarded)
    assert result.choice.review_id == pattern.evidence_ids[0]
    assert guarded.calls[0]["role"] == "persona_online_context_diagnostic"
    assert guarded.calls[0]["request_context"]["population_version"] == population.version

    guarded.choice = choice.model_copy(update={"review_id": uuid4()})
    with pytest.raises(OnlinePopulationError, match="INFERENCE_CONTEXT_IDENTITY_MISMATCH"):
        await probe_context(bound, 0, guarded)
    with pytest.raises(OnlinePopulationError, match="POPULATION_VERSION_MISMATCH"):
        bind_population(population, expected_version="0" * 64)
    with pytest.raises(OnlinePopulationError, match="SOURCETABLE_RUNTIME_NOT_VERIFIED"):
        bound.trial_plan(0, uuid4(), artifact_root=Settings().artifact_root)

    product = ProductHandoff.model_validate(binding.data()["product_manifest"]).version
    lease = Lease(JobRecord(id=uuid4(), kind=JOB_KIND, status="running", attempt=1,
        max_attempts=1, payload={"population_version": population.version,
                                 "persona_index": 0, "persona_id": str(persona.id),
                                 "task_id": str(task.id),
                                 "product_version_id": str(product.id)},
        result=None, last_error=None, lease_owner="test-worker",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=3),
        experiment_id=uuid4(), session_id=None))
    assert validate_job(lease, bound) == (0, lease.job.experiment_id)
    lease.job.payload["task_id"] = str(uuid4())
    with pytest.raises(TrialGateError, match="PILOT_JOB_IDENTITY_MISMATCH"):
        validate_job(lease, bound)

    plan = TrialPlan(mode="live", product=product, persona=persona,
                     task=task, experiment_id=uuid4())
    reset, check = product_callbacks(plan, bound)
    state = await reset(uuid4(), task.initial_state_ref, product.id)
    assert state.product_version_id == product.id

    class Page:
        def __init__(self, observation, error=False):
            self.observation, self.error = observation, error

        async def wait_for_function(self, *_args, **_kwargs):
            return None

        async def evaluate(self, _script):
            return self.observation

        def locator(self, _selector):
            return self

        async def is_visible(self):
            return self.error

    success = {"verdict": "Schema checks passed", "rows": EXPECTED_ROWS,
               "selected": {"row": 2, "column": 2, "text": "2"},
               "source_detail": "Page 1", "error_count": 0}
    assert (await check(Page(success), uuid4(), task.check_id)).outcome == "success"
    assert (await check(Page({}), uuid4(), task.check_id)).outcome == "continue"
    assert (await check(Page({}, error=True), uuid4(), task.check_id)).outcome == "application_failure"


def test_fixture_configuration_cannot_read_neon_or_send_hf():
    with pytest.raises(OnlinePopulationError, match="LIVE_NEON_CONFIGURATION_REQUIRED"):
        load_neon_population(Settings(app_mode="fixture"), "0" * 64)
    with pytest.raises(OnlinePopulationError, match="FROZEN_POPULATION_REQUIRED"):
        bind_population(SimpleNamespace(version="0" * 64), expected_version="0" * 64)
