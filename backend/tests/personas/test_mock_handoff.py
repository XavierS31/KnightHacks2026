from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.features.personas.mock_handoff import (
    MockHandoff,
    mock_experiment,
    mock_handoff,
    mock_population,
    select_task,
)
from backend.app.features.personas.mock_worker import BrowserDecision, require_mock_origin
from backend.app.shared.contracts import PersonaSummary


def test_complete_mock_a_handoff_has_resolvable_task_lineage():
    population = mock_population()
    handoff = mock_handoff(population)
    assert len(population) == len(handoff.tasks) == 500
    assert len({p.id for p in population}) == len({p.scenario.id for p in population}) == 500
    assert len({t.id for t in handoff.tasks}) == 500
    assert handoff.version.commit_sha is None
    assert not handoff.source_commits_available
    for persona, task in zip(population, handoff.tasks, strict=True):
        assert select_task(handoff, persona, task.id) == task
        assert persona.software_behavior.status == "fixture"
    assert mock_population()[499].id == population[499].id
    counts = mock_experiment(handoff, population).counts
    assert counts.configured == 500
    assert counts.completed == counts.running == counts.queued == counts.failed == 0


def test_population_is_deeply_isolated_and_never_live():
    population = mock_population(2)
    population[0].software_behavior.patterns[0].tendency = "changed locally"
    assert population[1].software_behavior.patterns[0].tendency != "changed locally"
    assert mock_population(1)[0].software_behavior.patterns[0].tendency != "changed locally"
    with pytest.raises(ValidationError, match="review-informed"):
        PersonaSummary(mode="live", personas=population, experiments=[], sessions=[], next_gate="")


@pytest.mark.parametrize("count", [0, -1, 501])
def test_fixture_population_is_bounded(count):
    with pytest.raises(ValueError):
        mock_population(count)


@pytest.mark.parametrize("field,value", [
    ("check_id", "unknown"), ("initial_state_ref", "unknown"),
    ("capability_ids", [str(uuid4())]), ("action_budget", 7),
])
def test_invalid_task_catalog_rejected(field, value):
    data = mock_handoff(mock_population(1)).model_dump(mode="json")
    data["tasks"][0][field] = value
    with pytest.raises(ValidationError):
        MockHandoff.model_validate(data)


def test_mock_cannot_promote_capability_or_version():
    data = mock_handoff(mock_population(1)).model_dump(mode="json")
    data["version"]["capabilities"][0]["validated"] = True
    with pytest.raises(ValidationError):
        MockHandoff.model_validate(data)


def test_task_selection_is_persona_scoped():
    population = mock_population(2)
    handoff = mock_handoff(population)
    with pytest.raises(ValueError):
        select_task(handoff, population[0], handoff.tasks[1].id)
    with pytest.raises(ValueError):
        select_task(handoff, population[0], uuid4())


@pytest.mark.parametrize("url", ["https://example.com/", "http://localhost:8000/",
                                   "http://127.0.0.1:8000/path", "http://secret@127.0.0.1:8000/",
                                   "http://127.0.0.1:8000/?token=secret"])
def test_mock_origin_rejects_external_or_secret_urls(url):
    with pytest.raises(ValueError):
        require_mock_origin(url)


@pytest.mark.parametrize("decision", [
    {"kind": "click", "target_id": None}, {"kind": "stop", "target_id": "load-sample"},
    {"kind": "execute_js", "target_id": "alert(1)"},
    {"kind": "click", "target_id": "load-sample", "script": "bad"},
])
def test_decisions_cannot_request_arbitrary_tools(decision):
    with pytest.raises(ValidationError):
        BrowserDecision.model_validate(decision)


async def test_hf_smoke_fixture_mode_cannot_call_provider(monkeypatch):
    from backend.app.features.personas.kickoff import hf_smoke

    monkeypatch.setenv("APP_MODE", "fixture")
    result = await hf_smoke()
    assert result == {"status": "failed", "code": "FIXTURE_INFERENCE_FORBIDDEN", "retryable": False}
