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

from backend.app.features.integration.handoff import ProductHandoff
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
                  experiment_id: UUID, artifact_root: Path, runtime_verifier=None):
    """Queue one exact pilot identity after A's local runtime gate passes."""
    plan = bound.trial_plan(index, experiment_id, artifact_root=artifact_root, runtime_verifier=runtime_verifier)
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
        raise TrialGateError("SELECTED_PROTOTYPE_PROCESS_NOT_VERIFIED") from None
    if observed != expected or observed.version != plan.product:
        raise TrialGateError("SELECTED_PROTOTYPE_PROCESS_HANDOFF_MISMATCH")


def product_callbacks(plan: TrialPlan, bound: BoundPopulation, *, callbacks=None):
    catalog = bound.binding.data()["product_manifest"]
    if plan.task.initial_state_ref not in catalog["initial_states"]:
        raise TrialGateError("UNKNOWN_INITIAL_STATE")
    if plan.task.check_id not in {check["id"] for check in catalog["checks"]}:
        raise TrialGateError("UNKNOWN_FIXED_CHECK")
    if callbacks is None:
        raise TrialGateError("SELECTED_PROTOTYPE_CALLBACKS_REQUIRED")
    reset, evaluate_check = callbacks
    async def reset_state(session_id, initial_state_ref, product_version_id):
        if initial_state_ref != plan.task.initial_state_ref or product_version_id != plan.product.id:
            raise TrialGateError("STATE_RESET_SCOPE_MISMATCH")
        result = await reset(session_id, initial_state_ref, product_version_id)
        return StateReset.model_validate(result)
    async def check(page, session_id, check_id):
        if check_id != plan.task.check_id:
            raise TrialGateError("UNKNOWN_FIXED_CHECK")
        return CheckResult.model_validate(await evaluate_check(page, session_id, check_id))
    return reset_state, check


async def run_claimed_pilot(lease: Lease, *, queue: JobQueue,
                            sessions: SessionRepository, bound: BoundPopulation,
                            inference: BudgetedInference, browser, artifact_root: Path,
                            worker_owner: str, runtime_verifier=None, callbacks=None) -> TrialExecution:
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
        plan = bound.trial_plan(index, experiment_id, artifact_root=artifact_root, runtime_verifier=runtime_verifier)
        reset_state, check = product_callbacks(plan, bound, callbacks=callbacks)
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
