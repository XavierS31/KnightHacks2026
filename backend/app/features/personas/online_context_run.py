"""Opt-in Neon population to Hugging Face context diagnostic; no browser trial."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backend.app.features.integration.handoff import load_handoff
from backend.app.features.personas.inference_budget import BudgetedInference
from backend.app.features.personas.live_readiness import qwen_smoke_policy
from backend.app.features.personas.local_generation_budget import LocalGenerationBudget
from backend.app.features.personas.online_context import probe_context
from backend.app.features.personas.online_population import load_neon_population
from backend.app.features.personas.product_handoff import ProductBinding
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings


def _approved_budget(directory: Path, journal_id: str, approval_reference: str) -> tuple[str, Decimal]:
    record = json.loads((directory / "budget.json").read_text(encoding="utf-8"))
    limit = Decimal(record["limit_dollars"])
    if (record["experiment_id"] != journal_id
            or record["approval_reference"] != approval_reference
            or not limit.is_finite() or not Decimal(0) < limit <= Decimal(4)
            or record["blocked"]):
        raise ValueError("SPEND_JOURNAL_NOT_APPROVED")
    version = (directory / "population.sha256").read_text(encoding="utf-8").strip()
    return version, limit


async def run(directory: Path, *, binding_path: Path, journal_id: str, approval_reference: str, index: int = 0) -> dict:
    """The population must be freshly read through C's Python repository before HF sends."""
    version, limit = _approved_budget(directory, journal_id, approval_reference)
    raw_binding = json.loads(binding_path.read_text())
    binding = ProductBinding(raw_binding["snapshot_json"], raw_binding["version"])
    if binding.data()["product_manifest"] != load_handoff().model_dump(mode="json"):
        raise ValueError("SELECTED_PROTOTYPE_BINDING_REQUIRED")
    settings = Settings(app_mode="live", experiment_budget_limit=float(limit))
    report = {"status": "blocked", "source": "neon_python_repository",
              "population_version": version, "trials_completed": 0,
              "started_at": datetime.now(UTC).isoformat()}
    try:
        bound = load_neon_population(settings, version, binding=binding)
    except Exception:
        report["code"] = "NEON_POPULATION_READ_FAILED"
        return report
    try:
        with_budget = LocalGenerationBudget(directory, journal_id, limit,
                                            approval_reference=approval_reference)
    except FileExistsError:
        report["code"] = "PAID_RUN_LOCK_EXISTS"
        return report
    adapter = HuggingFaceInference(settings)
    try:
        result = await probe_context(bound, index, BudgetedInference(
            adapter, with_budget, qwen_smoke_policy()))
        report.update(status="neon_to_hf_context_validated",
                      persona_id=str(result.choice.persona_id),
                      task_id=str(result.choice.task_id),
                      pattern_id=str(result.choice.pattern_id),
                      review_id=str(result.choice.review_id),
                      simulated_initial_relevance=result.choice.simulated_initial_relevance,
                      provenance=result.provenance)
    except InferenceError as failure:
        report.update(code=failure.code, retryable=failure.retryable)
    except Exception:
        report["code"] = "CONTEXT_DIAGNOSTIC_FAILED"
    finally:
        report["budget"] = await with_budget.snapshot()
        report["finished_at"] = datetime.now(UTC).isoformat()
        (directory / "online-context-neon-native-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        with_budget.close()
        await adapter.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="Use the existing guarded diagnostic budget for one HF request")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--journal-id", required=True)
    parser.add_argument("--approval-reference", required=True)
    arguments = parser.parse_args()
    report = asyncio.run(run(arguments.directory, index=arguments.index, binding_path=arguments.binding, journal_id=arguments.journal_id, approval_reference=arguments.approval_reference))
    print(json.dumps({key: report.get(key) for key in (
        "status", "code", "source", "population_version", "persona_id", "review_id",
        "trials_completed")}, sort_keys=True))
    if report["status"] != "neon_to_hf_context_validated":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
