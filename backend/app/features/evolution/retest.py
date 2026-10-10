"""Matched v2 retest: freeze v1 identities, hand them to B, then compare v1 and v2 honestly.

The comparison never drops a record. Each expected identity lands in one outcome bucket,
missing and mismatched v2 attempts stay visible, and optional continuation attempts stay
outside the mandatory denominators. Elapsed time is agent time, not human time.
"""

import hashlib
import json
from collections import Counter
from statistics import median
from threading import Lock
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.features.evolution.evidence import (
    FINISHED_STATUSES,
    EvidenceMismatch,
    validate_session_evidence,
)
from backend.app.features.evolution.models import (
    ComparisonReport,
    ConfigurationChange,
    ContinuationResult,
    ExperimentRun,
    FeedbackCounts,
    ModelTime,
    OutcomeCounts,
    PairResult,
    PatchRun,
    Rate,
    RetestRequest,
    Transition,
    TrialAttempt,
    TrialIdentity,
    TrialOutcome,
    VersionResult,
)
from backend.app.shared.contracts import Persona, Session, Task

TARGET_POPULATION = 500


class RetestError(ValueError):
    code = "RETEST_ERROR"


class RetestNotAllowed(RetestError):
    code = "RETEST_NOT_ALLOWED"


class RetestMismatch(RetestError):
    code = "RETEST_MISMATCH"


class RetestRequestNotFound(RetestError):
    code = "RETEST_REQUEST_NOT_FOUND"


def trial_identity(persona: Persona, task: Task, population_version: str) -> TrialIdentity:
    """Derive the frozen identity B records with each attempt."""
    if task.scenario_id != persona.scenario.id:
        raise RetestMismatch("The task does not belong to the persona's scenario.")
    behavior = persona.software_behavior
    return TrialIdentity(
        persona_id=persona.id, population_version=population_version,
        behavior_generation_version=behavior.generation_version,
        corpus_version=behavior.corpus_version, scenario_id=persona.scenario.id,
        task_id=task.id, task_version=task.task_version, check_id=task.check_id,
        initial_state_ref=task.initial_state_ref, action_budget=task.action_budget,
        time_budget_minutes=persona.scenario.time_budget_minutes)


def _run_mode(run: ExperimentRun):
    return "fixture" if run.experiment.status == "fixture" else "live"


def _phase_index(run: ExperimentRun, phase: str) -> dict[UUID, TrialAttempt]:
    """One attempt per persona and phase; duplicates are an integrity error, not a retry."""
    index: dict[UUID, TrialAttempt] = {}
    for attempt in run.attempts:
        if attempt.phase != phase:
            continue
        if attempt.identity.persona_id in index:
            raise EvidenceMismatch(f"A persona has more than one {phase} attempt in one experiment.")
        index[attempt.identity.persona_id] = attempt
    return index


def _validated(run: ExperimentRun, version_id: UUID) -> tuple[dict, dict]:
    """Ground every session in the run, then split it into mandatory and continuation."""
    experiment = run.experiment
    if experiment.product_version_id != version_id:
        raise RetestMismatch("The experiment did not run the expected product version.")
    sessions = [attempt.session for attempt in run.attempts]
    validate_session_evidence(experiment.id, sessions, _run_mode(run))
    for attempt in run.attempts:
        if (attempt.session.persona_id != attempt.identity.persona_id
                or attempt.session.product_version_id != version_id):
            raise EvidenceMismatch("A session does not match its persona or product version.")
    mandatory = _phase_index(run, "mandatory")
    continuation = _phase_index(run, "continuation")
    if len(mandatory) > TARGET_POPULATION:
        raise RetestMismatch("Mandatory attempts exceed the 500-person target population.")
    for persona_id, attempt in continuation.items():
        first = mandatory.get(persona_id)
        if (first is None or first.session.feedback is None
                or first.session.feedback.decision != "continue"
                or first.identity != attempt.identity):
            raise EvidenceMismatch(
                "A continuation must follow the same identity's mandatory attempt that chose to continue.")
    return mandatory, continuation


def _records_digest(mandatory: dict[UUID, TrialAttempt]) -> str:
    """Fingerprint the frozen v1 records so the comparison sees the exact same v1."""
    records = [attempt.model_dump(mode="json")
               for _, attempt in sorted(mandatory.items(), key=lambda item: str(item[0]))]
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_retest_request(run: PatchRun, v1: ExperimentRun) -> RetestRequest:
    """Ask B to rerun every frozen v1 identity once on the human-approved v2."""
    if run.state != "approved" or run.candidate is None:
        raise RetestNotAllowed("Only a human-approved, active v2 can be retested.")
    mandatory, _ = _validated(v1, run.base.version_id)
    identities = [mandatory[key].identity for key in sorted(mandatory, key=str)]
    return RetestRequest(
        id=uuid5(NAMESPACE_URL, f"repofusion:retest:{run.candidate.id}:{v1.experiment.id}"),
        mode=_run_mode(v1), patch_run_id=run.id, base_version_id=run.base.version_id,
        candidate_version_id=run.candidate.id, candidate_patch_sha256=run.candidate.patch_sha256,
        fixed_check_ids=list(run.base.fixed_check_ids),
        fixed_checks_sha256=run.base.fixed_checks_sha256,
        population_id=v1.experiment.population_id, v1_experiment_id=v1.experiment.id,
        v1_records_sha256=_records_digest(mandatory), identities=identities,
        identity_shortfall=TARGET_POPULATION - len(identities),
        inference_profile=dict(v1.experiment.inference_profile),
        instructions=[
            "Run each identity exactly once as a mandatory attempt on the candidate version.",
            "Keep persona, behavior, corpus, scenario, task, check, fixture state and budgets unchanged.",
            "Reuse the v1 inference profile; the comparison discloses every changed key.",
            "Record failed, cancelled and unrun attempts; do not retry silently or drop them.",
            "Run optional continuation only after all mandatory attempts and label it continuation.",
        ])


