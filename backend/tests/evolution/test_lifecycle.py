import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.lifecycle import (
    ActorNotAllowed,
    EditConflict,
    PatchLifecycle,
    PatchOutsideScope,
    RegressionMismatch,
    TransitionNotAllowed,
    validate_patch_paths,
)
from backend.app.features.evolution.models import (
    Actor,
    BaseVersion,
    BoundedEdit,
    CheckResult,
    PatchFile,
)
from backend.app.main import app
from backend.app.shared.contracts import Improvement
from backend.app.shared.fixtures import IMPROVEMENT
from backend.app.shared.settings import Settings, get_settings
from backend.tests.prototype_fixtures import BOUNDED_IMPROVEMENTS, SOURCES, STALE_STATUS

PRIORITIZER = Actor(id="prioritizer-1", role="prioritizer")
HUMAN = Actor(id="human-1", role="human_reviewer")
IMPLEMENTER = Actor(id="implementer-1", role="implementer")
QA = Actor(id="qa-1", role="qa_reviewer")
BASE = BaseVersion(version_id=uuid4(), label="Synthetic prototype v1",
                   fixed_check_ids=["normal-v1", "type-error-v1"], fixed_checks_sha256="a" * 64)
IMPROVEMENT_IN_SCOPE = Improvement(
    id=uuid4(), title="Clarify the input format", issue="Personas could not find supported input",
    supporting_session_ids=[uuid4()], severity=3, affected_share=0.5, evidence_strength=1,
    estimated_effort_hours=1, acceptance_check="A supported-input hint is visible",
    allowed_paths=["product/src"], status="proposed")
PATCH = [PatchFile(path="product/src/hint.txt", content="Supported input: ruled PDF tables.")]
EDITS = [BoundedEdit(path="product/src/hint.txt", find="Supported", replace="Accepted")]
PATCHABLE = frozenset({"product/src/hint.txt", "product/other/app.js"})
PASSING = [CheckResult(check_id="normal-v1", passed=True, evidence="Verdict matched."),
           CheckResult(check_id="type-error-v1", passed=True, evidence="Errors mapped.")]


def test_full_order_registers_v2_and_keeps_v1():
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
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
    "product/other/app.js", "product/src/../../backend/app.py", "../product/src/a.py",
    "/product/src/a.py", "product\\src\\a.py", "product/./src/a.py", "backend/app/main.py",
    "product/srcx/a.py",
])
def test_patch_outside_approved_paths_fails(path):
    lifecycle = PatchLifecycle(PATCHABLE)
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(PatchOutsideScope):
        lifecycle.submit_patch(run.id, IMPLEMENTER, [*PATCH, PatchFile(path=path, content="x")])
    assert lifecycle.get(run.id).state == "reviewed"
    assert lifecycle.get(run.id).patch is None


def test_duplicate_patch_paths_fail():
    lifecycle = PatchLifecycle(PATCHABLE)
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(PatchOutsideScope):
        lifecycle.submit_patch(run.id, IMPLEMENTER, [*PATCH, *PATCH])


@pytest.mark.parametrize("promoter", [
    Actor(id="implementer-1", role="human_reviewer"), IMPLEMENTER, QA, PRIORITIZER])
def test_implementer_cannot_promote_its_own_patch(promoter):
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    with pytest.raises(RegressionMismatch):
        lifecycle.record_regression(run.id, QA, digest or patched.patch.sha256, results)
    assert lifecycle.get(run.id).state == "patched"
    assert lifecycle.get(run.id).base.fixed_check_ids == ["normal-v1", "type-error-v1"]


def test_rejected_patch_cannot_be_approved():
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
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
    lifecycle = PatchLifecycle(PATCHABLE)
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


