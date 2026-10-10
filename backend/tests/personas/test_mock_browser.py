"""Opt-in local Chromium checks; no external APIs or paid inference."""
import asyncio
import os

import pytest
from playwright.async_api import async_playwright

from backend.app.features.personas.mock_handoff import mock_handoff, mock_population
from backend.app.features.personas.mock_product import serve_mock_product
from backend.app.features.personas.mock_worker import BrowserDecision, run_mock_trial

pytestmark = pytest.mark.skipif(os.environ.get("B_BROWSER_TESTS") != "1",
                                reason="Set B_BROWSER_TESTS=1 for local Chromium checks")


@pytest.fixture
async def browser():
    async with async_playwright() as playwright:
        instance = await playwright.chromium.launch()
        yield instance
        await instance.close()


async def test_observed_mock_success_frames_and_context_isolation(browser):
    population = mock_population(2)
    with serve_mock_product() as url:
        handoff = mock_handoff(population, url)
        results = await asyncio.gather(*(
            run_mock_trial(browser, handoff, persona, task.id)
            for persona, task in zip(population, handoff.tasks, strict=True)
        ))
    assert results[0].run_id != results[1].run_id
    for result in results:
        assert result.status == "check_success"
        assert [a["kind"] for a in result.actions] == ["navigate", "click", "click", "check"]
        assert [a["target"] for a in result.actions[1:3]] == ["load-sample", "generate-cards"]
        assert len(result.frames) == 4
        assert all(f.run_id == result.run_id and f.png.startswith(b"\x89PNG") for f in result.frames)
        assert [f.sequence for f in result.frames] == [1, 2, 3, 4]
        assert not result.counts_as_mandatory_trial
        assert result.mode == "fixture" and not result.inference_used
        assert "png" not in str(result.summary())
    assert browser.contexts == []


@pytest.mark.parametrize("failure,status", [("application", "application_failure"),
                                           ("timeout", "policy_stopped")])
async def test_mock_failure_does_not_become_success(browser, failure, status):
    population = mock_population(1)
    with serve_mock_product(failure) as url:
        handoff = mock_handoff(population, url)
        result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id)
    assert result.status == status
    assert not result.counts_as_mandatory_trial
    assert len(result.actions) <= 6
    assert browser.contexts == []


async def test_unobserved_target_cannot_execute(browser):
    class InvalidPolicy:
        async def decide(self, targets):
            return BrowserDecision(kind="click", target_id="invented-selector")

    population = mock_population(1)
    with serve_mock_product() as url:
        handoff = mock_handoff(population, url)
        result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id,
                                      policy=InvalidPolicy())
    assert result.status == "invalid_target"
    assert not any(a["kind"] == "click" for a in result.actions)


async def test_cancellation_before_or_between_actions(browser):
    cancel = asyncio.Event()

    class CancelPolicy:
        async def decide(self, targets):
            cancel.set()
            return BrowserDecision(kind="click", target_id="load-sample")

    population = mock_population(1)
    with serve_mock_product() as url:
        handoff = mock_handoff(population, url)
        result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id,
                                      cancel=cancel, policy=CancelPolicy())
        before = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id,
                                      cancel=cancel)
    assert result.status == before.status == "cancelled"
    assert not any(a["kind"] == "click" for a in result.actions)
    assert before.frames == before.actions == []
    assert browser.contexts == []


async def test_action_limit_and_recovery(browser):
    class RepeatingPolicy:
        async def decide(self, targets):
            return BrowserDecision(kind="click", target_id="load-sample")

    population = mock_population(1)
    with serve_mock_product() as url:
        handoff = mock_handoff(population, url)
        result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id,
                                      policy=RepeatingPolicy())
        recovered = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id)
    assert result.status == "action_limit"
    assert len(result.actions) == handoff.tasks[0].action_budget == 6
    assert recovered.status == "check_success"
    assert recovered.run_id != result.run_id
    assert browser.contexts == []


async def test_initial_state_mismatch_blocks_generation(browser):
    population = mock_population(1)
    with serve_mock_product() as url:
        handoff = mock_handoff(population, url)
        handoff.initial_states[0].notes = "Different initial state"
        result = await run_mock_trial(browser, handoff, population[0], handoff.tasks[0].id)
    assert result.status == "invalid_initial_state"
    assert not any(a["target"] == "generate-cards" for a in result.actions)
