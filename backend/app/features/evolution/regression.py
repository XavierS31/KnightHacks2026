"""Apply an inspected patch in a detached git worktree and run C's fixed regression suite.

The working tree that holds v1 is never written. The suite is defined here, not by the patch,
and the fixed-check digest is compared before and after the write. Checks run the patched code
as local processes without HF or database credentials; they are not a sandbox, so run them only
on a disposable development machine.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal

from pydantic import Field

from backend.app.features.evolution.models import PatchFile
from backend.app.features.evolution.patch_boundary import (
    SECRET_PATTERN,
    PatchRejected,
    fixed_checks_sha256,
    inspect_patch,
)
from backend.app.shared.contracts import Contract

SHA256 = r"^[a-f0-9]{64}$"
OUTPUT_TAIL_CHARS = 2000
PASSED_ENVIRONMENT = ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "PLAYWRIGHT_BROWSERS_PATH")


class RegressionCheck(Contract):
    id: str
    kind: Literal["build", "integration", "ui"]
    command: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(default=300, gt=0)


class CheckOutcome(Contract):
    check_id: str
    kind: Literal["build", "integration", "ui"]
    passed: bool
    exit_code: int | None
    duration_ms: int = Field(ge=0)
    output_tail: str


class RegressionReport(Contract):
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    patch_sha256: str = Field(pattern=SHA256)
    fixed_checks_sha256: str = Field(pattern=SHA256)
    checks_unchanged: bool
    results: list[CheckOutcome]
    passed: bool


FIXED_SUITE = [
    RegressionCheck(id="product-python-build", kind="build", command=[
        sys.executable, "-m", "compileall", "-q", "backend/app/features/integration/product"]),
    RegressionCheck(id="product-js-build", kind="build", command=[
        "node", "--check", "frontend/src/features/integration/product/app.js"]),
    RegressionCheck(id="product-integration", kind="integration", command=[
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "backend/tests/integration/test_product.py"]),
    RegressionCheck(id="product-ui", kind="ui", command=[
        sys.executable, "-m", "backend.app.features.evolution.product_ui_check"], timeout_seconds=120),
]


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True,
                          text=True, timeout=60).stdout.strip()


def write_patch(tree: Path, files: list[PatchFile]) -> None:
    root = tree.resolve()
    for item in files:
        target = tree / item.path
        # Refuse to follow a committed symlink out of the isolated tree.
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise PatchRejected(f"{item.path} resolves outside the isolated tree.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content.encode())


def _check_environment(tree: Path) -> dict[str, str]:
    """Pass only what the checks need. Credentials from the caller never reach patched code."""
    keep = {name: os.environ[name] for name in PASSED_ENVIRONMENT if name in os.environ}
    return {**keep, "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1",
            "APP_MODE": "fixture", "HF_TOKEN": "", "DATABASE_URL": "", "GITHUB_TOKEN": ""}


def _run(check: RegressionCheck, tree: Path) -> CheckOutcome:
    started = time.monotonic()
    try:
        completed = subprocess.run(check.command, cwd=tree, env=_check_environment(tree),
                                   capture_output=True, text=True, timeout=check.timeout_seconds)
        exit_code, output = completed.returncode, completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as expired:
        exit_code = None
        output = f"Timed out after {check.timeout_seconds} seconds. " + str(expired.output or "")
    except OSError as failure:
        exit_code, output = None, f"Could not start the check: {failure.strerror}"
    return CheckOutcome(
        check_id=check.id, kind=check.kind, passed=exit_code == 0, exit_code=exit_code,
        duration_ms=round((time.monotonic() - started) * 1000),
        output_tail=SECRET_PATTERN.sub("<redacted>", output[-OUTPUT_TAIL_CHARS:]))


def run_regression(repo: Path, base_commit: str, files: list[PatchFile], allowed_paths: list[str],
                   suite: list[RegressionCheck] = FIXED_SUITE) -> RegressionReport:
    """Inspect, apply in isolation and check. Raises PatchRejected before any write."""
    digest = inspect_patch(files, allowed_paths)
    commit = _git(repo, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
    holder = Path(tempfile.mkdtemp(prefix="repofusion-patch-"))
    tree = holder / "tree"
    try:
        _git(repo, "worktree", "add", "--detach", str(tree), commit)
        baseline = fixed_checks_sha256(tree)
        write_patch(tree, files)
        unchanged = fixed_checks_sha256(tree) == baseline
        # A changed check is a failed regression; its results would be meaningless.
        results = [_run(check, tree) for check in suite] if unchanged else []
        return RegressionReport(
            base_commit=commit, patch_sha256=digest, fixed_checks_sha256=baseline,
            checks_unchanged=unchanged, results=results,
            passed=unchanged and bool(results) and all(result.passed for result in results))
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
                       capture_output=True, timeout=60)
        shutil.rmtree(holder, ignore_errors=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True, timeout=60)
