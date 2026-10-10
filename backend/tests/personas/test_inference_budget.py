"""Offline accounting tests; fake prices, approvals and usage are not provider evidence."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.app.features.personas.inference_budget import (
    ApprovedPricePolicy,
    BudgetedInference,
    ExperimentBudget,
    forecast_experiment,
)
from backend.app.shared.inference import InferenceError, InferenceResult


class Answer(BaseModel):
    answer: str


def policy(**overrides):
    return ApprovedPricePolicy(**{
        "policy_id": "test-price-v1", "approval_reference": "test-only-not-live-approval",
        "token_bound_approval_reference": "test-only-token-bound-review",
        "model_id": "test/model", "provider": "test-provider",
        "input_dollars_per_million": Decimal("1"),
        "output_dollars_per_million": Decimal("2"), **overrides,
    })


def request():
    return {"role": "test", "messages": [{"role": "user", "content": "hi 😀"}],
            "output_schema": Answer, "prompt_version": "test-v1"}


class Adapter:
    def __init__(self, *, usage=True, retry=0, failure=None, gate=None):
        self.settings = SimpleNamespace(hf_model_id="test/model", hf_provider="test-provider",
                                        hf_coding_model_id="test/coding",
                                        hf_request_timeout_seconds=20)
        self.calls = 0
        self.usage, self.retry, self.failure, self.gate = usage, retry, failure, gate

    async def generate_structured(self, **kwargs):
        self.calls += 1
        if self.gate:
            await self.gate.wait()
        if self.failure:
            raise self.failure
        return InferenceResult(value=Answer(answer="ok"), provenance={
            "model_id": "test/model", "provider": "test-provider", "retry_count": self.retry,
            "token_usage_if_reported": ({"prompt_tokens": 100, "completion_tokens": 10,
                                         "total_tokens": 110} if self.usage is True else self.usage),
        })


def budget(limit=Decimal("1"), reserve=Decimal(0)):
    return ExperimentBudget("experiment", limit, approval_reference="test-only",
                            mandatory_reserve=reserve)


@pytest.mark.parametrize("override", [
    {"input_dollars_per_million": 1}, {"input_dollars_per_million": Decimal("NaN")},
    {"output_dollars_per_million": Decimal("Infinity")},
    {"input_dollars_per_million": Decimal("-1")}, {"approval_reference": ""},
    {"token_bound_approval_reference": ""}, {"tokens_per_utf8_byte": 0},
    {"tokens_per_utf8_byte": True}, {"input_overhead_tokens": 0},
])
def test_price_policy_requires_explicit_finite_rates_and_reviewed_bounds(override):
    with pytest.raises(ValueError):
        policy(**override)


def test_budget_cannot_be_inferred_from_positive_settings_limit():
    with pytest.raises(ValueError):
        ExperimentBudget("exp", Decimal("1"), approval_reference="")
    with pytest.raises(ValueError):
        budget(Decimal(0))
    with pytest.raises(ValueError):
        budget(Decimal("1"), Decimal("2"))


async def test_two_attempt_reservation_before_send_and_final_usage_settlement():
    gate = asyncio.Event()
    adapter = Adapter(gate=gate, retry=1)
    ledger = budget()
    prices = policy()
    wrapper = BudgetedInference(adapter, ledger, prices)
    task = asyncio.create_task(wrapper.generate_structured(**request()))
    await asyncio.sleep(0)
    reserved = Decimal((await ledger.snapshot())["reserved_dollars"])
    per_attempt = prices.cost(prices.input_bound(request()["messages"], Answer), 1024)
    assert adapter.calls == 1 and reserved == per_attempt * 2
    gate.set()
    result = await task
    snapshot = await ledger.snapshot()
    assert result.value.answer == "ok"
    assert Decimal(snapshot["charged_dollars"]) == per_attempt + Decimal("0.00012")
    assert Decimal(snapshot["reserved_dollars"]) == 0


async def test_racing_requests_never_exceed_cap():
    gate = asyncio.Event()
    adapter = Adapter(gate=gate, usage=None)
    prices = policy()
    maximum = prices.cost(prices.input_bound(request()["messages"], Answer), 1024) * 2
    ledger = budget(maximum)
    wrapper = BudgetedInference(adapter, ledger, prices)
    tasks = [asyncio.create_task(wrapper.generate_structured(**request())) for _ in range(12)]
    await asyncio.sleep(0)
    assert adapter.calls == 1
    assert Decimal((await ledger.snapshot())["reserved_dollars"]) == maximum
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(result, InferenceError) for result in results) == 11
    assert Decimal((await ledger.snapshot())["charged_dollars"]) == maximum


@pytest.mark.parametrize("usage,retry", [
    (None, 0), ({}, 0), ({"prompt_tokens": -1, "completion_tokens": 0, "total_tokens": -1}, 0),
    ({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3}, 0),
    ({"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2}, 0),
    (True, None), (True, 2),
])
async def test_missing_or_invalid_usage_and_retry_metadata_retains_full_charge(usage, retry):
    ledger = budget()
    await BudgetedInference(Adapter(usage=usage, retry=retry), ledger, policy()).generate_structured(
        **request())
    entry = (await ledger.snapshot())["entries"][0]
    assert entry["charged_dollars"] == entry["reserved_dollars"]
    assert entry["status"] == "unreported_usage"


async def test_failure_and_cancellation_do_not_release_ambiguous_sends():
    ledger = budget()
    wrapper = BudgetedInference(Adapter(failure=InferenceError("FAILED")), ledger, policy())
    with pytest.raises(InferenceError):
        await wrapper.generate_structured(**request())
    gate = asyncio.Event()
    wrapper = BudgetedInference(Adapter(gate=gate), ledger, policy())
    task = asyncio.create_task(wrapper.generate_structured(**request()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for entry in (await ledger.snapshot())["entries"]:
        assert entry["charged_dollars"] == entry["reserved_dollars"]
        assert entry["status"] == "unreported_or_failed"


async def test_exact_model_and_experiment_matching_before_calls():
    adapter = Adapter()
    wrapper = BudgetedInference(adapter, budget(), policy())
    with pytest.raises(InferenceError, match="MODEL_PROVIDER_MISMATCH"):
        await wrapper.generate_structured(**request(), coding=True)
    with pytest.raises(InferenceError, match="EXPERIMENT_MISMATCH"):
        await wrapper.generate_structured(**request(), request_context={"experiment_id": "other"})
    adapter.settings.hf_provider = "other"
    with pytest.raises(InferenceError, match="MODEL_PROVIDER_MISMATCH"):
        await wrapper.generate_structured(**request())
    assert adapter.calls == 0


async def test_usage_above_bound_records_overrun_and_stops_further_sends():
    ledger = budget()
    adapter = Adapter(usage={"prompt_tokens": 100_000, "completion_tokens": 1025,
                             "total_tokens": 101_025})
    wrapper = BudgetedInference(adapter, ledger, policy())
    with pytest.raises(InferenceError, match="TOKEN_BOUND_VIOLATED"):
        await wrapper.generate_structured(**request())
    snapshot = await ledger.snapshot()
    assert snapshot["blocked"] is True
    assert Decimal(snapshot["charged_dollars"]) == Decimal("0.10205")
    with pytest.raises(InferenceError, match="BUDGET_EXHAUSTED"):
        await wrapper.generate_structured(**request())
    assert adapter.calls == 1


async def test_unbounded_timeout_is_rejected_before_send():
    adapter = Adapter()
    adapter.settings.hf_request_timeout_seconds = 60
    with pytest.raises(InferenceError, match="TIMEOUT_POLICY_MISMATCH"):
        await BudgetedInference(adapter, budget(), policy()).generate_structured(**request())
    assert adapter.calls == 0


async def test_provenance_mismatch_retains_full_charge():
    class WrongProvider(Adapter):
        async def generate_structured(self, **kwargs):
            result = await super().generate_structured(**kwargs)
            result.provenance["provider"] = "other"
            return result

    ledger = budget()
    with pytest.raises(InferenceError, match="PROVENANCE_MISMATCH"):
        await BudgetedInference(WrongProvider(), ledger, policy()).generate_structured(**request())
    entry = (await ledger.snapshot())["entries"][0]
    assert entry["charged_dollars"] == entry["reserved_dollars"]
    assert entry["status"] == "provenance_mismatch"


async def test_optional_calls_cannot_spend_remaining_mandatory_capacity():
    ledger = budget(Decimal("1"), Decimal("0.99"))
    adapter = Adapter()
    with pytest.raises(InferenceError, match="BUDGET_EXHAUSTED"):
        await BudgetedInference(adapter, ledger, policy(), mandatory=False).generate_structured(
            **request())
    assert adapter.calls == 0
    await BudgetedInference(adapter, ledger, policy()).generate_structured(**request())
    snapshot = await ledger.snapshot()
    assert Decimal(snapshot["mandatory_reserve_dollars"]) == Decimal("0.98988")
    assert Decimal(snapshot["charged_dollars"]) == Decimal("0.00012")
    assert snapshot["storage"] == "in_memory_not_restart_safe"


async def test_reservations_cannot_be_settled_twice():
    ledger = budget()
    key = await ledger.reserve(Decimal("0.1"), mandatory=True, policy_id="test")
    await ledger.settle(key, Decimal("0.1"), status="unreported")
    with pytest.raises(ValueError, match="already settled"):
        await ledger.settle(key, Decimal("0.1"), status="unreported")


def test_forecast_protects_both_versions_and_labels_unmeasured_assumptions():
    result = forecast_experiment(policy=policy(), input_tokens_per_call=6000, calls_per_session=9)
    assert result["sessions"] == 1025
    assert result["maximum_provider_attempts"] == 1025 * 9 * 2
    assert Decimal(result["reserved_dollars"]) == Decimal("148.4856")
    assert Decimal(result["seconds_with_30_percent_contingency"]) == Decimal("39975")
    assert result["evidence"] == "assumption_only_not_measured"
    with pytest.raises(ValueError):
        forecast_experiment(policy=policy(), input_tokens_per_call=1, calls_per_session=0)
