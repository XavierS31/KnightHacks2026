import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.lifecycle import (
    ActorNotAllowed,
    PatchLifecycle,
    PatchOutsideScope,
    RegressionMismatch,
    TransitionNotAllowed,
)
from backend.app.features.evolution.models import Actor, BaseVersion, CheckResult, PatchFile
from backend.app.features.evolution.patch_boundary import PatchRejected, validate_allowed_paths
from backend.app.features.integration.product.handoff import MANIFEST
from backend.app.main import app
from backend.app.shared.contracts import Improvement
from backend.app.shared.fixtures import IMPROVEMENT

APP_JS = "frontend/src/features/integration/product/app.js"
PRIORITIZER = Actor(id="prioritizer-1", role="prioritizer")
HUMAN = Actor(id="human-1", role="human_reviewer")
IMPLEMENTER = Actor(id="implementer-1", role="implementer")
QA = Actor(id="qa-1", role="qa_reviewer")
BASE = BaseVersion(version_id=uuid4(), label="SourceTable v1",
                   fixed_check_ids=["normal-v1", "type-error-v1"], fixed_checks_sha256="a" * 64)
IMPROVEMENT_IN_SCOPE = Improvement(
    id=uuid4(), title="Clarify the input format", issue="Personas could not find supported input",
    supporting_session_ids=[uuid4()], severity=3, affected_share=0.5, evidence_strength=1,
    estimated_effort_hours=1, acceptance_check="A supported-input hint is visible",
    allowed_paths=[APP_JS], status="proposed")
PATCH = [PatchFile(path=APP_JS, content="const hint = 'Supported input: ruled PDF tables.';")]
PASSING = [CheckResult(check_id="normal-v1", passed=True, evidence="Verdict matched."),
           CheckResult(check_id="type-error-v1", passed=True, evidence="Errors mapped.")]


def test_full_order_registers_v2_and_keeps_v1():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    approved = lifecycle.approve(run.id, HUMAN)

    assert [event.state for event in approved.events] == [
        "proposed", "reviewed", "patched", "regression_passed", "approved"]
    assert approved.base == BASE
    assert approved.candidate.base_version_id == BASE.version_id
    assert approved.candidate.id != BASE.version_id
    assert approved.candidate.fixed_checks_sha256 == BASE.fixed_checks_sha256
    assert lifecycle.active_version_id(BASE.version_id) == approved.candidate.id


def test_steps_cannot_be_skipped():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.record_regression(run.id, QA, "0" * 64, PASSING)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(run.id, HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.review(run.id, HUMAN)
    assert lifecycle.get(run.id).state == "patched"
    assert lifecycle.get(run.id).patch == patched.patch


@pytest.mark.parametrize("path", [
    "frontend/src/features/integration/product/style.css",
    "frontend/src/features/integration/product/../../evolution/a.js", "../" + APP_JS, "/" + APP_JS,
    APP_JS.replace("/", "\\"), "frontend/src/features/integration/product/./app.js",
    "backend/app/main.py", APP_JS + "x", "backend/app/features/integration/product/checks.py",
])
def test_patch_outside_approved_paths_fails(path):
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(PatchOutsideScope):
        lifecycle.submit_patch(run.id, IMPLEMENTER, [*PATCH, PatchFile(path=path, content="x")])
    assert lifecycle.get(run.id).state == "reviewed"
    assert lifecycle.get(run.id).patch is None


def test_duplicate_patch_paths_fail():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(PatchOutsideScope):
        lifecycle.submit_patch(run.id, IMPLEMENTER, [*PATCH, *PATCH])


@pytest.mark.parametrize("promoter", [
    Actor(id="implementer-1", role="human_reviewer"), IMPLEMENTER, QA, PRIORITIZER])
def test_implementer_cannot_promote_its_own_patch(promoter):
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    with pytest.raises(ActorNotAllowed):
        lifecycle.approve(run.id, promoter)
    assert lifecycle.get(run.id).state == "regression_passed"
    assert lifecycle.get(run.id).candidate is None
    assert lifecycle.active_version_id(BASE.version_id) == BASE.version_id


def test_implementer_cannot_check_its_own_patch_or_review_its_scope():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, Actor(id="implementer-1", role="human_reviewer"))
    with pytest.raises(ActorNotAllowed):
        lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)

    other = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(other.id, HUMAN)
    patched = lifecycle.submit_patch(other.id, IMPLEMENTER, PATCH)
    with pytest.raises(ActorNotAllowed):
        lifecycle.record_regression(other.id, Actor(id="implementer-1", role="qa_reviewer"),
                                    patched.patch.sha256, PASSING)


