from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.evolution.lifecycle import PatchLifecycle
from backend.app.features.evolution.models import (
    TIME_BASIS,
    Actor,
    BaseVersion,
    CheckResult,
    ExperimentRun,
    PatchFile,
    TrialAttempt,
    TrialIdentity,
)
from backend.app.features.evolution.retest import (
    RetestMismatch,
    RetestNotAllowed,
    build_retest_request,
    compare_versions,
    trial_identity,
)
from backend.app.features.evolution.router import lifecycle
from backend.app.main import app
from backend.app.shared.contracts import (
    Action,
    Experiment,
    ExperimentCounts,
    Feedback,
    Improvement,
    Session,
    Task,
)
from backend.app.shared.fixtures import PERSONAS
from backend.app.shared.settings import Settings, get_settings
from backend.tests.prototype_fixtures import STALE_STATUS

HUMAN = Actor(id="human-1", role="human_reviewer")
QA = Actor(id="qa-1", role="qa_reviewer")
IMPLEMENTER = Actor(id="implementer-1", role="implementer")
BASE = BaseVersion(version_id=uuid4(), label="Synthetic prototype v1",
                   fixed_check_ids=["normal-v1"], fixed_checks_sha256="a" * 64)
IMPROVEMENT = Improvement(
    id=uuid4(), title="Clarify the input format", issue="Personas could not find supported input",
    supporting_session_ids=[uuid4()], severity=3, affected_share=0.5, evidence_strength=1,
    estimated_effort_hours=1, acceptance_check="A supported-input hint is visible",
    allowed_paths=["product/src"], status="proposed")
LIFECYCLE = PatchLifecycle(frozenset({"product/src/a.txt"}))
OPEN_RUN = LIFECYCLE.propose(IMPROVEMENT, BASE, HUMAN)
LIFECYCLE.review(OPEN_RUN.id, HUMAN)
PATCHED = LIFECYCLE.submit_patch(OPEN_RUN.id, IMPLEMENTER, [PatchFile(path="product/src/a.txt", content="x")])
LIFECYCLE.record_regression(OPEN_RUN.id, QA, PATCHED.patch.sha256,
                            [CheckResult(check_id="normal-v1", passed=True, evidence="Matched.")])
APPROVED = LIFECYCLE.approve(OPEN_RUN.id, HUMAN)
UNAPPROVED = LIFECYCLE.propose(IMPROVEMENT, BASE, HUMAN)

T0 = datetime(2026, 10, 10, tzinfo=UTC)
POPULATION_ID = uuid4()
PROFILE = {"model": "test/model", "provider": "hf-inference", "prompt_version": "trial-v1"}
IDENTITIES = [TrialIdentity(
    persona_id=uuid5(NAMESPACE_URL, f"retest:persona:{i}"), population_version="population-v1",
    behavior_generation_version="behavior-v1", corpus_version="corpus-v1",
    scenario_id=uuid5(NAMESPACE_URL, f"retest:scenario:{i}"), task_id=uuid5(NAMESPACE_URL, "retest:task"),
    task_version="task-v1", check_id="normal-v1", initial_state_ref="state:blank",
    action_budget=6, time_budget_minutes=2) for i in range(500)]
