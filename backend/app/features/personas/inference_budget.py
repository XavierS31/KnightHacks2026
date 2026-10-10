"""Opt-in, in-memory HF dollar reservations; NOT durable experiment accounting.

The current shared adapter sends at most two requests, each with max_tokens=1024.
It reports usage only for the successful final attempt. Any preceding attempt,
failed call, cancellation or absent usage therefore retains its worst-case charge.
No ambiguous send is automatically refunded. Prices and tokenizer bounds require
explicit approval for the exact provider/model. This module does not launch jobs.

The approved input bound is UTF-8 bytes of the complete messages/schema envelope
times an approved multiplier, plus an approved chat-template/provider overhead.
One token per UTF-8 byte and 4096 overhead are conservative starting assumptions,
NOT a universal tokenizer guarantee. The approver must verify that provider's
serialization/template/tokenization fits them (or increase them); expansion,
tool injection, changing prices or adapter limits invalidates that approval.
"""

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from backend.app.shared.inference import InferenceError

MILLION = Decimal(1_000_000)
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 1024


def _dollars(value: Decimal, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("Dollar values require finite nonnegative Decimal amounts")
    if positive and value == 0:
        raise ValueError("An explicit positive dollar limit is required")
    return value


@dataclass(frozen=True)
class ApprovedPricePolicy:
    """Approval is supplied by the caller, never inferred from settings or credits."""

    policy_id: str
    approval_reference: str
    model_id: str
    provider: str
    input_dollars_per_million: Decimal
    output_dollars_per_million: Decimal
    token_bound_approval_reference: str
    tokens_per_utf8_byte: int = 1
    input_overhead_tokens: int = 4096

    def __post_init__(self):
        for value in (self.policy_id, self.approval_reference, self.model_id,
                      self.provider, self.token_bound_approval_reference):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Explicit price and tokenizer approval references are required")
        _dollars(self.input_dollars_per_million)
        _dollars(self.output_dollars_per_million)
        if (type(self.tokens_per_utf8_byte) is not int or self.tokens_per_utf8_byte < 1
                or type(self.input_overhead_tokens) is not int or self.input_overhead_tokens < 4096):
            raise ValueError("Input bounds must include bytes and provider/template overhead")

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (input_tokens * self.input_dollars_per_million
                + output_tokens * self.output_dollars_per_million) / MILLION

    def input_bound(self, messages: list[dict[str, str]], output_schema: Any) -> int:
        envelope = {"messages": messages, "response_format": {
            "type": "json_schema", "json_schema": {
                "name": output_schema.__name__, "strict": True,
                "schema": output_schema.model_json_schema(),
            }}}
        size = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        return size * self.tokens_per_utf8_byte + self.input_overhead_tokens


class ExperimentBudget:
    """Single process/event-loop ledger. C must persist atomically before scaling.

    Snapshot values are decimal strings. They are a storage handoff, not a restart
    mechanism: constructing a new ledger must not reset an existing experiment.
    mandatory_reserve protects remaining mandatory calls from optional consumption.
    """

    def __init__(self, experiment_id: str, limit: Decimal, *,
                 approval_reference: str, mandatory_reserve: Decimal = Decimal(0)):
        if not experiment_id.strip() or not approval_reference.strip():
            raise ValueError("Experiment and budget approval reference are required")
        self.experiment_id = experiment_id
        self.limit = _dollars(limit, positive=True)
        self.approval_reference = approval_reference
        self.mandatory_reserve = _dollars(mandatory_reserve)
        if mandatory_reserve > limit:
            raise ValueError("Mandatory reserve exceeds approved budget")
        self._lock = asyncio.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._charged = Decimal(0)
        self._reserved = Decimal(0)
        self._blocked = False

    async def reserve(self, amount: Decimal, *, mandatory: bool, policy_id: str) -> str:
        _dollars(amount)
        if type(mandatory) is not bool or not policy_id.strip():
            raise ValueError("Mandatory classification and policy reference are required")
        async with self._lock:
            floor = Decimal(0) if mandatory else self.mandatory_reserve
            if self._blocked or self._charged + self._reserved + amount + floor > self.limit:
                raise InferenceError("EXPERIMENT_BUDGET_EXHAUSTED")
            key = str(uuid4())
            protected = min(amount, self.mandatory_reserve) if mandatory else Decimal(0)
            self.mandatory_reserve -= protected
            self._reserved += amount
            self._entries[key] = {
                "reserved_dollars": amount, "charged_dollars": None,
                "status": "reserved", "mandatory": mandatory,
                "protected_dollars": protected, "policy_id": policy_id,
            }
            return key

    async def settle(self, reservation_id: str, charge: Decimal, *, status: str):
        _dollars(charge)
        if not status.strip() or status == "reserved":
            raise ValueError("Settlement requires a terminal accounting status")
        async with self._lock:
            entry = self._entries[reservation_id]
            if entry["status"] != "reserved":
                raise ValueError("Reservation already settled")
            reserved = entry["reserved_dollars"]
            self._reserved -= reserved
            self._charged += charge
            if entry["mandatory"]:
                # Savings stay protected for remaining mandatory participation.
                self.mandatory_reserve += min(entry["protected_dollars"],
                                              max(Decimal(0), reserved - charge))
            entry.update(charged_dollars=charge, status=status)
            if charge > reserved or status == "policy_bound_violated":
                self._blocked = True  # Pricing/token-bound policy violated; stop all further sends.

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "storage": "in_memory_not_restart_safe", "experiment_id": self.experiment_id,
                "approval_reference": self.approval_reference, "limit_dollars": str(self.limit),
                "charged_dollars": str(self._charged), "reserved_dollars": str(self._reserved),
                "mandatory_reserve_dollars": str(self.mandatory_reserve), "blocked": self._blocked,
                "entries": [{"reservation_id": key, **{
                    name: str(value) if isinstance(value, Decimal) else value
                    for name, value in entry.items()}} for key, entry in self._entries.items()],
            }


