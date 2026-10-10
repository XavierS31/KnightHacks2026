"""Catalog planning is offline; fake verifier success never establishes real runtime proof."""
from dataclasses import replace
from uuid import uuid4

import pytest

from backend.app.features.integration.product import handoff as producer
from backend.app.features.integration.product.executor import ExecutionError
from backend.app.features.personas.product_handoff import HandoffError, consume_sourcetable_handoff


def manifest():
    return producer.ProductHandoff.model_validate_json(producer.MANIFEST.read_bytes())


def test_exact_catalog_binding_preserves_mandatory_budget_and_provenance():
    binding = consume_sourcetable_handoff()
    assert consume_sourcetable_handoff().version == binding.version
    assert binding.report()["runtime_verified"] is False
    assert binding.report()["completed_trials"] == 0
    task, = binding.tasks()
    assert task.check_id == "sourcetable-normal-v1"
    assert task.action_budget == 6
    assert task.initial_state_ref == "sample-inventory-v1"
    assert task.capability_ids == [manifest().version.capabilities[0].id]
    assert {q.cohort for q in binding.quotas()} == {
        "undergraduate", "graduate", "faculty", "staff", "resident"}
    assert sum(q.count for q in binding.quotas()) == 500
    assert {q.task_template_id for q in binding.quotas()} == {task.id}
    excluded = binding.report()["excluded_checks"]
    assert [check["required_action_budget"] for check in excluded] == [7, 9]
    assert all("assumptions" in q.assumption for q in binding.quotas())


@pytest.mark.parametrize("field", ["identity", "hash", "image", "check", "initial", "source"])
def test_remote_candidate_cannot_replace_any_frozen_identity(field):
    candidate = manifest()
    if field == "identity":
        candidate.version.id = uuid4()
    elif field == "hash":
        candidate.implementation_hashes[next(iter(candidate.implementation_hashes))] = "0" * 64
    elif field == "image":
        candidate.image_id = "sha256:" + "0" * 64
    elif field == "check":
        candidate.checks[0].expected["source_text"] = "invented"
    elif field == "initial":
        candidate.initial_states["sample-inventory-v1"]["pdf_base64"] = "changed"
    else:
        candidate.source_commits[next(iter(candidate.source_commits))] = "0" * 40
    with pytest.raises(HandoffError, match="SOURCETABLE_MANIFEST_NOT_COMPATIBLE"):
        consume_sourcetable_handoff(candidate=candidate)


def test_unchanged_remote_catalog_is_planning_only():
    binding = consume_sourcetable_handoff(candidate=manifest())
    assert binding.report()["runtime_blockers"] == ["LOCAL_RUNTIME_NOT_VERIFIED"]


def test_failed_local_verification_preserves_planning_and_records_blocker(monkeypatch, tmp_path):
    def fail(_):
        raise ExecutionError("VERSION_NOT_VALIDATED")
    monkeypatch.setattr(producer, "verified_handoff", fail)
    binding = consume_sourcetable_handoff(artifact_root=tmp_path)
    assert binding.report()["runtime_blockers"] == ["VERSION_NOT_VALIDATED"]
    assert binding.tasks()[0].action_budget == 6


def test_verification_calls_a_without_bypassing_its_checks(monkeypatch, tmp_path):
    calls = []
    def verified(path):
        calls.append(path)
        return manifest()
    monkeypatch.setattr(producer, "verified_handoff", verified)
    binding = consume_sourcetable_handoff(artifact_root=tmp_path)
    assert calls == [tmp_path]
    assert binding.report()["runtime_verified"] is True
    assert binding.report()["runtime_blockers"] == []


def test_mismatched_verifier_cannot_validate_catalog(monkeypatch, tmp_path):
    changed = manifest()
    changed.version.id = uuid4()
    monkeypatch.setattr(producer, "verified_handoff", lambda _: changed)
    assert consume_sourcetable_handoff(artifact_root=tmp_path).report()["runtime_verified"] is False


def test_binding_returns_copies_and_rejects_changed_snapshot():
    binding = consume_sourcetable_handoff()
    binding.tasks()[0].goal = "changed"
    assert binding.tasks()[0].goal != "changed"
    with pytest.raises(HandoffError, match="HANDOFF_BINDING_CHANGED"):
        replace(binding, snapshot_json=binding.snapshot_json + " ").data()