def _outcome(session: Session, mode: str) -> TrialOutcome:
    if mode == "live" and session.status not in FINISHED_STATUSES:
        return "not_run"
    return session.outcome


def _counts(outcomes: list[TrialOutcome], expected: int, mismatched: int = 0) -> OutcomeCounts:
    tally = Counter(outcomes)
    return OutcomeCounts(
        success=tally["success"], application_failure=tally["application_failure"],
        infrastructure_failure=tally["infrastructure_failure"], irrelevant=tally["irrelevant"],
        not_run=tally["not_run"], identity_mismatch=mismatched,
        no_attempt=expected - len(outcomes) - mismatched)


def _rate(numerator: int, denominator: int) -> Rate:
    return Rate(numerator=numerator, denominator=denominator,
                value=round(numerator / denominator, 6) if denominator else None)


def _model_time(sessions: list[Session]) -> ModelTime:
    spans = [(max(a.timestamp for a in s.actions) - min(a.timestamp for a in s.actions)).total_seconds()
             for s in sessions if len(s.actions) >= 2]
    return ModelTime(sessions_measured=len(spans), median_seconds=median(spans) if spans else None)


def _version_result(attempts: list[TrialAttempt], version_id: UUID, experiment_id: UUID,
                    mode: str, mismatched: int = 0) -> VersionResult:
    """Count one version's attempts for the expected identities against the full target."""
    sessions = [attempt.session for attempt in attempts]
    outcomes = [_outcome(session, mode) for session in sessions]
    feedback = [session.feedback for session in sessions if session.feedback is not None]
    relevance = Counter(item.post_trial_relevance for item in feedback)
    stop_reasons = Counter(
        session.stop_reason or "unrecorded" for session, outcome in zip(sessions, outcomes)
        if outcome == "infrastructure_failure")
    return VersionResult(
        version_id=version_id, experiment_id=experiment_id,
        outcomes=_counts(outcomes, TARGET_POPULATION, mismatched),
        infrastructure_stop_reasons=dict(sorted(stop_reasons.items())),
        success_over_target=_rate(outcomes.count("success"), TARGET_POPULATION),
        feedback=FeedbackCounts(
            present=len(feedback), missing=TARGET_POPULATION - len(feedback),
            chose_continue=sum(item.decision == "continue" for item in feedback),
            post_trial_relevance={level: relevance[level] for level in ("low", "medium", "high")}),
        model_time=_model_time(sessions))


def _inference_changes(v1_profile: dict, v2_profile: dict) -> list[ConfigurationChange]:
    return [ConfigurationChange(key=key, v1_value=v1_profile.get(key), v2_value=v2_profile.get(key))
            for key in sorted(v1_profile.keys() | v2_profile.keys())
            if key not in v1_profile or key not in v2_profile or v1_profile[key] != v2_profile[key]]


