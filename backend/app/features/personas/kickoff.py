"""B's offline kickoff and explicitly opted-in HF configuration smoke check."""
import argparse
import asyncio
import json

from backend.app.features.personas.mock_handoff import (
    mock_experiment,
    mock_handoff,
    mock_population,
)
from backend.app.features.personas.mock_product import serve_mock_product
from backend.app.features.personas.mock_worker import BrowserDecision, run_mock_trial
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import get_settings


async def hf_smoke():
    """At most one logical request (adapter can retry once); no population/batch execution."""
    settings = get_settings()
    adapter = HuggingFaceInference(settings)
    try:
        response = await adapter.generate_structured(
            role="browser_persona_configuration_smoke", output_schema=BrowserDecision,
            prompt_version="b-mock-hf-smoke-v1", messages=[
                {"role": "system", "content": "Choose one action from the supplied observed targets. "
                 "Use click with target_id for a supported target; stop uses null target_id. "
                 "This is a synthetic configuration test, not a real persona or product trial."},
                {"role": "user", "content": json.dumps({
                    "briefing": "Mock product: load sample then generate study cards.",
                    "goal": "Try the sample", "observed_targets": [
                        {"id": "load-sample", "name": "Load sample"}],
                    "action_budget_remaining": 6,
                })},
            ],
        )
        if response.value.kind != "click" or response.value.target_id != "load-sample":
            return {"status": "failed", "code": "UNSUPPORTED_SMOKE_DECISION"}
        return {"status": "validated_configuration_smoke", "input_mode": "fixture",
                "inference_used": True, "counts_as_mandatory_trial": False,
                "decision": response.value.model_dump(), "provenance": response.provenance}
    except InferenceError as failure:
        return {"status": "failed", "code": failure.code, "retryable": failure.retryable}
    finally:
        await adapter.close()


async def browser_smoke(failure: str):
    from playwright.async_api import async_playwright

    population = mock_population(1)
    with serve_mock_product(failure) as url:
        handoff = mock_handoff(population, url)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id)
                return result.summary()
            finally:
                await browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="Run one mock Chromium task; no HF")
    mode.add_argument("--hf-smoke", action="store_true", help="Explicitly opt into a potentially paid "
                      "HF request; requires live mode, token/model/provider and positive budget")
    mode.add_argument("--handoff", action="store_true", help="Print the complete synthetic A input")
    parser.add_argument("--failure", choices=["none", "application", "timeout"], default="none")
    args = parser.parse_args()
    if args.hf_smoke:
        result = asyncio.run(hf_smoke())
    elif args.browser:
        try:
            result = asyncio.run(browser_smoke(args.failure))
        except Exception:
            result = {"status": "failed", "code": "MOCK_BROWSER_UNAVAILABLE",
                      "next_step": "Install Chromium with: python -m playwright install chromium"}
    else:
        population = mock_population()
        handoff = mock_handoff(population)
        result = handoff.model_dump(mode="json") if args.handoff else {
            "mode": "fixture", "configured_personas": len(population),
            "configured_tasks": len(handoff.tasks),
            "experiment": mock_experiment(handoff, population).model_dump(mode="json"),
            "source_commits_available": False, "inference_used": False,
            "next_gate": "HF configuration smoke; real review corpus and C persistence; "
                         "replace mock handoff with A's validated product before real trials",
        }
    print(json.dumps(result, indent=2))
    if result.get("status") in {"failed", "infrastructure_failure", "invalid_target",
                               "invalid_initial_state", "unexpected_mock_product"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