class BudgetedInference:
    """Duck-type generate_structured wrapper around the bounded shared HF adapter.

    Private adapter configuration mutation or replacing its retry/token limits is
    outside this policy; each request checks exposed model/provider settings. No
    external provider credentials, prices or positive Settings limit imply approval.
    """

    def __init__(self, adapter: Any, ledger: ExperimentBudget, policy: ApprovedPricePolicy,
                 *, mandatory: bool = True):
        self.adapter, self.ledger, self.policy = adapter, ledger, policy
        self.mandatory = mandatory

    async def generate_structured(self, **kwargs):
        settings = self.adapter.settings
        model = ((settings.hf_coding_model_id if kwargs.get("coding", False) else "")
                 or settings.hf_model_id)
        if model != self.policy.model_id or settings.hf_provider != self.policy.provider:
            raise InferenceError("PRICE_POLICY_MODEL_PROVIDER_MISMATCH")
        timeout = settings.hf_request_timeout_seconds
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 20:
            raise InferenceError("INFERENCE_TIMEOUT_POLICY_MISMATCH")
        context = dict(kwargs.get("request_context") or {})
        if context.get("experiment_id", self.ledger.experiment_id) != self.ledger.experiment_id:
            raise InferenceError("BUDGET_EXPERIMENT_MISMATCH")
        context["experiment_id"] = self.ledger.experiment_id
        kwargs["request_context"] = context
        input_bound = self.policy.input_bound(kwargs["messages"], kwargs["output_schema"])
        per_attempt = self.policy.cost(input_bound, MAX_OUTPUT_TOKENS)
        worst_case = MAX_ATTEMPTS * per_attempt
        key = await self.ledger.reserve(worst_case, mandatory=self.mandatory,
                                        policy_id=self.policy.policy_id)
        try:
            result = await self.adapter.generate_structured(**kwargs)
        except BaseException:
            # Cancellation can occur after send. Keep the reservation on interruption,
            # even if this settlement is itself interrupted; that is conservative.
            await self.ledger.settle(key, worst_case, status="unreported_or_failed")
            raise
        provenance = result.provenance
        if (provenance.get("model_id") != model
                or provenance.get("provider") != self.policy.provider):
            await self.ledger.settle(key, worst_case, status="provenance_mismatch")
            raise InferenceError("INFERENCE_PROVENANCE_MISMATCH")
        usage = provenance.get("token_usage_if_reported")
        retry_count = provenance.get("retry_count")
        charge, status = worst_case, "unreported_usage"
        if (isinstance(usage, dict) and type(retry_count) is int
                and 0 <= retry_count < MAX_ATTEMPTS
                and all(type(usage.get(name)) is int and usage[name] >= 0
                        for name in ("prompt_tokens", "completion_tokens", "total_tokens"))
                and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]):
            charge = (retry_count * per_attempt + self.policy.cost(
                usage["prompt_tokens"], usage["completion_tokens"]))
            status = "reported_final_attempt"
            if (usage["prompt_tokens"] > input_bound
                    or usage["completion_tokens"] > MAX_OUTPUT_TOKENS):
                # Charge reported overage, retain at least the full reservation, and stop.
                charge = max(charge, worst_case)
                status = "policy_bound_violated"
        await self.ledger.settle(key, charge, status=status)
        if status == "policy_bound_violated":
            raise InferenceError("INFERENCE_TOKEN_BOUND_VIOLATED")
        return result


def forecast_experiment(*, policy: ApprovedPricePolicy, input_tokens_per_call: int,
                        calls_per_session: int, workers: int = 4,
                        assumed_seconds_per_session: Decimal = Decimal(120)) -> dict[str, Any]:
    """Planning assumptions only; no measured throughput/provider/CPU evidence.

    Reserves two calls per role invocation and 1024 output tokens per attempt.
    1000 mandatory matched sessions + five pilots + twenty soak sessions = 1025.
    Generation/extraction and optional work require a separate cost allocation.
    """
    if any(type(value) is not int or value < 1
           for value in (input_tokens_per_call, calls_per_session, workers)):
        raise ValueError("Positive integer forecast inputs are required")
    _dollars(assumed_seconds_per_session, positive=True)
    sessions = 1000 + 5 + 20
    role_calls = sessions * calls_per_session
    return {
        "evidence": "assumption_only_not_measured", "sessions": sessions,
        "mandatory_sessions": 1000, "pilot_sessions": 5, "soak_sessions": 20,
        "role_calls": role_calls, "maximum_provider_attempts": role_calls * MAX_ATTEMPTS,
        "workers": workers, "policy_id": policy.policy_id,
        "reserved_dollars": str(role_calls * MAX_ATTEMPTS
                                * policy.cost(input_tokens_per_call, MAX_OUTPUT_TOKENS)),
        "seconds_with_30_percent_contingency": str(
            sessions * assumed_seconds_per_session / workers * Decimal("1.30")),
        "limitations": ["Assumes homogeneous workers; CPU/memory not measured",
                        "Provider rate limits and queue latency not measured",
                        "Persona generation/review extraction costs excluded",
                        "No authorization to launch a full batch"],
    }
