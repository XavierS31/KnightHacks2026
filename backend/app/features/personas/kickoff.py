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
from backend.app.features.personas.mock_worker import run_mock_trial
from backend.app.shared.settings import get_settings


async def hf_smoke():
    """Legacy entry point cannot bypass the explicit dollar reservation workflow."""
    settings = get_settings()
    if settings.app_mode == "fixture":
        return {"status": "failed", "code": "FIXTURE_INFERENCE_FORBIDDEN", "retryable": False}
    return {"status": "failed", "code": "USE_BUDGETED_LIVE_READINESS", "retryable": False,
            "next_step": "Use personas.live_readiness --run --budget with reviewed accounting; "
                         "never reset an existing spending marker."}


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
