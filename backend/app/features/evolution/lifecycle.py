"""Improvement lifecycle: proposed -> reviewed -> patched -> regression -> human approval.

Every transition checks the current state and the actor's role. The frozen v1 base and its
fixed checks are copied into the run once and never change. Approval registers a separate
v2 candidate; rollback makes v1 active again. Records live in memory only.
"""

import hashlib
import json
from datetime import UTC, datetime
from threading import Lock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.app.features.evolution.models import (
    Actor,
    BaseVersion,
    CandidateVersion,
    CheckResult,
    IsolatedPatch,
    LifecycleEvent,
    LifecycleState,
    PatchFile,
    PatchRun,
)
from backend.app.features.evolution.patch_boundary import (
    PatchRejected,
    inspect_patch,
    validate_allowed_paths,
)
from backend.app.shared.contracts import Improvement


class LifecycleError(ValueError):
    code = "LIFECYCLE_ERROR"


class PatchRunNotFound(LifecycleError):
    code = "PATCH_RUN_NOT_FOUND"


class TransitionNotAllowed(LifecycleError):
    code = "TRANSITION_NOT_ALLOWED"


class ActorNotAllowed(LifecycleError):
    code = "ACTOR_NOT_ALLOWED"


class PatchOutsideScope(LifecycleError):
    code = "PATCH_OUTSIDE_SCOPE"


class RegressionMismatch(LifecycleError):
    code = "REGRESSION_MISMATCH"