def compare_versions(request: RetestRequest, v1: ExperimentRun, v2: ExperimentRun) -> ComparisonReport:
    """Pair each frozen v1 identity with its v2 attempt and report every gap."""
    if v1.experiment.id != request.v1_experiment_id:
        raise RetestMismatch("The v1 experiment is not the one this retest request froze.")
    if v2.experiment.id == v1.experiment.id or v2.experiment.population_id != request.population_id:
        raise RetestMismatch("The v2 experiment must be separate and use the same population.")
    mode = request.mode
    if _run_mode(v1) != mode or _run_mode(v2) != mode:
        raise RetestMismatch("Fixture and live experiments cannot be compared with each other.")
    v1_mandatory, v1_continuation = _validated(v1, request.base_version_id)
    v2_mandatory, v2_continuation = _validated(v2, request.candidate_version_id)
    if _records_digest(v1_mandatory) != request.v1_records_sha256:
        raise RetestMismatch("The v1 records changed after the retest request froze them.")

    pairs: list[PairResult] = []
    matched: list[tuple[TrialAttempt, TrialAttempt]] = []
    expected_v2: list[TrialAttempt] = []
    for identity in request.identities:
        first = v1_mandatory[identity.persona_id]
        second = v2_mandatory.get(identity.persona_id)
        mismatched = [] if second is None else [
            field for field in TrialIdentity.model_fields
            if getattr(identity, field) != getattr(second.identity, field)]
        status = "missing_v2" if second is None else "identity_mismatch" if mismatched else "matched"
        if status == "matched":
            matched.append((first, second))
            expected_v2.append(second)
        pairs.append(PairResult(
            persona_id=identity.persona_id, status=status, mismatched_fields=mismatched,
            v1_session_id=first.session.id,
            v2_session_id=None if second is None else second.session.id,
            v1_outcome=_outcome(first.session, mode),
            v2_outcome=None if second is None else _outcome(second.session, mode)))
    expected_ids = {identity.persona_id for identity in request.identities}
    unexpected = sorted((attempt.session.id for persona_id, attempt in v2_mandatory.items()
                         if persona_id not in expected_ids), key=str)

    completed = [(first, second) for first, second in matched
                 if _outcome(first.session, mode) != "not_run"
                 and _outcome(second.session, mode) != "not_run"]
    transitions = Counter((_outcome(first.session, mode), _outcome(second.session, mode))
                          for first, second in completed)
    changes = _inference_changes(request.inference_profile, v2.experiment.inference_profile)
    v1_eligible = [a for a in v1_mandatory.values()
                   if a.session.feedback is not None and a.session.feedback.decision == "continue"]
    v2_eligible = [a for a in expected_v2
                   if a.session.feedback is not None and a.session.feedback.decision == "continue"]
    v2_continued = [v2_continuation[a.identity.persona_id] for a in v2_eligible
                    if a.identity.persona_id in v2_continuation]
    missing_v2 = sum(pair.status == "missing_v2" for pair in pairs)
    mismatches = sum(pair.status == "identity_mismatch" for pair in pairs)
    matched_complete = (len(matched) == TARGET_POPULATION and not unexpected
                        and all(_outcome(second.session, mode) != "not_run" for _, second in matched))

    limitations = [
        "Rates over the target count every identity without a completed attempt as not successful.",
        "Paired rates use only identities with a matched, finished attempt on both versions.",
        "Elapsed time is agent wall clock between recorded actions. It is not human task time.",
        "Feedback is synthetic persona output, not measured human opinion.",
        "Continuation attempts are optional and excluded from mandatory denominators.",
    ]
    if mode == "fixture":
        limitations.insert(0, "Fixture comparison: no real browser trial, inference or persistence occurred.")
    if changes:
        limitations.append("The v2 inference configuration differs from v1; see inference_changes.")
    if request.identity_shortfall:
        limitations.append(
            f"v1 froze {len(request.identities)} identities, {request.identity_shortfall} short of 500.")

    return ComparisonReport(
        retest_request_id=request.id, mode=mode, expected_identities=len(request.identities),
        matched_pairs=len(matched), completed_pairs=len(completed), missing_v2=missing_v2,
        identity_mismatches=mismatches, unexpected_v2_session_ids=unexpected,
        matched_complete=matched_complete,
        v1=_version_result(list(v1_mandatory.values()), request.base_version_id,
                           v1.experiment.id, mode),
        v2=_version_result(expected_v2, request.candidate_version_id, v2.experiment.id, mode,
                           mismatches),
        success_over_completed_pairs={
            "v1": _rate(sum(_outcome(f.session, mode) == "success" for f, _ in completed),
                        len(completed)),
            "v2": _rate(sum(_outcome(s.session, mode) == "success" for _, s in completed),
                        len(completed))},
        transitions=[Transition(v1_outcome=before, v2_outcome=after, count=count)
                     for (before, after), count in sorted(transitions.items())],
        inference_configuration_changed=bool(changes), inference_changes=changes,
        continuation=ContinuationResult(
            v1_eligible=len(v1_eligible), v1_attempted=len(v1_continuation),
            v1_outcomes=_counts([_outcome(a.session, mode) for a in v1_continuation.values()],
                                len(v1_eligible)),
            v2_eligible=len(v2_eligible), v2_attempted=len(v2_continued),
            v2_outcomes=_counts([_outcome(a.session, mode) for a in v2_continued], len(v2_eligible))),
        pairs=pairs, limitations=limitations,
        next_gate=("Matched 500-person comparison is complete; review it before reporting results."
                   if matched_complete else
                   "Finish the missing or mismatched v2 attempts before reporting a complete comparison."))


class RetestRegistry:
    """In-memory retest requests. A durable repository replaces this after the Neon gate."""

    def __init__(self) -> None:
        self._requests: dict[UUID, RetestRequest] = {}
        self._lock = Lock()

    def save(self, request: RetestRequest) -> RetestRequest:
        with self._lock:
            self._requests[request.id] = request
        return request.model_copy(deep=True)

    def get(self, request_id: UUID) -> RetestRequest:
        with self._lock:
            request = self._requests.get(request_id)
        if request is None:
            raise RetestRequestNotFound("No retest request has this ID.")
        return request.model_copy(deep=True)
