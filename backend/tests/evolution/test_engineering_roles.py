from uuid import uuid4

import pytest

from backend.app.features.evolution.engineering_roles import (
    ImplementerOutput,
    QAOutput,
    RoleOutputRejected,
    accept_implementer_output,
    accept_qa_output,
    implement,
    product_snapshot,
)
from backend.app.features.evolution.models import PatchFile
from backend.app.features.evolution.patch_boundary import PatchRejected
from backend.app.features.evolution.regression import CheckOutcome, RegressionReport
from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
from backend.app.shared.contracts import Improvement
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings

APP_JS = "frontend/src/features/integration/product/app.js"
IMPROVEMENT = Improvement(
    id=uuid4(), title="Explain schema errors", issue="Personas did not find the error cell",
    supporting_session_ids=[uuid4()], severity=3, affected_share=0.4, evidence_strength=1,
    estimated_effort_hours=1, acceptance_check="sourcetable-type-error-v1",
    allowed_paths=[APP_JS], status="reviewed")
REPORT = RegressionReport(
    base_commit="a" * 40, patch_sha256="b" * 64, fixed_checks_sha256="c" * 64,
    checks_unchanged=True, passed=False, results=[CheckOutcome(
        check_id="product-ui", kind="ui", passed=False, exit_code=1, duration_ms=5,
        output_tail="Sample columns did not render")])


def test_implementer_output_must_answer_its_improvement_inside_scope():
    files = [PatchFile(path=APP_JS, content="ready();\n")]
    output = ImplementerOutput(improvement_id=IMPROVEMENT.id, summary="Label errors", files=files)
    assert len(accept_implementer_output(IMPROVEMENT, output)) == 64
    with pytest.raises(RoleOutputRejected, match="different improvement"):
        accept_implementer_output(IMPROVEMENT, output.model_copy(update={"improvement_id": uuid4()}))
    with pytest.raises(PatchRejected, match="fixed check"):
        accept_implementer_output(IMPROVEMENT, output.model_copy(update={"files": [PatchFile(
            path="backend/app/features/integration/product/checks.py", content="")]}))


def test_qa_cannot_approve_a_failed_regression_or_review_another_patch():
    with pytest.raises(RoleOutputRejected, match="regression failed"):
        accept_qa_output(REPORT, QAOutput(patch_sha256="b" * 64, findings=[],
                                          recommendation="approve"))
    with pytest.raises(RoleOutputRejected, match="different patch"):
        accept_qa_output(REPORT, QAOutput(patch_sha256="d" * 64, findings=[],
                                          recommendation="reject"))
    assert accept_qa_output(REPORT, QAOutput(patch_sha256="b" * 64, findings=[],
                                             recommendation="reject")).recommendation == "reject"
    # The schema gives QA no way to return files or edited checks.
    assert set(QAOutput.model_fields) == {"patch_sha256", "findings", "recommendation"}


async def test_implementer_runs_only_live_on_reviewed_evidence():
    checks = ProductHandoff.model_validate_json(MANIFEST.read_text()).checks
    fixture = HuggingFaceInference(Settings(_env_file=None, app_mode="fixture"))
    with pytest.raises(InferenceError, match="FIXTURE_INFERENCE_FORBIDDEN"):
        await implement(fixture, IMPROVEMENT, {APP_JS: "ready();\n"}, checks)
    unconfigured = HuggingFaceInference(Settings(_env_file=None, app_mode="live"))
    with pytest.raises(InferenceError, match="INFERENCE_NOT_CONFIGURED"):
        await implement(unconfigured, IMPROVEMENT, {APP_JS: "ready();\n"}, checks)
    for update in ({"status": "proposed"}, {"supporting_session_ids": []}):
        with pytest.raises(RoleOutputRejected, match="human-reviewed"):
            await implement(fixture, IMPROVEMENT.model_copy(update=update), {}, checks)


def test_snapshot_contains_only_the_approved_files(tmp_path):
    (tmp_path / APP_JS).parent.mkdir(parents=True)
    (tmp_path / APP_JS).write_text("ready();\n")
    (tmp_path / APP_JS).with_name("style.css").write_text("body{}\n")
    assert product_snapshot(tmp_path, [APP_JS]) == {APP_JS: "ready();\n"}
    with pytest.raises(PatchRejected):
        product_snapshot(tmp_path, ["backend/app/features/evolution/"])
