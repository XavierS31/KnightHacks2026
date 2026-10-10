"""Combine up to three accepted improvements into one v2 candidate. Only a human approves it.

Each patch must pass the fixed suite alone and with the others, on the same v1 commit and the
same fixed-check digest. A failed or rejected patch is left out; v1 stays the working version.
Approval writes the combined patch as one commit on a new branch. It never edits the v1 tree,
and it does not freeze v2: A's freeze turns the approved branch into a validated version.
"""
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import Field

from backend.app.features.evolution.engineering_roles import QAOutput
from backend.app.features.evolution.models import PatchFile, PatchRun
from backend.app.features.evolution.patch_boundary import patch_sha256
from backend.app.features.evolution.regression import (
    FIXED_SUITE,
    SHA256,
    RegressionCheck,
    RegressionReport,
    run_regression,
    write_patch,
)
from backend.app.shared.contracts import Contract

MAX_IMPROVEMENTS = 3


class CycleBlocked(ValueError):
    """The v2 gate is closed. v1 remains the active version."""


class AcceptedPatch(Contract):
    improvement_id: UUID
    implementer_id: str = Field(min_length=1, max_length=120)
    allowed_paths: list[str] = Field(min_length=1)
    files: list[PatchFile] = Field(min_length=1)
    regression: RegressionReport
    qa: QAOutput


class V2Candidate(Contract):
    id: UUID
    base_version_id: UUID
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    fixed_checks_sha256: str = Field(pattern=SHA256)
    improvement_ids: list[UUID]
    implementer_ids: list[str]
    files: list[PatchFile]
    combined_regression: RegressionReport


class V2Registration(Contract):
    candidate_id: UUID
    base_version_id: UUID
    status: Literal["approved_pending_freeze"] = "approved_pending_freeze"
    approved_by: str
    approved_at: datetime
    note: str
    branch: str
    commit_sha: str = Field(pattern=r"^[a-f0-9]{40}$")


def accept_patch_run(run: PatchRun, report: RegressionReport, qa: QAOutput) -> AcceptedPatch:
    """Join one lifecycle run with its build/integration/UI report and QA review.

    The run must have passed its fixed v1 checks. Human approval happens once, for the whole v2.
    """
    if run.state != "regression_passed" or run.patch is None or run.implementer_id is None:
        raise CycleBlocked(f"Patch run {run.id} has not passed its fixed v1 checks.")
    if report.patch_sha256 != run.patch.sha256:
        raise CycleBlocked(f"Patch run {run.id} has a suite report for another patch.")
    return AcceptedPatch(improvement_id=run.improvement_id, implementer_id=run.implementer_id,
                         allowed_paths=run.allowed_paths, files=run.patch.files,
                         regression=report, qa=qa)


def build_candidate(repo: Path, base_version_id: UUID, base_commit: str,
                    v1_fixed_checks_sha256: str, patches: list[AcceptedPatch],
                    suite: list[RegressionCheck] = FIXED_SUITE) -> V2Candidate:
    """Check every patch against the same v1 baseline, then rerun the suite on all of them."""
    if not 1 <= len(patches) <= MAX_IMPROVEMENTS:
        raise CycleBlocked(f"A v2 combines between 1 and {MAX_IMPROVEMENTS} improvements.")
    if len({patch.improvement_id for patch in patches}) != len(patches):
        raise CycleBlocked("Each improvement can enter v2 once.")
    paths: set[str] = set()
    for patch in patches:
        report = patch.regression
        if not report.passed:
            raise CycleBlocked(f"Improvement {patch.improvement_id} failed its fixed regression.")
        if report.base_commit != base_commit or report.fixed_checks_sha256 != v1_fixed_checks_sha256:
            raise CycleBlocked(f"Improvement {patch.improvement_id} was checked on another baseline.")
        if report.patch_sha256 != patch_sha256(patch.files) or patch.qa.patch_sha256 != report.patch_sha256:
            raise CycleBlocked(f"Improvement {patch.improvement_id} has evidence for another patch.")
        if patch.qa.recommendation != "approve":
            raise CycleBlocked(f"QA did not recommend improvement {patch.improvement_id}.")
        touched = {item.path for item in patch.files}
        if touched & paths:
            raise CycleBlocked("Two improvements change the same file; they are not isolated.")
        paths |= touched
    files = [item for patch in patches for item in patch.files]
    scopes = [scope for patch in patches for scope in patch.allowed_paths]
    combined = run_regression(repo, base_commit, files, scopes, suite)
    return V2Candidate(
        id=uuid5(base_version_id, f"repofusion-v2:{combined.patch_sha256}"),
        base_version_id=base_version_id, base_commit=combined.base_commit,
        fixed_checks_sha256=combined.fixed_checks_sha256,
        improvement_ids=[patch.improvement_id for patch in patches],
        implementer_ids=sorted({patch.implementer_id for patch in patches}),
        files=files, combined_regression=combined)


def approve_v2(repo: Path, candidate: V2Candidate, reviewer_id: str, note: str) -> V2Registration:
    """Human approval: commit the combined patch on a new branch. The v1 tree is not touched."""
    reviewer = reviewer_id.strip()
    if not reviewer:
        raise CycleBlocked("A named human reviewer is required to approve v2.")
    if reviewer in candidate.implementer_ids:
        raise CycleBlocked("An implementer cannot approve its own patch.")
    report = candidate.combined_regression
    if (not report.passed or report.patch_sha256 != patch_sha256(candidate.files)
            or report.fixed_checks_sha256 != candidate.fixed_checks_sha256):
        raise CycleBlocked("The combined patch has no passing fixed regression.")
    branch = f"evolution/v2-{str(candidate.id)[:8]}"
    if subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                       f"refs/heads/{branch}"], capture_output=True, timeout=60).returncode == 0:
        raise CycleBlocked(f"{branch} already exists; an approved v2 is never overwritten.")
    holder = Path(tempfile.mkdtemp(prefix="repofusion-v2-"))
    tree = holder / "tree"
    try:
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", branch, str(tree),
                        candidate.base_commit], check=True, capture_output=True, timeout=60)
        write_patch(tree, candidate.files)
        subprocess.run(["git", "-C", str(tree), "add", "--", *[item.path for item in candidate.files]],
                       check=True, capture_output=True, timeout=60)
        message = (f"Apply reviewed v2 candidate {candidate.id}\n\n"
                   f"Base version: {candidate.base_version_id}\nApproved by: {reviewer}\n"
                   f"Improvements: {', '.join(str(item) for item in candidate.improvement_ids)}\n"
                   f"Patch sha256: {report.patch_sha256}\n")
        subprocess.run(["git", "-C", str(tree), "commit", "-q", "-m", message],
                       check=True, capture_output=True, timeout=60)
        commit = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True, timeout=60).stdout.strip()
    except BaseException:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
                       capture_output=True, timeout=60)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", branch], capture_output=True, timeout=60)
        raise
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
                       capture_output=True, timeout=60)
        shutil.rmtree(holder, ignore_errors=True)
    return V2Registration(candidate_id=candidate.id, base_version_id=candidate.base_version_id,
                          approved_by=reviewer, approved_at=datetime.now(UTC), note=note,
                          branch=branch, commit_sha=commit)
