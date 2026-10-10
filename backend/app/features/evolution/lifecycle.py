"""Improvement lifecycle: proposed -> reviewed -> patched -> regression -> human approval.

Every transition checks the current state and the actor's role. The frozen v1 base and its
fixed checks are copied into the run once and never change. A release run composes the
bounded edits of two or three regression-passed runs and passes the same checks again.
Approval registers a separate v2 candidate; rollback makes v1 active again. Records live
in memory only.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from threading import Lock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.app.features.evolution.models import (
    Actor,
    BaseVersion,
    BoundedEdit,
    CandidateVersion,
    CheckResult,
    IsolatedPatch,
    LifecycleEvent,
    LifecycleState,
    PatchFile,
    PatchRun,
    RoleRun,
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


class EditConflict(LifecycleError):
    code = "EDIT_CONFLICT"


def validate_patch_paths(paths: list[str]) -> None:
    """Limit product patches to relative product/ descendants."""
    if not paths:
        raise ValueError("A non-empty approved product path list is required.")
    for raw in paths:
        normalized = raw.replace("\\", "/")
        path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(raw)
        if (path.is_absolute() or windows_path.drive or ".." in path.parts
                or not path.parts or path.parts[0] != "product" or len(path.parts) < 2):
            raise ValueError("Patch paths must stay within relative product/ descendants.")


def fixed_checks_digest(checks: list[dict]) -> str:
    canonical = json.dumps(checks, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _patch_digest(files: list[PatchFile]) -> str:
    canonical = json.dumps([[item.path, item.content] for item in files], separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def within_scope(path: str, allowed_paths: list[str]) -> bool:
    if "\\" in path or str(PurePosixPath(path)) != path:
        return False
    try:
        validate_patch_paths([path])
    except ValueError:
        return False
    candidate = PurePosixPath(path)
    return any(candidate.is_relative_to(PurePosixPath(allowed)) for allowed in allowed_paths)


def _require_role(actor: Actor, *roles: str) -> None:
    if actor.role not in roles:
        raise ActorNotAllowed(f"Role {actor.role} cannot perform this step.")


def _require_state(run: PatchRun, *states: LifecycleState) -> None:
    if run.state not in states:
        raise TransitionNotAllowed(
            f"Patch run is {run.state}; this step requires {' or '.join(states)}.")


class PatchLifecycle:
    """In-memory patch runs. A durable repository replaces this after the Neon gate.

    `patchable_paths` is the exact file set inside A's approved product boundary.
    """

    def __init__(self, patchable_paths: frozenset[str]) -> None:
        self._patchable = patchable_paths
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

    def propose(self, improvement: Improvement, base: BaseVersion, actor: Actor,
                analysis_record_id: UUID | None = None) -> PatchRun:
        _require_role(actor, "prioritizer", "human_reviewer")
        if improvement.status != "proposed":
            raise TransitionNotAllowed("Only a proposed, non-fixture improvement can start a patch run.")
        if not improvement.supporting_session_ids or improvement.evidence_strength == 0:
            raise TransitionNotAllowed("An improvement without session evidence cannot be patched.")
        try:
            validate_patch_paths(improvement.allowed_paths)
        except ValueError as exc:
            raise PatchOutsideScope(str(exc)) from None
        note = improvement.title
        if analysis_record_id is not None:
            note += f"\nE1 analysis record: {analysis_record_id}; proposal: {improvement.id}"
        event = LifecycleEvent(state="proposed", actor=actor, at=datetime.now(UTC), note=note)
        run = PatchRun(id=uuid4(), improvement_id=improvement.id, title=improvement.title,
                       issue=improvement.issue, allowed_paths=list(improvement.allowed_paths),
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

    def propose_release(self, run_ids: list[UUID], actor: Actor) -> PatchRun:
        """A human composes regression-passed runs into one run that must pass QA again."""
        _require_role(actor, "human_reviewer")
        with self._lock:
            if not 2 <= len(run_ids) <= 3 or len(set(run_ids)) != len(run_ids):
                raise TransitionNotAllowed("A release composes two or three distinct runs.")
            components = [self._get(run_id) for run_id in run_ids]
            for component in components:
                _require_state(component, "regression_passed")
                if component.component_run_ids or not component.patch.edits:
                    raise TransitionNotAllowed(
                        "A release composes bounded-edit runs, not files or other releases.")
            if any(component.base != components[0].base for component in components):
                raise TransitionNotAllowed("Release components must share one frozen base.")
            improvement_ids = [component.improvement_id for component in components]
            if len(set(improvement_ids)) != len(improvement_ids):
                raise TransitionNotAllowed("Release components must address distinct improvements.")
            now = datetime.now(UTC)
            run = PatchRun(
                id=uuid4(),
                improvement_id=uuid5(NAMESPACE_URL, "repofusion:release:" + ",".join(
                    sorted(str(identity) for identity in improvement_ids))),
                title="v2 release: " + " + ".join(component.title for component in components),
                issue=" ".join(f"({index}) {component.issue}"
                               for index, component in enumerate(components, start=1)),
                allowed_paths=sorted({path for component in components
                                      for path in component.allowed_paths}),
                acceptance_check=" ".join(
                    f"({index}) {component.acceptance_check}"
                    for index, component in enumerate(components, start=1)),
                base=components[0].base.model_copy(deep=True), state="reviewed",
                component_run_ids=list(run_ids),
                events=[LifecycleEvent(state="proposed", actor=actor, at=now,
                                       note=f"Release of {len(components)} regression-passed runs."),
                        LifecycleEvent(state="reviewed", actor=actor, at=now,
                                       note="Composed scope accepted.")])
            self._runs[run.id] = run
            return run.model_copy(deep=True)

    def _release_edits(self, run: PatchRun) -> list[BoundedEdit]:
        return [edit for run_id in run.component_run_ids for edit in self._get(run_id).patch.edits]

    def release_edits(self, run_id: UUID) -> list[BoundedEdit]:
        """The only edits a release may apply: each component's edits, in order."""
        with self._lock:
            run = self._get(run_id)
            if not run.component_run_ids:
                raise TransitionNotAllowed("This run is not a release.")
            return [edit.model_copy() for edit in self._release_edits(run)]

    def _check_patch_actor(self, run: PatchRun, actor: Actor) -> None:
        _require_role(actor, "implementer")
        _require_state(run, "reviewed")
        if any(event.actor.id == actor.id for event in run.events):
            raise ActorNotAllowed("The implementer cannot also propose or review this run.")

    def ready_for_patch(self, run_id: UUID, actor: Actor) -> PatchRun:
        """Check role, state and separation before an implementer spends inference."""
        with self._lock:
            run = self._get(run_id)
            self._check_patch_actor(run, actor)
            return run.model_copy(deep=True)

    def submit_patch(self, run_id: UUID, actor: Actor, files: list[PatchFile],
                     edits: list[BoundedEdit] | None = None,
                     implementer_run: RoleRun | None = None) -> PatchRun:
        edits = list(edits or [])
        with self._lock:
            run = self._get(run_id)
            self._check_patch_actor(run, actor)
            paths = [item.path for item in files]
            if len(set(paths)) != len(paths):
                raise PatchOutsideScope("A patch cannot list the same path twice.")
            outside = [path for path in paths if path not in self._patchable
                       or not within_scope(path, run.allowed_paths)]
            if outside:
                raise PatchOutsideScope(f"Patch paths are outside the approved scope: {outside}.")
            if run.component_run_ids and edits != self._release_edits(run):
                raise EditConflict("A release must apply exactly its components' edits in order.")
            patch = IsolatedPatch(files=list(files), sha256=_patch_digest(files), edits=edits)
            return self._advance(run, "patched", actor, f"Isolated patch {patch.sha256[:12]}.",
                                 implementer_id=actor.id, implementer_run=implementer_run,
                                 patch=patch)

    def _check_regression_actor(self, run: PatchRun, actor: Actor) -> None:
        _require_role(actor, "qa_reviewer")
        _require_state(run, "patched")
        if actor.id == run.implementer_id:
            raise ActorNotAllowed("The implementer cannot record its own regression.")

    def ready_for_regression(self, run_id: UUID, actor: Actor) -> PatchRun:
        """Check role, state and separation before QA spends time running checks."""
        with self._lock:
            run = self._get(run_id)
            self._check_regression_actor(run, actor)
            return run.model_copy(deep=True)

    def record_regression(self, run_id: UUID, actor: Actor, patch_sha256: str,
                          results: list[CheckResult]) -> PatchRun:
        """Results must cover exactly v1's fixed checks for the submitted patch."""
        with self._lock:
            run = self._get(run_id)
            self._check_regression_actor(run, actor)
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
            components = [self._get(run_id) for run_id in run.component_run_ids]
            if actor.id in {run.implementer_id, *(item.implementer_id for item in components)}:
                raise ActorNotAllowed("The implementer cannot promote its own patch.")
            _require_state(run, "regression_passed")
            if any(item.state != "regression_passed" for item in components):
                raise TransitionNotAllowed("Every release component must still be regression-passed.")
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
