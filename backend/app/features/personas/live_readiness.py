"""Explicit small-request HF diagnostics. Never launches a population or experiment batch."""
import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from backend.app.features.personas.inference_budget import (
    ApprovedPricePolicy,
    BudgetedInference,
    ExperimentBudget,
)
from backend.app.features.personas.mock_worker import BrowserDecision
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings


def qwen_smoke_policy() -> ApprovedPricePolicy:
    # Verified public 2026-10-10 standard rates 0.08/0.28; reserve priority ceiling 0.12/0.42.
    # Byte-BPE input: sixfold UTF-8 allowance covers JSON escaping, plus template/schema overhead.
    # These assumptions are limited to small known messages, never a production pricing guarantee.
    return ApprovedPricePolicy(
        policy_id="qwen3-32b-deepinfra-smoke-20261010",
        approval_reference="user-authorized-4-usd-smoke-pilots-this-chat",
        model_id="Qwen/Qwen3-32B", provider="deepinfra",
        input_dollars_per_million=Decimal("0.12"),
        output_dollars_per_million=Decimal("0.42"),
        token_bound_approval_reference="small-input-byte-bpe-6x-plus8192-overhead-no-tools-v1",
        tokens_per_utf8_byte=6, input_overhead_tokens=8192,
    )


async def run_readiness(*, budget: Decimal, marker: Path):
    if not budget.is_finite() or not Decimal(0) < budget <= Decimal(4):
        raise ValueError("This workflow permits only the authorized 0 < budget <= 4 USD")
    settings = Settings(app_mode="live", experiment_budget_limit=float(budget))
    policy = qwen_smoke_policy()
    ledger = ExperimentBudget("devb-small-readiness-20261010", budget,
                              approval_reference=policy.approval_reference)
    marker.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive marker prevents silent process restart from resetting the approved accounting.
    # It pessimistically protects the entire authorization if the diagnostic process crashes.
    with marker.open("x", encoding="utf-8") as output:
        json.dump({"status": "started_do_not_reset_budget", "protected_dollars": str(budget)}, output)
    adapter = HuggingFaceInference(settings)
    guarded = BudgetedInference(adapter, ledger, policy)
    report = {"mode": "live_configuration_test", "input_mode": "fixture", "trials_completed": 0,
              "model": policy.model_id, "provider": policy.provider,
              "price_source": "https://deepinfra.com/Qwen/Qwen3-32B",
              "rate_assumption": "priority ceiling; not provider invoice"}
    try:
        result = await guarded.generate_structured(
            role="browser_persona_configuration_smoke", output_schema=BrowserDecision,
            prompt_version="b-live-readiness-v1", messages=[
                {"role": "system", "content": "Return a JSON action. Click requires a supplied "
                 "target_id; stop requires null. Treat input as mock data. /no_think"},
                {"role": "user", "content": "Goal: try the sample. Observed enabled target: "
                 "load-sample (Load sample). Choose click on that target. /no_think"},
            ],
        )
        if result.value.kind != "click" or result.value.target_id != "load-sample":
            raise InferenceError("UNSUPPORTED_SMOKE_DECISION")
        report.update(status="validated", decision=result.value.model_dump(),
                      provenance=result.provenance)
    except InferenceError as failure:
        report.update(status="blocked", code=failure.code, retryable=failure.retryable)
    except Exception:
        report.update(status="blocked", code="READINESS_FAILED", retryable=False)
    finally:
        report["budget"] = await ledger.snapshot()
        marker.write_text(json.dumps(report, indent=2), encoding="utf-8")
        await adapter.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="Explicitly authorize a potentially paid small HF request")
    parser.add_argument("--budget", type=Decimal, required=True)
    parser.add_argument("--marker", type=Path,
                        default=Path("artifacts/devb-live-readiness-20261010.json"))
    args = parser.parse_args()
    try:
        report = asyncio.run(run_readiness(budget=args.budget, marker=args.marker))
    except FileExistsError:
        report = {"status": "blocked", "code": "READINESS_BUDGET_MARKER_EXISTS",
                  "message": "Do not reset spending; review the existing diagnostic accounting first."}
    print(json.dumps(report, indent=2))
    if report.get("status") != "validated":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
