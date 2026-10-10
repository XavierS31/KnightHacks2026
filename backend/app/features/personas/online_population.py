"""Read a frozen live population through C's repository and bind it to A's catalog.

This module does not schedule trials. A validated runtime and durable job/session
records are separate gates before any configured persona becomes an executed one.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from backend.app.features.integration.product.handoff import ProductHandoff
from backend.app.features.personas.population import FrozenPopulation
from backend.app.features.personas.product_handoff import (
    SourceTableBinding,
    consume_sourcetable_handoff,
)
from backend.app.features.personas.session_execution import TrialPlan
from backend.app.shared.contracts import Persona, Task
from backend.app.shared.database import NeonDatabase
from backend.app.shared.settings import Settings


class OnlinePopulationError(ValueError):
    """Safe readiness failure without source text or connection details."""


@dataclass(frozen=True)
class BoundPopulation:
    population: FrozenPopulation
    binding: SourceTableBinding

    def persona_task(self, index: int) -> tuple[Persona, Task]:
        data = self.population.data()
        if not 0 <= index < data["configured_count"]:
            raise OnlinePopulationError("PERSONA_INDEX_OUT_OF_RANGE")
        return (Persona.model_validate(data["personas"][index]),
                Task.model_validate(data["tasks"][index]))

    def trial_plan(self, index: int, experiment_id: UUID, *, artifact_root: Path) -> TrialPlan:
        """Only a locally verified A runtime can become a live browser plan."""
        verified = consume_sourcetable_handoff(artifact_root=artifact_root)
        if (not verified.report()["runtime_verified"]
                or verified.data()["manifest_sha256"] != self.binding.data()["manifest_sha256"]
                or verified.tasks() != self.binding.tasks()):
            raise OnlinePopulationError("SOURCETABLE_RUNTIME_NOT_VERIFIED")
        persona, task = self.persona_task(index)
        handoff = ProductHandoff.model_validate(verified.data()["product_manifest"])
        return TrialPlan(
            mode="live", product=handoff.version,
            persona=persona, task=task,
            experiment_id=experiment_id,
        )


def bind_population(population: FrozenPopulation, *, binding: SourceTableBinding | None = None,
                    expected_version: str) -> BoundPopulation:
    """Check exact immutable population and task identities before inference or scheduling."""
    if not isinstance(population, FrozenPopulation):
        raise OnlinePopulationError("FROZEN_POPULATION_REQUIRED")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_version):
        raise OnlinePopulationError("INVALID_POPULATION_VERSION")
    if population.version != expected_version:
        raise OnlinePopulationError("POPULATION_VERSION_MISMATCH")
    data = population.data()
    selected = binding or consume_sourcetable_handoff()
    handoff = ProductHandoff.model_validate(selected.data()["product_manifest"])
    if (data["status"] != "configured_population" or data["purpose"] != "complete"
            or data["configured_count"] != 500 or data["completed_trials"] != 0
            or [Task.model_validate(item) for item in data["task_catalog"]] != selected.tasks()
            or any(Task.model_validate(item).task_version !=
                   "sourcetable-v1:" + str(handoff.version.id) for item in data["tasks"])):
        raise OnlinePopulationError("POPULATION_HANDOFF_MISMATCH")
    return BoundPopulation(population, selected)


def load_neon_population(settings: Settings, version: str) -> BoundPopulation:
    """Normal application path. C owns the connection and immutable repository."""
    if settings.app_mode != "live" or not settings.database_url.get_secret_value():
        raise OnlinePopulationError("LIVE_NEON_CONFIGURATION_REQUIRED")
    if not re.fullmatch(r"[a-f0-9]{64}", version):
        raise OnlinePopulationError("INVALID_POPULATION_VERSION")
    from backend.app.features.evolution.population_repository import PopulationRepository

    database = NeonDatabase(settings)
    try:
        population = PopulationRepository(database).load_population(version)
        return bind_population(population, expected_version=version)
    finally:
        database.close()