EXPERIMENTS = {version: Experiment(
    id=uuid4(), population_id=POPULATION_ID, product_version_id=product_version_id,
    status="completed", inference_profile=PROFILE,
    counts=ExperimentCounts(configured=500, queued=0, running=0, completed=500, failed=0),
) for version, product_version_id in (("v1", BASE.version_id), ("v2", APPROVED.candidate.id))}
# v1: even personas succeed. v2: every persona succeeds except i % 4 == 3.
OUTCOMES = {
    "v1": ["success" if i % 2 == 0 else "application_failure" for i in range(500)],
    "v2": ["success" if i % 4 != 3 else "application_failure" for i in range(500)],
}
ATTEMPTS = {version: [TrialAttempt(identity=identity, phase="mandatory", session=Session(
    id=uuid5(NAMESPACE_URL, f"retest:{version}:session:{i}"),
    experiment_id=EXPERIMENTS[version].id, persona_id=identity.persona_id,
    product_version_id=EXPERIMENTS[version].product_version_id, status="completed",
    outcome=OUTCOMES[version][i], stop_reason=OUTCOMES[version][i], stream_mode="live",
    actions=[
        Action(id=uuid5(NAMESPACE_URL, f"retest:{version}:action:{i}:1"),
               session_id=uuid5(NAMESPACE_URL, f"retest:{version}:session:{i}"), sequence=1,
               timestamp=T0, kind="navigate", result="product_page_loaded"),
        Action(id=uuid5(NAMESPACE_URL, f"retest:{version}:action:{i}:2"),
               session_id=uuid5(NAMESPACE_URL, f"retest:{version}:session:{i}"), sequence=2,
               timestamp=T0 + timedelta(seconds=30 if version == "v1" else 20), kind="check",
               result=f"deterministic_{OUTCOMES[version][i]}"),
    ],
    feedback=Feedback(
        id=uuid5(NAMESPACE_URL, f"retest:{version}:feedback:{i}"), persona_id=identity.persona_id,
        session_id=uuid5(NAMESPACE_URL, f"retest:{version}:session:{i}"),
        initial_relevance="medium",
        post_trial_relevance="high" if OUTCOMES[version][i] == "success" else "low",
        decision="stop", useful_parts=[], barriers=[], suggested_changes=[],
        evidence_action_ids=[uuid5(NAMESPACE_URL, f"retest:{version}:action:{i}:2")],
        reason="Synthetic test feedback."),
)) for i, identity in enumerate(IDENTITIES)] for version in ("v1", "v2")}
V1 = ExperimentRun(experiment=EXPERIMENTS["v1"], attempts=ATTEMPTS["v1"])
V2 = ExperimentRun(experiment=EXPERIMENTS["v2"], attempts=ATTEMPTS["v2"])
REQUEST = build_retest_request(APPROVED, V1)


def test_request_freezes_every_v1_identity_for_the_approved_v2():
    assert REQUEST.base_version_id == BASE.version_id
    assert REQUEST.candidate_version_id == APPROVED.candidate.id
    assert REQUEST.fixed_check_ids == BASE.fixed_check_ids
    assert REQUEST.fixed_checks_sha256 == BASE.fixed_checks_sha256
    assert sorted(REQUEST.identities, key=lambda item: str(item.persona_id)) == REQUEST.identities
    assert {identity.persona_id for identity in REQUEST.identities} == {
        identity.persona_id for identity in IDENTITIES}
    assert REQUEST.identity_shortfall == 0
    assert REQUEST.inference_profile == PROFILE
    assert build_retest_request(APPROVED, V1) == REQUEST


def test_matched_500_comparison_uses_honest_denominators():
    report = compare_versions(REQUEST, V1, V2)

    assert report.matched_complete
    assert (report.matched_pairs, report.completed_pairs, report.missing_v2) == (500, 500, 0)
    assert report.v1.outcomes.success == 250 and report.v1.outcomes.application_failure == 250
    assert report.v2.outcomes.success == 375 and report.v2.outcomes.application_failure == 125
    assert sum(report.v2.outcomes.model_dump().values()) == 500
    assert report.v1.success_over_target.model_dump() == {"numerator": 250, "denominator": 500, "value": 0.5}
    assert report.success_over_completed_pairs["v2"].model_dump() == {
        "numerator": 375, "denominator": 500, "value": 0.75}
    assert [(t.v1_outcome, t.v2_outcome, t.count) for t in report.transitions] == [
        ("application_failure", "application_failure", 125),
        ("application_failure", "success", 125),
        ("success", "success", 250)]
    assert report.v2.feedback.present == 500
    assert report.v2.feedback.post_trial_relevance == {"low": 125, "medium": 0, "high": 375}
    assert not report.inference_configuration_changed
    assert report.continuation.v1_eligible == report.continuation.v2_attempted == 0