def fixed_checks_digest(checks: list[dict]) -> str:
    canonical = json.dumps(checks, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _require_role(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise ActorNotAllowed(f"Role {actor.role} cannot perform this step.")


def _require_state(run: PatchRun, *states: LifecycleState) -> None:
    if run.state not in states:
        raise TransitionNotAllowed(
            f"Patch run is {run.state}; this step requires {' or '.join(states)}.")


class PatchLifecycle:
    """In-memory patch runs. A durable repository replaces this after the Neon gate."""

    def __init__(self) -> None:
        self._runs: dict[UUID, PatchRun] = {}
        self._lock = Lock()

    def _get(self, run_id: UUID) -> PatchRun:
        run = self._runs.get(run_id)
        if run is None:
            raise PatchRunNotFound("No patch run has this ID.")
        return run

    def _advance(self, run: PatchRun, state: LifecycleState, actor: Actor, note: str,
                 **changes) -> PatchRun:
        event = LifecycleEvent(state=state, actor=actor, at=datetime.now(UTC), note=note)
        updated = run.model_copy(deep=True, update={
            **changes, "state": state, "events": [*run.events, event]})
        self._runs[run.id] = updated
        return updated.model_copy(deep=True)

    def get(self, run_id: UUID) -> PatchRun:
        with self._lock:
            return self._get(run_id).model_copy(deep=True)

    def active_version_id(self, base_version_id: UUID) -> UUID:
        with self._lock:
            for run in self._runs.values():
                if run.base.version_id == base_version_id and run.state == "approved":
                    return run.candidate.id
            return base_version_id

    def propose(self, improvement: Improvement, base: BaseVersion, actor: Actor) -> PatchRun:
        _require_role(actor, "prioritizer", "human_reviewer")
        if improvement.status != "proposed":
            raise TransitionNotAllowed("Only a proposed, non-fixture improvement can start a patch run.")
        if not improvement.supporting_session_ids or improvement.evidence_strength == 0:
            raise TransitionNotAllowed("An improvement without session evidence cannot be patched.")
        try:
            validate_allowed_paths(improvement.allowed_paths)
        except PatchRejected as exc:
            raise PatchOutsideScope(str(exc)) from None
        event = LifecycleEvent(state="proposed", actor=actor, at=datetime.now(UTC),
                               note=improvement.title)
        run = PatchRun(id=uuid4(), improvement_id=improvement.id,
                       allowed_paths=list(improvement.allowed_paths),
                       acceptance_check=improvement.acceptance_check,
                       base=base.model_copy(deep=True), state="proposed", events=[event])
        with self._lock:
            self._runs[run.id] = run
        return run.model_copy(deep=True)

    def review(self, run_id: UUID, actor: Actor, note: str = "") -> PatchRun:
        """A human accepts the proposed scope before any patch is written."""
        _require_role(actor, "human_reviewer")
        with self._lock:
            run = self._get(run_id)
            _require_state(run, "proposed")
            return self._advance(run, "reviewed", actor, note or "Scope accepted.")

    def submit_patch(self, run_id: UUID, actor: Actor, files: list[PatchFile]) -> PatchRun:
        _require_role(actor, "implementer")
        with self._lock:
            run = self._get(run_id)
            _require_state(run, "reviewed")
            if any(event.actor.id == actor.id for event in run.events):
                raise ActorNotAllowed("The implementer cannot also propose or review this run.")
            try:
                digest = inspect_patch(files, run.allowed_paths)
            except PatchRejected as exc:
                raise PatchOutsideScope(str(exc)) from None
            patch = IsolatedPatch(files=list(files), sha256=digest)
            return self._advance(run, "patched", actor, f"Isolated patch {patch.sha256[:12]}.",
                                 implementer_id=actor.id, patch=patch)

    def record_regression(self, run_id: UUID, actor: Actor, patch_sha256: str,
                          results: list[CheckResult]) -> PatchRun:
        """Results must cover exactly v1's fixed checks for the submitted patch."""
        _require_role(actor, "qa_reviewer")
        with self._lock:
            run = self._get(run_id)
            _require_state(run, "patched")
            if actor.id == run.implementer_id:
                raise ActorNotAllowed("The implementer cannot record its own regression.")
            if patch_sha256 != run.patch.sha256:
                raise RegressionMismatch("Regression results refer to a different patch.")
            check_ids = [result.check_id for result in results]
            if sorted(check_ids) != sorted(run.base.fixed_check_ids):
                raise RegressionMismatch("Results must cover each fixed v1 check exactly once.")
            passed = all(result.passed for result in results)
            failed = [result.check_id for result in results if not result.passed]
            return self._advance(
                run, "regression_passed" if passed else "regression_failed", actor,
                "All fixed checks passed." if passed else f"Failed fixed checks: {failed}.",
                regression=list(results))

    def approve(self, run_id: UUID, actor: Actor, note: str = "") -> PatchRun:
        """Human approval registers a v2 candidate. v1 stays unchanged."""
        _require_role(actor, "human_reviewer")
        with self._lock:
            run = self._get(run_id)
            if actor.id == run.implementer_id:
                raise ActorNotAllowed("The implementer cannot promote its own patch.")
            _require_state(run, "regression_passed")
            if any(other.base.version_id == run.base.version_id and other.state == "approved"
                   for other in self._runs.values()):
                raise TransitionNotAllowed("Another v2 is active for this base; roll it back first.")
            candidate = CandidateVersion(
                id=uuid5(NAMESPACE_URL, f"repofusion:v2:{run.id}:{run.patch.sha256}"),
                label=f"{run.base.label} + patch {run.patch.sha256[:12]}",
                base_version_id=run.base.version_id, patch_sha256=run.patch.sha256,
                fixed_checks_sha256=run.base.fixed_checks_sha256)
            return self._advance(run, "approved", actor, note or "Human approved v2.",
                                 candidate=candidate)

    def reject(self, run_id: UUID, actor: Actor, note: str = "") -> PatchRun:
        _require_role(actor, "human_reviewer")
        with self._lock:
            run = self._get(run_id)
            _require_state(run, "proposed", "reviewed", "patched", "regression_passed")
            return self._advance(run, "rejected", actor, note or "Rejected by human review.")

    def rollback(self, run_id: UUID, actor: Actor, note: str = "") -> PatchRun:
        """Retire an approved v2. The base v1 becomes the active version again."""
        _require_role(actor, "human_reviewer")
        with self._lock:
            run = self._get(run_id)
            _require_state(run, "approved")
            return self._advance(run, "rolled_back", actor, note or "v2 rolled back to v1.")