def test_failed_regression_blocks_v2():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    failing = [PASSING[0], CheckResult(check_id="type-error-v1", passed=False, evidence="No errors.")]
    failed = lifecycle.record_regression(run.id, QA, patched.patch.sha256, failing)

    assert failed.state == "regression_failed"
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(run.id, HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    assert lifecycle.get(run.id).candidate is None
    assert lifecycle.active_version_id(BASE.version_id) == BASE.version_id


@pytest.mark.parametrize("results,digest", [
    (PASSING[:1], None),
    ([*PASSING, CheckResult(check_id="new-weaker-check", passed=True, evidence="Added.")], None),
    ([PASSING[0], PASSING[0]], None),
    (PASSING, "0" * 64),
])
def test_regression_must_cover_fixed_checks_for_the_submitted_patch(results, digest):
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    with pytest.raises(RegressionMismatch):
        lifecycle.record_regression(run.id, QA, digest or patched.patch.sha256, results)
    assert lifecycle.get(run.id).state == "patched"
    assert lifecycle.get(run.id).base.fixed_check_ids == ["normal-v1", "type-error-v1"]


def test_rejected_patch_cannot_be_approved():
    lifecycle = PatchLifecycle()
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    with pytest.raises(ActorNotAllowed):
        lifecycle.reject(run.id, QA)
    rejected = lifecycle.reject(run.id, HUMAN, "Hint wording is misleading.")

    assert rejected.state == "rejected"
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(run.id, HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.reject(run.id, HUMAN)
    assert lifecycle.active_version_id(BASE.version_id) == BASE.version_id


def test_rollback_restores_v1_and_allows_one_active_v2():
    lifecycle = PatchLifecycle()
    first = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    second = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    for run in (first, second):
        lifecycle.review(run.id, HUMAN)
        patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
        lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    approved = lifecycle.approve(first.id, HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(second.id, HUMAN)
    with pytest.raises(ActorNotAllowed):
        lifecycle.rollback(first.id, IMPLEMENTER)

    rolled_back = lifecycle.rollback(first.id, HUMAN)
    assert rolled_back.state == "rolled_back"
    assert rolled_back.candidate == approved.candidate
    assert rolled_back.base == BASE
    assert lifecycle.active_version_id(BASE.version_id) == BASE.version_id
    with pytest.raises(TransitionNotAllowed):
        lifecycle.rollback(first.id, HUMAN)
    assert lifecycle.approve(second.id, HUMAN).state == "approved"


def test_fixture_unsupported_or_out_of_scope_improvements_cannot_start():
    lifecycle = PatchLifecycle()
    with pytest.raises(TransitionNotAllowed):
        lifecycle.propose(IMPROVEMENT, BASE, PRIORITIZER)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.propose(IMPROVEMENT_IN_SCOPE.model_copy(update={"supporting_session_ids": []}),
                          BASE, PRIORITIZER)
    with pytest.raises(PatchOutsideScope):
        lifecycle.propose(IMPROVEMENT_IN_SCOPE.model_copy(update={"allowed_paths": ["backend"]}),
                          BASE, PRIORITIZER)
    with pytest.raises(ActorNotAllowed):
        lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, IMPLEMENTER)


def test_routes_enforce_lifecycle_against_frozen_v1():
    manifest_digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    client = TestClient(app)
    improvement = IMPROVEMENT_IN_SCOPE.model_dump(mode="json")
    human, implementer = HUMAN.model_dump(), IMPLEMENTER.model_dump()

    created = client.post(f"/api/v1/improvements/{IMPROVEMENT_IN_SCOPE.id}/patch-runs",
                          json={"actor": PRIORITIZER.model_dump(), "improvement": improvement})
    assert created.status_code == 201
    run = created.json()
    assert run["state"] == "proposed" and run["storage"] == "memory"
    assert run["base"]["label"] == "SourceTable v1"
    base_checks = run["base"]["fixed_check_ids"]
    assert base_checks

    early = client.post(f"/api/v1/patch-runs/{run['id']}/approve", json={"actor": human})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "TRANSITION_NOT_ALLOWED"
    assert client.post(f"/api/v1/patch-runs/{run['id']}/review",
                       json={"actor": human}).status_code == 200
    outside = client.post(f"/api/v1/patch-runs/{run['id']}/patch", json={
        "actor": implementer, "files": [{"path": "backend/app/main.py", "content": "x"}]})
    assert outside.status_code == 422
    assert outside.json()["error"]["code"] == "PATCH_OUTSIDE_SCOPE"
    patched = client.post(f"/api/v1/patch-runs/{run['id']}/patch", json={
        "actor": implementer, "files": [file.model_dump() for file in PATCH]}).json()
    checked = client.post(f"/api/v1/patch-runs/{run['id']}/regression", json={
        "actor": QA.model_dump(), "patch_sha256": patched["patch"]["sha256"],
        "results": [{"check_id": check, "passed": True, "evidence": "Observed."}
                    for check in base_checks]})
    assert checked.json()["state"] == "regression_passed"
    own = client.post(f"/api/v1/patch-runs/{run['id']}/approve",
                      json={"actor": {"id": IMPLEMENTER.id, "role": "human_reviewer"}})
    assert own.status_code == 403
    assert own.json()["error"]["code"] == "ACTOR_NOT_ALLOWED"
    approved = client.post(f"/api/v1/patch-runs/{run['id']}/approve", json={"actor": human})
    assert approved.json()["candidate"]["base_version_id"] == run["base"]["version_id"]
    rolled_back = client.post(f"/api/v1/patch-runs/{run['id']}/rollback", json={"actor": human})
    assert rolled_back.json()["state"] == "rolled_back"

    assert client.get(f"/api/v1/patch-runs/{run['id']}").json()["base"] == run["base"]
    assert client.get(f"/api/v1/patch-runs/{uuid4()}").status_code == 404
    mismatch = client.post(f"/api/v1/improvements/{uuid4()}/patch-runs",
                           json={"actor": PRIORITIZER.model_dump(), "improvement": improvement})
    assert mismatch.status_code == 422
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == manifest_digest


@pytest.mark.parametrize("path", ["../" + APP_JS, "frontend/src/features/integration/../app.js",
                                  "/" + APP_JS, "C:\\" + APP_JS, "backend/a.py", "product/src",
                                  "frontend/src/features/integration/product"])
def test_patch_boundaries_reject_escape(path):
    with pytest.raises(PatchRejected):
        validate_allowed_paths([path])


def test_product_descendant_path_is_allowed():
    validate_allowed_paths([APP_JS, "backend/app/features/integration/product/runtime/adapter.py"])