def test_routes_enforce_lifecycle_against_frozen_v1(tmp_path):
    manifest_digest = hashlib.sha256(str(SOURCES).encode()).hexdigest()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, artifact_root=tmp_path)
    client = TestClient(app)
    improvement = IMPROVEMENT_IN_SCOPE.model_copy(update={
        "allowed_paths": STALE_STATUS.allowed_paths}).model_dump(mode="json")
    human, implementer = HUMAN.model_dump(), IMPLEMENTER.model_dump()
    try:
        created = client.post(f"/api/v1/improvements/{IMPROVEMENT_IN_SCOPE.id}/patch-runs",
                              json={"actor": PRIORITIZER.model_dump(), "improvement": improvement})
        assert created.status_code == 201
        run = created.json()
        assert run["state"] == "proposed" and run["storage"] == "memory"
        assert run["base"]["label"] == "Synthetic prototype v1"
        assert run["title"] == IMPROVEMENT_IN_SCOPE.title
        assert run["base"]["fixed_check_ids"]

        early = client.post(f"/api/v1/patch-runs/{run['id']}/approve", json={"actor": human})
        assert early.status_code == 409
        assert early.json()["error"]["code"] == "TRANSITION_NOT_ALLOWED"
        assert client.post(f"/api/v1/patch-runs/{run['id']}/review",
                           json={"actor": human}).status_code == 200
        outside = client.post(f"/api/v1/patch-runs/{run['id']}/patch", json={
            "actor": implementer, "files": [{"path": "backend/app/main.py", "content": "x"}]})
        assert outside.status_code == 422
        assert outside.json()["error"]["code"] == "PATCH_OUTSIDE_SCOPE"
        new_file = client.post(f"/api/v1/patch-runs/{run['id']}/patch", json={
            "actor": implementer, "files": [{"path": "product/ui/hint.txt", "content": "x"}]})
        assert new_file.status_code == 422
        conflict = client.post(f"/api/v1/patch-runs/{run['id']}/edits", json={
            "actor": implementer, "edits": [{"path": "product/ui/app.js", "find": "absent text",
                                             "replace": "x"}]})
        assert conflict.status_code == 422
        assert conflict.json()["error"]["code"] == "EDIT_CONFLICT"
        patched = client.post(f"/api/v1/patch-runs/{run['id']}/edits", json={
            "actor": implementer,
            "edits": [edit.model_dump() for edit in STALE_STATUS.edits]}).json()
        assert patched["state"] == "patched"
        assert patched["patch"]["edits"] == [edit.model_dump() for edit in STALE_STATUS.edits]
        assert [file["path"] for file in patched["patch"]["files"]] == ["product/ui/app.js"]

        assert client.post(f"/api/v1/patch-runs/{run['id']}/regression", json={
            "actor": QA.model_dump(), "patch_sha256": patched["patch"]["sha256"],
            "results": []}).status_code in {404, 405}
        own_check = client.post(f"/api/v1/patch-runs/{run['id']}/qa", json={
            "actor": {"id": IMPLEMENTER.id, "role": "qa_reviewer"}})
        assert own_check.status_code == 503
        unavailable = client.post(f"/api/v1/patch-runs/{run['id']}/qa",
                                  json={"actor": QA.model_dump()})
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "QA_UNAVAILABLE"
        stored = client.get(f"/api/v1/patch-runs/{run['id']}").json()
        assert stored["state"] == "patched" and stored["regression"] == []
        assert client.post(f"/api/v1/patch-runs/{run['id']}/approve",
                           json={"actor": human}).status_code == 409

        assert client.get(f"/api/v1/patch-runs/{run['id']}").json()["base"] == run["base"]
        assert client.get(f"/api/v1/patch-runs/{uuid4()}").status_code == 404
        mismatch = client.post(f"/api/v1/improvements/{uuid4()}/patch-runs",
                               json={"actor": PRIORITIZER.model_dump(), "improvement": improvement})
        assert mismatch.status_code == 422
    finally:
        app.dependency_overrides.clear()
    assert hashlib.sha256(str(SOURCES).encode()).hexdigest() == manifest_digest


@pytest.mark.parametrize("path", ["../product/a.py", "product/../backend/app.py", "/product/a.py",
                                  "C:\\product\\a.py", "backend/a.py", "product"])
def test_patch_boundaries_reject_escape(path):
    with pytest.raises(ValueError):
        validate_patch_paths([path])


def test_product_descendant_path_is_allowed():
    validate_patch_paths(["product/src/app.py"])


def test_unlisted_product_file_cannot_be_patched():
    lifecycle = PatchLifecycle(frozenset({"product/src/app.js"}))
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(PatchOutsideScope):
        lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH)
    assert lifecycle.get(run.id).state == "reviewed"


def test_pre_checks_reject_wrong_actor_or_state_before_expensive_work():
    lifecycle = PatchLifecycle(PATCHABLE)
    run = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.ready_for_patch(run.id, IMPLEMENTER)
    lifecycle.review(run.id, HUMAN)
    with pytest.raises(ActorNotAllowed):
        lifecycle.ready_for_patch(run.id, Actor(id=HUMAN.id, role="implementer"))
    assert lifecycle.ready_for_patch(run.id, IMPLEMENTER).state == "reviewed"
    with pytest.raises(TransitionNotAllowed):
        lifecycle.ready_for_regression(run.id, QA)
    lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH, EDITS)
    with pytest.raises(ActorNotAllowed):
        lifecycle.ready_for_regression(run.id, Actor(id=IMPLEMENTER.id, role="qa_reviewer"))
    assert lifecycle.ready_for_regression(run.id, QA).patch.edits == EDITS


