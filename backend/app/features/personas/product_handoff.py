"""B's exact SourceTable catalog binding; catalog access is not runtime proof."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid5

from backend.app.features.integration.product import handoff as producer
from backend.app.features.integration.product.executor import ExecutionError
from backend.app.features.personas.population import CoverageQuota
from backend.app.shared.contracts import Task


class HandoffError(Exception):
    """Fixed error codes only; untrusted manifests are never echoed."""


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class SourceTableBinding:
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


def consume_sourcetable_handoff(*, artifact_root: Path | None = None,
                              candidate: producer.ProductHandoff | None = None):
    """Bind only A's frozen catalog; use A's verifier unchanged for runtime proof.

    A caller-supplied or remotely fetched handoff must equal the trusted tracked
    manifest, including checks, initial state, source pins and image/fingerprints.
    This does not fetch or execute its runtime URL. Missing local image/hash proof
    leaves the catalog usable for generation but prevents live scheduling.
    """
    try:
        raw = producer.MANIFEST.read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError("Oversized manifest")
        frozen = producer.ProductHandoff.model_validate_json(raw)
        if (frozen.mode != "live" or frozen.version.status != "validated"
                or frozen.version.label != "SourceTable v1"
                or frozen.version.runtime_url != "http://127.0.0.1:8001"
                or not frozen.implementation_hashes or not frozen.source_commits
                or len(frozen.version.capabilities) != 1
                or frozen.version.capabilities[0].key != "extract_validate_table"
                or not frozen.version.capabilities[0].validated):
            raise ValueError("Unsupported catalog")
        if candidate is not None and candidate != frozen:
            raise ValueError("Candidate differs from trusted manifest")
    except (OSError, ValueError, TypeError):
        raise HandoffError("SOURCETABLE_MANIFEST_NOT_COMPATIBLE") from None

    runtime_verified = False
    runtime_blockers = ["LOCAL_RUNTIME_NOT_VERIFIED"]
    if artifact_root is not None:
        try:
            verified = producer.verified_handoff(artifact_root)
            if verified != frozen:
                raise ExecutionError("VERSION_NOT_VALIDATED")
            runtime_verified = True
            runtime_blockers = []
        except ExecutionError:
            runtime_blockers = ["VERSION_NOT_VALIDATED"]

    capabilities = [frozen.version.capabilities[0].id]
    tasks, excluded = [], []
    for check in frozen.checks:
        if check.initial_state not in frozen.initial_states:
            raise HandoffError("SOURCETABLE_INITIAL_STATE_MISSING")
        if check.action_budget > 6:
            excluded.append({"check_id": check.id, "required_action_budget": check.action_budget,
                             "reason": "EXCEEDS_MANDATORY_SIX_ACTION_LIMIT"})
            continue
        task_id = uuid5(frozen.version.id, "mandatory-task:" + check.id)
        tasks.append(Task(id=task_id, scenario_id=uuid5(task_id, "template-scenario"),
                          capability_ids=capabilities, goal=check.goal,
                          initial_state_ref=check.initial_state, check_id=check.id,
                          task_version="sourcetable-v1:" + str(frozen.version.id),
                          action_budget=check.action_budget))
    if len(tasks) != 1 or tasks[0].check_id != "sourcetable-normal-v1":
        raise HandoffError("SOURCETABLE_MANDATORY_CATALOG_NOT_SUPPORTED")

    coverage = [
        ("undergraduate", "Student checking a practice inventory", "library", "laptop"),
        ("graduate", "Research trainee inspecting tabular source values", "home", "laptop"),
        ("faculty", "Instructor reviewing an inventory exercise", "classroom", "laptop"),
        ("staff", "Office coordinator inspecting a sample inventory", "office", "laptop"),
        ("resident", "Resident testing a sample table workflow", "home", "phone"),
    ]
    quotas = [CoverageQuota(cohort=cohort, count=100, active_role=role,
                           location_id=location, device=device, task_template_id=tasks[0].id,
                           assumption="Balanced fictional scenario coverage: cohort, role, "
                           "location and device are assumptions, not review-author demographics "
                           "or measured frequencies.")
              for cohort, role, location, device in coverage]
    data = {
        "product_version_id": str(frozen.version.id),
        "manifest_sha256": hashlib.sha256(_encode(frozen.model_dump(mode="json")).encode()).hexdigest(),
        "catalog_status": "frozen_manifest_bound",
        "runtime_verified": runtime_verified,
        "runtime_blockers": runtime_blockers,
        "product_manifest": frozen.model_dump(mode="json"),
        "task_templates": [task.model_dump(mode="json") for task in tasks],
        "coverage_quotas": [quota.model_dump(mode="json") for quota in quotas],
        "excluded_checks": excluded,
        "configured_count": 500,
        "completed_trials": 0,
        "limitations": ["Catalog binding is not process availability or persona execution.",
                        "All personas use the same supported fixed-sample normal check.",
                        "A's type-error/recovery templates require seven/nine actions; "
                        "revised independently validated checks are needed for mandatory use.",
                        "Five equal cohorts are intentional coverage, not representativeness.",
                        *frozen.limitations],
    }
    encoded = _encode(data)
    return SourceTableBinding(encoded, hashlib.sha256(encoded.encode()).hexdigest())
