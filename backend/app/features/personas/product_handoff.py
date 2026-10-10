"""Generic selected-prototype catalog binding; catalog access is not runtime proof."""
import hashlib
import json
from dataclasses import dataclass
from uuid import uuid5

from backend.app.features.integration import handoff as producer
from backend.app.features.personas.population import CoverageQuota
from backend.app.shared.contracts import Task


class HandoffError(Exception):
    """Fixed error codes only; untrusted manifests are never echoed."""


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ProductBinding:
    snapshot_json: str
    version: str

    def data(self):
        if hashlib.sha256(self.snapshot_json.encode()).hexdigest() != self.version:
            raise HandoffError("HANDOFF_BINDING_CHANGED")
        return json.loads(self.snapshot_json)

    def tasks(self):
        return [Task.model_validate(value) for value in self.data()["task_templates"]]

    def quotas(self):
        return [CoverageQuota.model_validate(value) for value in self.data()["coverage_quotas"]]

    def report(self):
        data = self.data()
        return {key: data[key] for key in (
            "product_version_id", "manifest_sha256", "catalog_status", "runtime_verified",
            "runtime_blockers", "excluded_checks", "configured_count", "completed_trials",
            "limitations",
        )}


def consume_product_handoff(*, candidate: producer.ProductHandoff, quotas: list[CoverageQuota]):
    if candidate.mode != "live" or candidate.version.status != "validated" or not candidate.checks:
        raise HandoffError("VALIDATED_PROTOTYPE_REQUIRED")
    capabilities = [c.id for c in candidate.version.capabilities if c.validated]
    if not capabilities:
        raise HandoffError("VALIDATED_CAPABILITIES_REQUIRED")
    tasks, excluded = [], []
    for check in candidate.checks:
        if check.initial_state not in candidate.initial_states:
            raise HandoffError("PROTOTYPE_INITIAL_STATE_MISSING")
        if check.action_budget > 6:
            excluded.append({"check_id": check.id, "reason": "EXCEEDS_MANDATORY_SIX_ACTION_LIMIT"})
            continue
        task_id = uuid5(candidate.version.id, "mandatory-task:" + check.id)
        tasks.append(Task(id=task_id, scenario_id=uuid5(task_id, "template-scenario"),
            capability_ids=capabilities, goal=check.goal, initial_state_ref=check.initial_state,
            check_id=check.id, task_version="prototype:" + str(candidate.version.id), action_budget=check.action_budget))
    if not tasks or not quotas or any(q.task_template_id not in {t.id for t in tasks} for q in quotas):
        raise HandoffError("PRODUCT_RELEVANT_COVERAGE_REQUIRED")
    data = {"product_version_id": str(candidate.version.id),
        "manifest_sha256": hashlib.sha256(_encode(candidate.model_dump(mode="json")).encode()).hexdigest(),
        "catalog_status": "explicit_manifest_bound", "runtime_verified": False,
        "runtime_blockers": ["SELECTED_RUNTIME_NOT_VERIFIED"], "product_manifest": candidate.model_dump(mode="json"),
        "task_templates": [t.model_dump(mode="json") for t in tasks],
        "coverage_quotas": [q.model_dump(mode="json") for q in quotas], "excluded_checks": excluded,
        "configured_count": sum(q.count for q in quotas), "completed_trials": 0,
        "limitations": ["Explicit catalog and audience coverage do not establish runtime availability or trials.", *candidate.limitations]}
    encoded = _encode(data)
    return ProductBinding(encoded, hashlib.sha256(encoded.encode()).hexdigest())
