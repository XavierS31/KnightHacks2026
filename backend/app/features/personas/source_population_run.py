"""Explicit local HF population generation; never starts browser experiments."""
import argparse
import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from backend.app.features.personas.behavior_extraction import BehaviorProposals, PendingExtraction
from backend.app.features.personas.generation_batches import (
    CheckpointedDetailBatches,
    FictionalDetailBatch,
    batch_messages,
)
from backend.app.features.personas.inference_budget import BudgetedInference
from backend.app.features.personas.live_readiness import qwen_smoke_policy
from backend.app.features.personas.local_generation_budget import LocalGenerationBudget
from backend.app.features.personas.population import (
    FrozenPopulation,
    IndependentSupportReview,
    PopulationError,
    approve_behavior,
    generate_population,
    population_messages,
)
from backend.app.features.personas.product_handoff import consume_sourcetable_handoff
from backend.app.features.personas.review_corpus import FrozenCorpus
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings

GENERATION_VERSION = "sourcetable-fictional-batches5-v1"
APPROVAL_REFERENCE = "user-4usd-cap-and-explicit-sourcetable500-request"


def _read(path):
    raw = path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise PopulationError("LOCAL_INPUT_TOO_LARGE")
    return json.loads(raw)


def _freeze_file(path, text):
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise PopulationError("LOCAL_FROZEN_FILE_CONFLICT")
        return
    import os
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def inputs(corpus_path, directory):
    record = _read(corpus_path)
    corpus = FrozenCorpus(record["snapshot_json"], record["version"])
    extraction = _read(directory / "extraction.json")
    review = IndependentSupportReview.model_validate(_read(directory / "support-review.json"))
    audit = _read(directory / "support-review-audit-v3.json")
    if (extraction["status"] != "pending_independent_support_review"
            or audit["corpus_version"] != corpus.version
            or audit["reviewer_ref"] != review.reviewer_ref
            or audit["extraction_digest"] != hashlib.sha256(
                extraction["output_json"].encode()).hexdigest()
            or audit["supported_pattern_ids"] != [str(d.pattern_id) for d in review.decisions]):
        raise PopulationError("INDEPENDENT_AUDIT_MISMATCH")
    draft = PendingExtraction(corpus.version, extraction["output_json"],
                              extraction["provenance_json"])
    return corpus, approve_behavior(draft, corpus, review)


