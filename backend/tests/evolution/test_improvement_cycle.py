import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.features.evolution.engineering_roles import QAOutput
from backend.app.features.evolution.improvement_cycle import (
    MAX_IMPROVEMENTS,
    AcceptedPatch,
    CycleBlocked,
    accept_patch_run,
    approve_v2,
    build_candidate,
)
from backend.app.features.evolution.lifecycle import PatchLifecycle
from backend.app.features.evolution.models import Actor, BaseVersion, CheckResult, PatchFile
from backend.app.features.evolution.patch_boundary import (
    FIXED_CHECK_PATHS,
    PatchRejected,
    fixed_checks_sha256,
)
from backend.app.features.evolution.regression import RegressionCheck, run_regression
from backend.app.shared.contracts import Improvement

APP_JS = "frontend/src/features/integration/product/app.js"
STYLE = "frontend/src/features/integration/product/style.css"
CHECKS = "backend/app/features/integration/product/checks.py"
# Stand-in fixed suite: each patch adds a marker; "broken" text and both markers together fail.
SUITE = [
    RegressionCheck(id="build", kind="build", command=[sys.executable, "-c", (
        "import pathlib; text = pathlib.Path('frontend/src/features/integration/product/app.js')"
        ".read_text() + pathlib.Path('frontend/src/features/integration/product/style.css')"
        ".read_text(); raise SystemExit('broken' in text)")]),
    RegressionCheck(id="ui", kind="ui", command=[sys.executable, "-c", (
        "import pathlib; text = pathlib.Path('frontend/src/features/integration/product/app.js')"
        ".read_text() + pathlib.Path('frontend/src/features/integration/product/style.css')"
        ".read_text(); raise SystemExit('conflict-a' in text and 'conflict-b' in text)")]),
]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for path, text in [*[(path, f"# fixed v1 check {path}\n") for path in FIXED_CHECK_PATHS],
                       (APP_JS, "ready();\n"), (STYLE, "body{}\n")]:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    for command in (["init", "-q", "-b", "master"], ["config", "user.email", "c@example.test"],
                    ["config", "user.name", "Developer C"], ["add", "-A"],
                    ["commit", "-q", "-m", "v1"]):
        subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
    return root


def test_passing_patch_runs_isolated_and_leaves_v1_untouched(repo):
    v1_digest = fixed_checks_sha256(repo)
    report = run_regression(repo, "HEAD", [PatchFile(path=APP_JS, content="ready(); hint();\n")],
                            [APP_JS], SUITE)
    assert report.passed and report.checks_unchanged
    assert [result.check_id for result in report.results] == ["build", "ui"]
    assert report.fixed_checks_sha256 == v1_digest
    assert (repo / APP_JS).read_text() == "ready();\n"
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True,
                          text=True, check=True).stdout == ""
    assert len(subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True,
                              text=True, check=True).stdout.splitlines()) == 1


def test_failed_regression_is_reported_and_v1_stays(repo):
    report = run_regression(repo, "HEAD", [PatchFile(path=APP_JS, content="broken();\n")],
                            [APP_JS], SUITE)
    assert not report.passed
    assert [(result.check_id, result.passed, result.exit_code) for result in report.results] == [
        ("build", False, 1), ("ui", True, 0)]
    assert (repo / APP_JS).read_text() == "ready();\n"


def test_rejected_patch_is_never_written_or_checked(repo):
    with pytest.raises(PatchRejected, match="fixed check"):
        run_regression(repo, "HEAD", [PatchFile(path=CHECKS, content="def evaluate(*_): return True")],
                       [APP_JS], SUITE)
    assert (repo / CHECKS).read_text().startswith("# fixed v1 check")
    assert len(subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True,
                              text=True, check=True).stdout.splitlines()) == 1


def test_symlink_cannot_redirect_a_patch_into_the_fixed_checks(repo):
    link = "frontend/src/features/integration/product/helper.js"
    (repo / link).symlink_to(repo / CHECKS)
    subprocess.run(["git", "-C", str(repo), "add", link], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "link"], check=True)
    with pytest.raises(PatchRejected, match="outside the isolated tree"):
        run_regression(repo, "HEAD", [PatchFile(path=link, content="def evaluate(*_): return True")],
                       [link], SUITE)
    assert (repo / CHECKS).read_text().startswith("# fixed v1 check")


