"""One guarded B trial job against A's validated local product and C's records.

The caller supplies a previously created live experiment, a leased job, a durable
session repository and a guarded HF budget. Full batches still require C's atomic
multiworker spend ledger and measured pilot authorization.
"""

import asyncio
from pathlib import Path
from urllib.parse import urljoin
from uuid import UUID

import httpx

from backend.app.features.integration.product.checks import OBSERVE_SCRIPT, evaluate
from backend.app.features.integration.product.handoff import ProductHandoff
from backend.app.features.personas.durable_evidence import DurableEvidenceSink
from backend.app.features.personas.inference_budget import BudgetedInference
from backend.app.features.personas.online_context import probe_context
from backend.app.features.personas.online_population import BoundPopulation, OnlinePopulationError
from backend.app.features.personas.runtime_policy import HFActionPolicy
from backend.app.features.personas.session_execution import (
    CheckResult,
    StateReset,
    TrialExecution,
    TrialGateError,
    TrialPlan,
    execute_trial,
)
from backend.app.shared.inference import InferenceError
from backend.app.shared.jobs import JobQueue, Lease
from backend.app.shared.session_records import SessionRepository

JOB_KIND = "persona_mandatory_pilot_v1"


def enqueue_pilot(queue: JobQueue, bound: BoundPopulation, *, index: int,
                  experiment_id: UUID, artifact_root: Path):
    """Queue one exact pilot identity after A's local runtime gate passes."""
    plan = bound.trial_plan(index, experiment_id, artifact_root=artifact_root)
    return queue.enqueue(JOB_KIND, {
        "population_version": bound.population.version, "persona_index": index,
        "persona_id": str(plan.persona.id), "task_id": str(plan.task.id),
        "product_version_id": str(plan.product.id),
    }, experiment_id=experiment_id, max_attempts=1)


def validate_job(lease: Lease, bound: BoundPopulation) -> tuple[int, UUID]:
    job = lease.job
    payload = job.payload
    if (job.kind != JOB_KIND or job.status != "running" or job.attempt < 1
            or job.experiment_id is None or job.max_attempts != 1
            or payload.get("population_version") != bound.population.version
            or type(payload.get("persona_index")) is not int):
        raise TrialGateError("PILOT_JOB_IDENTITY_MISMATCH")
    index = payload["persona_index"]
    persona, task = bound.persona_task(index)
    if (payload.get("persona_id") != str(persona.id)
            or payload.get("task_id") != str(task.id)
            or payload.get("product_version_id") != bound.binding.data()["product_version_id"]):
        raise TrialGateError("PILOT_JOB_IDENTITY_MISMATCH")
    return index, job.experiment_id


async def verify_product_process(plan: TrialPlan, bound: BoundPopulation):
    """A's local handoff endpoint must serve the identical frozen product."""
    expected = ProductHandoff.model_validate(bound.binding.data()["product_manifest"])
    url = urljoin(plan.product.runtime_url.rstrip("/") + "/", "api/v1/handoff")
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(url)
        if response.status_code != 200:
            raise ValueError("handoff unavailable")
        observed = ProductHandoff.model_validate(response.json())
    except (httpx.HTTPError, ValueError, TypeError):
        raise TrialGateError("SOURCETABLE_PROCESS_NOT_VERIFIED") from None
    if observed != expected or observed.version != plan.product:
        raise TrialGateError("SOURCETABLE_PROCESS_HANDOFF_MISMATCH")


def product_callbacks(plan: TrialPlan, bound: BoundPopulation):
    states = bound.binding.data()["product_manifest"]["initial_states"]
    if plan.task.initial_state_ref not in states:
        raise TrialGateError("UNKNOWN_INITIAL_STATE")

    async def reset_state(session_id, initial_state_ref, product_version_id):
        if (initial_state_ref != plan.task.initial_state_ref
                or product_version_id != plan.product.id):
            raise TrialGateError("STATE_RESET_SCOPE_MISMATCH")
        # SourceTable holds no server session state; each browser context starts blank.
        return StateReset(session_id=session_id, initial_state_ref=initial_state_ref,
                          product_version_id=product_version_id)

    async def check(page, session_id, check_id):
        if check_id != plan.task.check_id or check_id != "sourcetable-normal-v1":
            raise TrialGateError("UNKNOWN_FIXED_CHECK")
        try:
            await page.wait_for_function(
                "() => !document.querySelector('#load-sample')?.disabled", timeout=18000)
            observation = await page.evaluate(OBSERVE_SCRIPT)
            error_visible = await page.locator("#error").is_visible()
        except Exception:
            raise TrialGateError("PRODUCT_OBSERVATION_FAILED") from None
        if evaluate(check_id, observation):
            return CheckResult(outcome="success", code="A_FIXED_NORMAL_CHECK_PASSED")
        if error_visible or observation.get("verdict") == "Schema errors found":
            return CheckResult(outcome="application_failure", code="A_PRODUCT_ERROR_OBSERVED")
        return CheckResult(outcome="continue", code="A_FIXED_NORMAL_CHECK_PENDING")

    return reset_state, check


async def run_claimed_pilot(lease: Lease, *, queue: JobQueue,
                            sessions: SessionRepository, bound: BoundPopulation,
                            inference: BudgetedInference, browser, artifact_root: Path,
                            worker_owner: str) -> TrialExecution:
    """Run exactly one claimed pilot. A terminal attempt cannot silently be replaced."""
    if not isinstance(inference, BudgetedInference):
        raise TypeError("A pilot requires guarded inference")
    current_lease = lease

    async def heartbeat():
        nonlocal current_lease
        current_lease = await asyncio.to_thread(queue.heartbeat, current_lease, 180)

    try:
        index, experiment_id = validate_job(lease, bound)
        if lease.job.lease_owner != worker_owner or not worker_owner.strip():
            raise TrialGateError("PILOT_WORKER_LEASE_MISMATCH")
        plan = bound.trial_plan(index, experiment_id, artifact_root=artifact_root)
        await verify_product_process(plan, bound)
        await heartbeat()
        choice = await probe_context(bound, index, inference)
        await heartbeat()
        policy = HFActionPolicy(inference,
                                initial_relevance=choice.choice.simulated_initial_relevance)
        sink = DurableEvidenceSink(sessions, task_id=plan.task.id, attempt=lease.job.attempt,
            artifact_root=artifact_root, before_write=heartbeat,
            provenance={"population_version": bound.population.version,
                        "behavior_corpus_version": plan.persona.software_behavior.corpus_version,
                        "context_probe_request_id": choice.provenance.get("request_id"),
                        "simulated_initial_relevance": choice.choice.simulated_initial_relevance})
        reset_state, check = product_callbacks(plan, bound)
        result = await execute_trial(browser, plan, policy=policy, sink=sink,
                                     reset_state=reset_state, check=check)
        await heartbeat()
        if result.counts_as_mandatory_trial:
            await asyncio.to_thread(queue.complete, current_lease,
                {"session_id": str(result.session.id), "outcome": result.session.outcome,
                 "pilot": True, "completed_mandatory_trial": True,
                 "inference_provenance": policy.provenance})
        else:
            await asyncio.to_thread(queue.fail, current_lease,
                result.check_outcome, retryable=False)
        return result
    except Exception as failure:
        code = (failure.code if isinstance(failure, InferenceError) else
                str(failure) if isinstance(failure, (TrialGateError, OnlinePopulationError))
                else "PILOT_WORKER_FAILED")
        try:
            await asyncio.to_thread(queue.fail, current_lease, code, retryable=False)
        except Exception:
            pass  # An expired/cancelled lease cannot be changed by this worker.
        raise