def forecast(binding, approved_data, policy):
    proposals = BehaviorProposals.model_validate(approved_data["proposals"])
    accepted = {d["pattern_id"] for d in approved_data["review"]["decisions"]}
    patterns = [p.pattern for p in proposals.proposals if str(p.pattern.id) in accepted]
    tasks = {t.id: t for t in binding.tasks()}
    total = Decimal(0)
    index = 0
    for quota in binding.quotas():
        if quota.count % 5:
            raise PopulationError("BATCH_QUOTA_NOT_DIVISIBLE_BY_FIVE")
        for _ in range(quota.count // 5):
            messages = batch_messages(population_messages(
                quota, tasks[quota.task_template_id], proposals.software_context, patterns), index)
            total += 2 * policy.cost(policy.input_bound(messages, FictionalDetailBatch), 1024)
            index += 1
    return {"provider_calls": index, "maximum_attempts": index * 2,
            "worst_case_new_dollars": str(total), "basis": "conservative_reservation_not_invoice"}


def persist_neon(corpus, approved, population, settings):
    # C owns this persistence boundary; do not reinterpret missing DB as success.
    if not settings.database_url.get_secret_value():
        return {"status": "blocked", "code": "DATABASE_URL_MISSING"}
    from backend.app.features.evolution.population_repository import (
        PopulationRepository,
        ReviewerIdentity,
    )
    from backend.app.shared.database import NeonDatabase
    database = NeonDatabase(settings)
    try:
        repository = PopulationRepository(database)
        population_id = repository.save_bundle(corpus, approved, population,
            reviewer=ReviewerIdentity(operator_ref="authorized-local-operator",
                independent_reviewer_ref=approved.data(corpus)["review"]["reviewer_ref"]))
        readback = repository.load_population(population.version)
        if readback != population:
            raise PopulationError("NEON_READBACK_MISMATCH")
        return {"status": "persisted_readback_verified", "population_id": str(population_id)}
    except Exception:
        return {"status": "blocked", "code": "NEON_WRITE_READBACK_FAILED"}
    finally:
        database.close()


async def run(*, corpus_path: Path, directory: Path, remaining_budget: Decimal,
              persist: bool = False):
    if not remaining_budget.is_finite() or not Decimal(0) < remaining_budget <= Decimal(4):
        raise PopulationError("INVALID_AUTHORIZED_REMAINING_BUDGET")
    corpus, approved = inputs(corpus_path, directory)
    binding = consume_sourcetable_handoff()
    policy = qwen_smoke_policy()
    plan = forecast(binding, approved.data(corpus), policy)
    ledger = LocalGenerationBudget(directory, "sourcetable-500-generation-20261010",
        remaining_budget, approval_reference=APPROVAL_REFERENCE)
    settings = Settings(app_mode="live", experiment_budget_limit=float(remaining_budget))
    adapter = HuggingFaceInference(settings)
    report = {"status": "blocked", "configured_count": 0, "completed_trials": 0,
              "forecast": plan, "handoff": binding.report(), "corpus_version": corpus.version,
              "approval_version": approved.version,
              "reviewer_authentication": "local_operator_attestation_not_hosted_human_identity"}
    try:
        _freeze_file(directory / "approved-behavior.json", approved.snapshot_json)
        _freeze_file(directory / "handoff-binding.json", binding.snapshot_json)
        output = directory / "population.json"
        if output.exists():
            snapshot = output.read_text(encoding="utf-8")
            population = FrozenPopulation(snapshot, hashlib.sha256(snapshot.encode()).hexdigest())
            data = population.data()
            if (data["approval_version"] != approved.version
                    or data["corpus_version"] != corpus.version
                    or data["generation_version"] != GENERATION_VERSION):
                raise PopulationError("LOCAL_POPULATION_INPUT_MISMATCH")
        else:
            budget = await ledger.snapshot()
            if (Decimal(budget["charged_dollars"]) + Decimal(plan["worst_case_new_dollars"])
                    > remaining_budget):
                raise PopulationError("GENERATION_FORECAST_EXCEEDS_REMAINING_CAP")
            batches = CheckpointedDetailBatches(BudgetedInference(adapter, ledger, policy),
                                               directory / "chunks")
            population = await generate_population(corpus, approved, batches,
                quotas=binding.quotas(), task_templates=binding.tasks(),
                generation_version=GENERATION_VERSION, purpose="complete")
            batches.assert_complete()
            _freeze_file(output, population.snapshot_json)
        _freeze_file(directory / "population.sha256", population.version)
        report.update(status="configured_population_local_persisted", configured_count=500,
                      population_version=population.version)
        report["neon"] = (persist_neon(corpus, approved, population, settings) if persist
                          else {"status": "not_requested"})
    except InferenceError as failure:
        report.update(code=failure.code, retryable=failure.retryable)
    except PopulationError as failure:
        report.update(code=str(failure))
    except Exception:
        report.update(code="GENERATION_RUN_FAILED")
    finally:
        report["budget"] = await ledger.snapshot()
        report["durable_chunk_count"] = len(list((directory / "chunks").glob("batch-*.json")))
        (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        await adapter.close()
        ledger.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--remaining-budget", type=Decimal, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--persist-neon", action="store_true")
    args = parser.parse_args()
    try:
        report = asyncio.run(run(corpus_path=args.corpus, directory=args.directory,
            remaining_budget=args.remaining_budget, persist=args.persist_neon))
        print(json.dumps({k: v for k, v in report.items() if k != "budget"}, indent=2))
        if report["configured_count"] != 500:
            raise SystemExit(1)
    except (FileExistsError, PopulationError):
        print('{"status":"blocked","code":"LOCAL_GENERATION_GUARD_REJECTED"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