def test_checks_get_no_caller_credentials_and_time_out(repo, monkeypatch):
    secret = "hf_" + "s" * 30
    monkeypatch.setenv("HF_TOKEN", secret)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db.example/neon")
    suite = [
        RegressionCheck(id="env", kind="integration", command=[sys.executable, "-c", (
            "import os; print(os.environ.get('HF_TOKEN'), os.environ.get('DATABASE_URL'), "
            "os.environ['APP_MODE']); raise SystemExit(os.environ.get('HF_TOKEN') != '')")]),
        RegressionCheck(id="slow", kind="ui", timeout_seconds=0.5,
                        command=[sys.executable, "-c", "import time; time.sleep(5)"]),
    ]
    report = run_regression(repo, "HEAD", [PatchFile(path=APP_JS, content="ready();\n")],
                            [APP_JS], suite)
    environment, slow = report.results
    assert environment.passed and environment.output_tail.split() == ["fixture"]
    assert secret not in environment.output_tail and os.environ["HF_TOKEN"] == secret
    assert not slow.passed and slow.exit_code is None and "Timed out" in slow.output_tail
    assert not report.passed


def test_two_reviewed_improvements_become_a_human_approved_v2_branch(repo):
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    v1_digest = fixed_checks_sha256(repo)
    accepted = []
    for path, content in [(APP_JS, "ready(); explainErrors();\n"), (STYLE, "body{gap:1rem}\n")]:
        files = [PatchFile(path=path, content=content)]
        report = run_regression(repo, base, files, [path], SUITE)
        accepted.append(AcceptedPatch(
            improvement_id=uuid4(), implementer_id="implementer-hf", allowed_paths=[path],
            files=files, regression=report,
            qa=QAOutput(patch_sha256=report.patch_sha256, findings=[], recommendation="approve")))
    version_id = uuid4()
    candidate = build_candidate(repo, version_id, base, v1_digest, accepted, SUITE)
    assert candidate.combined_regression.passed
    assert candidate.id == build_candidate(repo, version_id, base, v1_digest, accepted, SUITE).id

    with pytest.raises(CycleBlocked, match="cannot approve its own"):
        approve_v2(repo, candidate, "implementer-hf", "self review")
    with pytest.raises(CycleBlocked, match="named human"):
        approve_v2(repo, candidate, "  ", "")
    registration = approve_v2(repo, candidate, "reviewer-sanan", "Both changes match the evidence.")

    assert registration.status == "approved_pending_freeze"
    changed = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", base,
                              registration.branch], capture_output=True, text=True,
                             check=True).stdout.split()
    assert sorted(changed) == sorted([APP_JS, STYLE])
    assert subprocess.run(["git", "-C", str(repo), "rev-parse", registration.branch],
                          capture_output=True, text=True, check=True).stdout.strip() == registration.commit_sha
    assert (repo / APP_JS).read_text() == "ready();\n" and fixed_checks_sha256(repo) == v1_digest
    with pytest.raises(CycleBlocked, match="never overwritten"):
        approve_v2(repo, candidate, "reviewer-sanan", "again")


def test_patches_that_fail_together_block_v2_and_keep_v1(repo):
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    v1_digest = fixed_checks_sha256(repo)
    accepted = []
    for path, content in [(APP_JS, "conflict-a\n"), (STYLE, "conflict-b\n")]:
        files = [PatchFile(path=path, content=content)]
        report = run_regression(repo, base, files, [path], SUITE)
        assert report.passed
        accepted.append(AcceptedPatch(
            improvement_id=uuid4(), implementer_id="implementer-hf", allowed_paths=[path],
            files=files, regression=report,
            qa=QAOutput(patch_sha256=report.patch_sha256, findings=[], recommendation="approve")))
    candidate = build_candidate(repo, uuid4(), base, v1_digest, accepted, SUITE)
    assert not candidate.combined_regression.passed
    with pytest.raises(CycleBlocked, match="no passing fixed regression"):
        approve_v2(repo, candidate, "reviewer-sanan", "")
    assert subprocess.run(["git", "-C", str(repo), "branch", "--list", "evolution/*"],
                          capture_output=True, text=True, check=True).stdout == ""