def test_missing_and_mismatched_v2_results_stay_visible():
    changed = ATTEMPTS["v2"][1].model_copy(update={
        "identity": ATTEMPTS["v2"][1].identity.model_copy(update={
            "task_version": "task-v2", "action_budget": 8})})
    stranger = ATTEMPTS["v2"][2].model_copy(update={
        "identity": ATTEMPTS["v2"][2].identity.model_copy(update={"persona_id": uuid4()})})
    stranger = stranger.model_copy(update={"session": stranger.session.model_copy(update={
        "persona_id": stranger.identity.persona_id,
        "feedback": stranger.session.feedback.model_copy(update={
            "persona_id": stranger.identity.persona_id})})})
    v2 = V2.model_copy(update={"attempts": [changed, stranger, *ATTEMPTS["v2"][3:]]})

    report = compare_versions(REQUEST, V1, v2)

    assert not report.matched_complete
    assert (report.matched_pairs, report.missing_v2, report.identity_mismatches) == (497, 2, 1)
    assert report.unexpected_v2_session_ids == [stranger.session.id]
    pairs = {pair.persona_id: pair for pair in report.pairs}
    assert pairs[IDENTITIES[0].persona_id].status == "missing_v2"
    assert pairs[IDENTITIES[0].persona_id].v2_outcome is None
    assert pairs[IDENTITIES[1].persona_id].mismatched_fields == ["task_version", "action_budget"]
    assert report.v2.outcomes.identity_mismatch == 1
    assert report.v2.outcomes.no_attempt == 2
    assert sum(report.v2.outcomes.model_dump().values()) == 500
    assert report.v2.success_over_target.denominator == 500
    assert report.success_over_completed_pairs["v1"].denominator == 497


def test_error_categories_are_counted_separately():
    infrastructure = [attempt.model_copy(update={"session": attempt.session.model_copy(update={
        "status": "failed", "outcome": "infrastructure_failure", "stop_reason": reason,
        "feedback": None})}) for attempt, reason in zip(ATTEMPTS["v2"][:3],
                                                        ["BROWSER_TIMEOUT", "BROWSER_TIMEOUT", None])]
    irrelevant = ATTEMPTS["v2"][3].model_copy(update={"session": ATTEMPTS["v2"][3].session.model_copy(
        update={"outcome": "irrelevant"})})
    unrun = ATTEMPTS["v2"][4].model_copy(update={"session": ATTEMPTS["v2"][4].session.model_copy(
        update={"status": "running", "outcome": "not_run", "feedback": None})})
    v2 = V2.model_copy(update={"attempts": [*infrastructure, irrelevant, unrun, *ATTEMPTS["v2"][5:]]})

    report = compare_versions(REQUEST, V1, v2)

    assert report.v2.outcomes.infrastructure_failure == 3
    assert report.v2.outcomes.irrelevant == 1
    assert report.v2.outcomes.not_run == 1
    assert report.v2.infrastructure_stop_reasons == {"BROWSER_TIMEOUT": 2, "unrecorded": 1}
    assert report.v2.feedback.missing == 4
    assert report.matched_pairs == 500 and report.completed_pairs == 499
    assert not report.matched_complete


def test_inference_configuration_changes_are_disclosed():
    v2 = V2.model_copy(update={"experiment": V2.experiment.model_copy(update={"inference_profile": {
        "model": "test/other-model", "provider": "hf-inference", "temperature": 0.2}})})

    report = compare_versions(REQUEST, V1, v2)

    assert report.inference_configuration_changed
    assert [(c.key, c.v1_value, c.v2_value) for c in report.inference_changes] == [
        ("model", "test/model", "test/other-model"),
        ("prompt_version", "trial-v1", None),
        ("temperature", None, 0.2)]
    assert any("inference configuration differs" in item for item in report.limitations)


def test_optional_continuation_is_compared_separately():
    chose_continue = [attempt.model_copy(update={"session": attempt.session.model_copy(update={
        "feedback": attempt.session.feedback.model_copy(update={"decision": "continue"})})})
        for attempt in ATTEMPTS["v2"][:4]]
    continued = [attempt.model_copy(update={"phase": "continuation", "session": attempt.session.model_copy(
        update={"id": uuid4(), "outcome": "success", "actions": [], "feedback": None})})
        for attempt in chose_continue[:3]]
    v2 = V2.model_copy(update={"attempts": [*chose_continue, *ATTEMPTS["v2"][4:], *continued]})

    report = compare_versions(REQUEST, V1, v2)

    assert (report.continuation.v2_eligible, report.continuation.v2_attempted) == (4, 3)
    assert report.continuation.v2_outcomes.success == 3
    assert report.continuation.v2_outcomes.no_attempt == 1
    assert report.v2.outcomes.success == 375
    assert report.matched_pairs == 500 and report.matched_complete