def test_release_composes_passed_runs_and_needs_its_own_checks_and_approval():
    lifecycle = PatchLifecycle(PATCHABLE)
    components = []
    for index in range(2):
        improvement = IMPROVEMENT_IN_SCOPE.model_copy(update={"id": uuid4(), "title": f"Fix {index}"})
        run = lifecycle.propose(improvement, BASE, PRIORITIZER)
        lifecycle.review(run.id, HUMAN)
        edits = [BoundedEdit(path="product/src/hint.txt", find=f"old {index}", replace=f"new {index}")]
        patched = lifecycle.submit_patch(run.id, Actor(id=f"implementer-{index}", role="implementer"),
                                         PATCH, edits)
        lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
        components.append(run.id)

    with pytest.raises(ActorNotAllowed):
        lifecycle.propose_release(components, PRIORITIZER)
    release = lifecycle.propose_release(components, HUMAN)
    assert release.state == "reviewed" and release.component_run_ids == components
    assert release.base == BASE and release.title == "v2 release: Fix 0 + Fix 1"
    assert [event.state for event in release.events] == ["proposed", "reviewed"]
    expected = lifecycle.release_edits(release.id)
    assert [edit.find for edit in expected] == ["old 0", "old 1"]

    composer = Actor(id="implementer-release", role="implementer")
    with pytest.raises(EditConflict):
        lifecycle.submit_patch(release.id, composer, PATCH, expected[:1])
    with pytest.raises(EditConflict):
        lifecycle.submit_patch(release.id, composer, PATCH, list(reversed(expected)))
    patched = lifecycle.submit_patch(release.id, composer, PATCH, expected)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(release.id, HUMAN)
    lifecycle.record_regression(release.id, QA, patched.patch.sha256, PASSING)
    with pytest.raises(ActorNotAllowed):
        lifecycle.approve(release.id, Actor(id="implementer-0", role="human_reviewer"))
    approved = lifecycle.approve(release.id, HUMAN)
    assert approved.candidate.base_version_id == BASE.version_id
    assert lifecycle.active_version_id(BASE.version_id) == approved.candidate.id
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(components[0], HUMAN)
    lifecycle.rollback(release.id, HUMAN)
    assert lifecycle.active_version_id(BASE.version_id) == BASE.version_id


def test_release_rejects_unready_mixed_or_repeated_components():
    lifecycle = PatchLifecycle(PATCHABLE)
    ids = {}
    for name, edits in [("passed", EDITS), ("other", EDITS), ("files_only", None), ("open", EDITS)]:
        run = lifecycle.propose(IMPROVEMENT_IN_SCOPE.model_copy(update={"id": uuid4()}), BASE,
                                PRIORITIZER)
        lifecycle.review(run.id, HUMAN)
        patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH, edits)
        if name != "open":
            lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
        ids[name] = run.id
    same_improvement = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    twin = lifecycle.propose(IMPROVEMENT_IN_SCOPE, BASE, PRIORITIZER)
    for run in (same_improvement, twin):
        lifecycle.review(run.id, HUMAN)
        patched = lifecycle.submit_patch(run.id, IMPLEMENTER, PATCH, EDITS)
        lifecycle.record_regression(run.id, QA, patched.patch.sha256, PASSING)
    other_base = lifecycle.propose(
        IMPROVEMENT_IN_SCOPE.model_copy(update={"id": uuid4()}),
        BASE.model_copy(update={"version_id": uuid4()}), PRIORITIZER)
    lifecycle.review(other_base.id, HUMAN)
    patched = lifecycle.submit_patch(other_base.id, IMPLEMENTER, PATCH, EDITS)
    lifecycle.record_regression(other_base.id, QA, patched.patch.sha256, PASSING)

    for run_ids in ([ids["passed"]], [ids["passed"], ids["passed"]],
                    [ids["passed"], ids["open"]], [ids["passed"], ids["files_only"]],
                    [same_improvement.id, twin.id], [ids["passed"], other_base.id],
                    [ids["passed"], ids["other"], ids["files_only"], other_base.id]):
        with pytest.raises(TransitionNotAllowed):
            lifecycle.propose_release(run_ids, HUMAN)
    release = lifecycle.propose_release([ids["passed"], ids["other"]], HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.propose_release([release.id, ids["files_only"]], HUMAN)
    with pytest.raises(TransitionNotAllowed):
        lifecycle.release_edits(ids["passed"])

    patched = lifecycle.submit_patch(release.id, Actor(id="composer", role="implementer"), PATCH,
                                     lifecycle.release_edits(release.id))
    lifecycle.record_regression(release.id, QA, patched.patch.sha256, PASSING)
    lifecycle.reject(ids["other"], HUMAN, "Component withdrawn.")
    with pytest.raises(TransitionNotAllowed):
        lifecycle.approve(release.id, HUMAN)


def test_bounded_improvements_stay_in_one_boundary_file():
    assert len(BOUNDED_IMPROVEMENTS) == 3
    for improvement in BOUNDED_IMPROVEMENTS:
        assert improvement.allowed_paths == ["product/ui/app.js"]
        assert {edit.path for edit in improvement.edits} == {"product/ui/app.js"}