def test_candidate_requires_passing_qa_approved_isolated_evidence(repo):
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    v1_digest = fixed_checks_sha256(repo)
    good_files = [PatchFile(path=APP_JS, content="ready(); hint();\n")]
    good = run_regression(repo, base, good_files, [APP_JS], SUITE)
    bad_files = [PatchFile(path=APP_JS, content="broken();\n")]
    bad = run_regression(repo, base, bad_files, [APP_JS], SUITE)
    approve = QAOutput(patch_sha256=good.patch_sha256, findings=[], recommendation="approve")
    patch = AcceptedPatch(improvement_id=uuid4(), implementer_id="implementer-hf",
                          allowed_paths=[APP_JS], files=good_files, regression=good, qa=approve)

    cases = [
        ([patch.model_copy(update={"files": bad_files, "regression": bad})], "failed its fixed"),
        ([patch.model_copy(update={"qa": approve.model_copy(update={"recommendation": "reject"})})],
         "QA did not recommend"),
        ([patch.model_copy(update={"files": [PatchFile(path=APP_JS, content="other();\n")]})],
         "another patch"),
        ([patch, patch.model_copy(update={"improvement_id": uuid4()})], "same file"),
        ([patch, patch], "once"),
        ([patch.model_copy(update={"improvement_id": uuid4()})
          for _ in range(MAX_IMPROVEMENTS + 1)], "between 1 and"),
        ([], "between 1 and"),
    ]
    for patches, reason in cases:
        with pytest.raises(CycleBlocked, match=reason):
            build_candidate(repo, uuid4(), base, v1_digest, patches, SUITE)
    with pytest.raises(CycleBlocked, match="another baseline"):
        build_candidate(repo, uuid4(), base, "0" * 64, [patch], SUITE)



def test_lifecycle_run_joins_the_cycle_only_after_its_fixed_checks_pass(repo):
    lifecycle = PatchLifecycle()
    implementer = Actor(id="implementer-hf", role="implementer")
    improvement = Improvement(
        id=uuid4(), title="Explain schema errors", issue="Personas missed the error cell",
        supporting_session_ids=[uuid4()], severity=3, affected_share=0.4, evidence_strength=1,
        estimated_effort_hours=1, acceptance_check="sourcetable-type-error-v1",
        allowed_paths=[APP_JS], status="proposed")
    base = BaseVersion(version_id=uuid4(), label="SourceTable v1",
                       fixed_check_ids=["sourcetable-type-error-v1"], fixed_checks_sha256="a" * 64)
    files = [PatchFile(path=APP_JS, content="ready(); explainErrors();\n")]
    run = lifecycle.propose(improvement, base, Actor(id="prioritizer", role="prioritizer"))
    lifecycle.review(run.id, Actor(id="reviewer-sanan", role="human_reviewer"))
    patched = lifecycle.submit_patch(run.id, implementer, files)
    report = run_regression(repo, "HEAD", files, [APP_JS], SUITE)
    qa = QAOutput(patch_sha256=report.patch_sha256, findings=[], recommendation="approve")
    assert report.patch_sha256 == patched.patch.sha256

    with pytest.raises(CycleBlocked, match="not passed its fixed v1 checks"):
        accept_patch_run(patched, report, qa)
    passed = lifecycle.record_regression(run.id, Actor(id="qa", role="qa_reviewer"),
                                         patched.patch.sha256, [CheckResult(
                                             check_id="sourcetable-type-error-v1", passed=True,
                                             evidence="Error cell selected.")])
    accepted = accept_patch_run(passed, report, qa)
    assert (accepted.improvement_id, accepted.implementer_id) == (improvement.id, implementer.id)
    other = run_regression(repo, "HEAD", [PatchFile(path=APP_JS, content="ready(); other();\n")],
                           [APP_JS], SUITE)
    with pytest.raises(CycleBlocked, match="another patch"):
        accept_patch_run(passed, other, qa)


@pytest.mark.skipif(os.environ.get("C_REGRESSION_TESTS") != "1",
                    reason="Set C_REGRESSION_TESTS=1 for the real Node/pytest/Chromium suite")
def test_real_fixed_suite_accepts_a_style_patch_and_catches_a_broken_ui():
    # Runs on the committed HEAD of this repository; the working tree is never written.
    root = Path(__file__).resolve().parents[3]
    style = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{STYLE}"], capture_output=True,
                           text=True, check=True).stdout
    app_js = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{APP_JS}"], capture_output=True,
                            text=True, check=True).stdout
    styled = run_regression(root, "HEAD", [PatchFile(path=STYLE, content=style + "/* v2 */\n")],
                            [STYLE])
    assert styled.passed, [result for result in styled.results if not result.passed]
    assert [result.kind for result in styled.results] == ["build", "build", "integration", "ui"]
    broken = run_regression(root, "HEAD", [PatchFile(path=APP_JS, content=app_js.replace(
        "$('load-sample').onclick", "$('missing-sample').onclick"))], [APP_JS])
    assert not broken.passed
    assert {result.check_id for result in broken.results if not result.passed} == {"product-ui"}