def test_continuation_requires_a_mandatory_attempt_that_chose_to_continue():
    continued = ATTEMPTS["v2"][0].model_copy(update={"phase": "continuation", "session": ATTEMPTS[
        "v2"][0].session.model_copy(update={"id": uuid4(), "actions": [], "feedback": None})})

    with pytest.raises(EvidenceMismatch):
        compare_versions(REQUEST, V1, V2.model_copy(update={"attempts": [*ATTEMPTS["v2"], continued]}))


def test_model_time_is_labeled_and_never_human_time():
    report = compare_versions(REQUEST, V1, V2)

    assert report.v1.model_time.basis == report.v2.model_time.basis == TIME_BASIS
    assert "not human time" in TIME_BASIS
    assert (report.v1.model_time.median_seconds, report.v2.model_time.median_seconds) == (30, 20)
    assert report.v2.model_time.sessions_measured == 500
    assert "human_seconds" not in str(report.model_dump())


def test_retest_requires_a_human_approved_v2():
    with pytest.raises(RetestNotAllowed):
        build_retest_request(UNAPPROVED, V1)
    with pytest.raises(RetestNotAllowed):
        build_retest_request(APPROVED.model_copy(update={"state": "rolled_back"}), V1)
    with pytest.raises(RetestMismatch):
        build_retest_request(APPROVED, V2)


def test_v1_records_cannot_change_after_the_request():
    rewritten = ATTEMPTS["v1"][1].model_copy(update={"session": ATTEMPTS["v1"][1].session.model_copy(
        update={"outcome": "success"})})

    with pytest.raises(RetestMismatch):
        compare_versions(REQUEST, V1.model_copy(update={"attempts": [
            ATTEMPTS["v1"][0], rewritten, *ATTEMPTS["v1"][2:]]}), V2)


@pytest.mark.parametrize("experiment_update", [
    {"product_version_id": BASE.version_id},
    {"population_id": uuid4()},
    {"id": EXPERIMENTS["v1"].id},
    {"status": "fixture"},
])
def test_v2_must_run_the_candidate_on_the_same_population(experiment_update):
    v2 = V2.model_copy(update={"experiment": V2.experiment.model_copy(update=experiment_update)})

    with pytest.raises((RetestMismatch, EvidenceMismatch)):
        compare_versions(REQUEST, V1, v2)


def test_duplicate_mandatory_attempts_are_rejected():
    retry = ATTEMPTS["v2"][0].model_copy(update={"session": ATTEMPTS["v2"][0].session.model_copy(
        update={"id": uuid4(), "actions": [], "feedback": None})})

    with pytest.raises(EvidenceMismatch):
        compare_versions(REQUEST, V1, V2.model_copy(update={"attempts": [*ATTEMPTS["v2"], retry]}))


def test_short_v1_population_is_reported_not_hidden():
    request = build_retest_request(APPROVED, V1.model_copy(update={"attempts": ATTEMPTS["v1"][:10]}))
    report = compare_versions(request, V1.model_copy(update={"attempts": ATTEMPTS["v1"][:10]}),
                              V2.model_copy(update={"attempts": ATTEMPTS["v2"][:10]}))

    assert request.identity_shortfall == 490
    assert report.matched_pairs == 10 and not report.matched_complete
    assert report.v1.outcomes.no_attempt == 490
    assert report.v1.success_over_target.denominator == 500
    assert any("490 short of 500" in item for item in report.limitations)


