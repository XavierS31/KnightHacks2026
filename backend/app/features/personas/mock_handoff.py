"""B-owned, in-memory substitute for A's unfinished handoff. Never a live product."""
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.app.shared.contracts import (
    Capability,
    Contract,
    Experiment,
    ExperimentCounts,
    Persona,
    ProductVersion,
    Repository,
    Task,
)
from backend.app.shared.fixtures import EVIDENCE, PERSONAS, REPOSITORIES, fixture_id


class Card(Contract):
    question: str
    answer: str


class SampleInput(Contract):
    notes: str = Field(min_length=1, max_length=2000)


class SampleOutput(Contract):
    cards: list[Card]


class MockCheck(Contract):
    id: str
    expected_cards: list[Card] = Field(min_length=1)


class MockState(Contract):
    id: str
    notes: str
    failure: Literal["none", "application", "timeout"] = "none"


class MockHandoff(Contract):
    mode: Literal["fixture"] = "fixture"
    repositories: list[Repository]
    version: ProductVersion
    initial_states: list[MockState]
    checks: list[MockCheck]
    tasks: list[Task]
    source_commits_available: Literal[False] = False

    @model_validator(mode="after")
    def references_resolve(self):
        if self.version.status != "fixture" or any(c.validated for c in self.version.capabilities):
            raise ValueError("Mock capabilities/version cannot claim integration validation")
        if any(r.discovery_mode != "fixture" or r.commit_sha for r in self.repositories):
            raise ValueError("Mock repositories cannot claim real source execution")
        for records in (self.repositories, self.version.capabilities, self.initial_states,
                        self.checks, self.tasks):
            if len({item.id for item in records}) != len(records):
                raise ValueError("Duplicate handoff identity")
        states = {s.id for s in self.initial_states}
        checks = {c.id for c in self.checks}
        capabilities = {c.id for c in self.version.capabilities}
        for task in self.tasks:
            if task.initial_state_ref not in states or task.check_id not in checks:
                raise ValueError("Task state/check reference does not resolve")
            if not task.capability_ids or not set(task.capability_ids) <= capabilities:
                raise ValueError("Task capability is unsupported")
            if not 2 <= task.action_budget <= 6:
                raise ValueError("Mock trial needs navigation/check and has a six-action maximum")
        return self


def mock_population(count: int = 500) -> list[Persona]:
    """Deterministic coverage fixtures, not HF-generated/review-informed population."""
    if not 1 <= count <= 500:
        raise ValueError("Fixture count must be between 1 and 500")
    population = []
    for index in range(count):
        template = PERSONAS[index % len(PERSONAS)]
        persona_id = fixture_id(f"b-mock-population-v1-persona-{index}")
        scenario = template.scenario.model_copy(update={
            "id": fixture_id(f"b-mock-population-v1-scenario-{index}"),
            "persona_id": persona_id,
            "goal": "Generate the two study cards from the provided sample notes",
        }, deep=True)
        population.append(template.model_copy(update={
            "id": persona_id,
            "synthetic_name": f"Mock persona {index + 1:03d}",
            "scenario": scenario,
        }, deep=True))
    return population


def mock_handoff(personas: list[Persona], runtime_url: str | None = None) -> MockHandoff:
    if len({p.id for p in personas}) != len(personas):
        raise ValueError("Duplicate persona identity")
    if any(p.software_behavior.status != "fixture" for p in personas):
        raise ValueError("Mock handoff accepts explicit fixture personas only")
    capability = Capability(
        id=fixture_id("b-mock-compose-cards"), key="compose_study_cards",
        description="Mock only: transform a fixed notes sample into two fixed cards",
        input_schema=SampleInput.model_json_schema(), output_schema=SampleOutput.model_json_schema(),
        validated=False, evidence=[EVIDENCE],
    )
    version = ProductVersion(
        id=fixture_id("b-mock-product-v1"), label="B mock of A handoff v1", status="fixture",
        runtime_url=runtime_url, capabilities=[capability],
        briefing="MOCK: choose Load sample, then Generate cards. No upload, login, or real adapter. "
                 "All source commits are unavailable. Only the fixed sample is supported.",
        limitations=["Synthetic A input", "No integrated repositories", "No review-informed population"],
    )
    state = MockState(id="b-mock-sample-v1", notes="Photosynthesis uses sunlight. Water freezes at 0 C.")
    check = MockCheck(id="b-mock-two-cards-v1", expected_cards=[
        Card(question="What does photosynthesis use?", answer="Sunlight"),
        Card(question="At what temperature does water freeze?", answer="0 C"),
    ])
    return MockHandoff(
        repositories=[r.model_copy(deep=True) for r in REPOSITORIES], version=version,
        initial_states=[state], checks=[check], tasks=[Task(
            id=fixture_id(f"b-mock-task-{p.id}"), scenario_id=p.scenario.id,
            capability_ids=[capability.id], goal=p.scenario.goal, initial_state_ref=state.id,
            check_id=check.id, task_version="b-mock-task-v1", action_budget=6,
        ) for p in personas],
    )


def mock_experiment(handoff: MockHandoff, population: list[Persona]) -> Experiment:
    return Experiment(
        id=fixture_id("b-mock-experiment-v1"), population_id=fixture_id("b-mock-population-v1"),
        product_version_id=handoff.version.id, status="fixture",
        counts=ExperimentCounts(configured=len(population), queued=0, running=0, completed=0, failed=0),
        inference_profile={"mode": "fixture", "model": None, "generation_version": "fixture-v1"},
    )


def select_task(handoff: MockHandoff, persona: Persona, task_id: UUID) -> Task:
    task = next((t for t in handoff.tasks if t.id == task_id), None)
    if task is None or task.scenario_id != persona.scenario.id:
        raise ValueError("Task does not belong to this persona scenario")
    return task