def test_trial_identity_comes_from_persona_and_task():
    persona = PERSONAS[0]
    task = Task(id=uuid4(), scenario_id=persona.scenario.id, capability_ids=[uuid4()], goal="Check a table",
                initial_state_ref="state:blank", check_id="normal-v1", task_version="task-v1",
                action_budget=6)

    identity = trial_identity(persona, task, "population-v1")

    assert identity.corpus_version == persona.software_behavior.corpus_version
    assert identity.behavior_generation_version == persona.software_behavior.generation_version
    assert identity.time_budget_minutes == persona.scenario.time_budget_minutes
    with pytest.raises(RetestMismatch):
        trial_identity(persona, task.model_copy(update={"scenario_id": uuid4()}), "population-v1")


def test_routes_compare_fixture_runs_and_refuse_live_mode():
    client = TestClient(app)
    human, prioritizer = HUMAN.model_dump(), {"id": "prioritizer-1", "role": "prioritizer"}
    improvement = IMPROVEMENT.model_copy(update={"allowed_paths": STALE_STATUS.allowed_paths})
    run = client.post(f"/api/v1/improvements/{IMPROVEMENT.id}/patch-runs", json={
        "actor": prioritizer, "improvement": improvement.model_dump(mode="json")}).json()
    client.post(f"/api/v1/patch-runs/{run['id']}/review", json={"actor": human})
    patched = client.post(f"/api/v1/patch-runs/{run['id']}/edits", json={
        "actor": IMPLEMENTER.model_dump(),
        "edits": [edit.model_dump() for edit in STALE_STATUS.edits]}).json()
    # QA over HTTP needs Docker and Chromium (test_qa.py); record its results directly here.
    lifecycle.record_regression(UUID(run["id"]), QA, patched["patch"]["sha256"], [
        CheckResult(check_id=check, passed=True, evidence="Observed.")
        for check in run["base"]["fixed_check_ids"]])
    candidate = client.post(f"/api/v1/patch-runs/{run['id']}/approve",
                            json={"actor": human}).json()["candidate"]
    runs = {version: {
        "experiment": EXPERIMENTS[version].model_copy(update={
            "status": "fixture", "product_version_id": product_version_id}).model_dump(mode="json"),
        "attempts": [{"identity": attempt.identity.model_dump(mode="json"), "phase": "mandatory",
                      "session": attempt.session.model_copy(update={
                          "status": "fixture", "stream_mode": "fixture",
                          "product_version_id": product_version_id}).model_dump(mode="json")}
                     for attempt in ATTEMPTS[version][:3]],
    } for version, product_version_id in (("v1", UUID(run["base"]["version_id"])),
                                         ("v2", UUID(candidate["id"])))}

    live = client.post(f"/api/v1/patch-runs/{run['id']}/retest-requests",
                       json={"v1": {**runs["v1"], "experiment": V1.experiment.model_dump(mode="json")}})
    assert live.status_code == 422
    assert live.json()["error"]["code"] == "SUBMITTED_SESSIONS_FORBIDDEN"
    created = client.post(f"/api/v1/patch-runs/{run['id']}/retest-requests", json={"v1": runs["v1"]})
    assert created.status_code == 201
    request = created.json()
    assert request["mode"] == "fixture" and request["identity_shortfall"] == 497
    assert client.get(f"/api/v1/retest-requests/{request['id']}").json() == request
    report = client.post(f"/api/v1/retest-requests/{request['id']}/comparison", json=runs).json()
    assert report["mode"] == "fixture" and report["matched_pairs"] == 3
    assert not report["matched_complete"]
    assert report["limitations"][0].startswith("Fixture comparison")
    missing = client.get(f"/api/v1/retest-requests/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RETEST_REQUEST_NOT_FOUND"

    client.post(f"/api/v1/patch-runs/{run['id']}/rollback", json={"actor": human})
    retired = client.post(f"/api/v1/patch-runs/{run['id']}/retest-requests", json={"v1": runs["v1"]})
    assert retired.status_code == 409
    assert retired.json()["error"]["code"] == "RETEST_NOT_ALLOWED"
    app.dependency_overrides[get_settings] = lambda: Settings(app_mode="live", _env_file=None)
    try:
        refused = client.get(f"/api/v1/retest-requests/{request['id']}")
    finally:
        app.dependency_overrides.pop(get_settings)
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "DURABLE_TRIAL_RECORDS_REQUIRED"
