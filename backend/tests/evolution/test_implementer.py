import hashlib
import json
import subprocess
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.boundary import PRODUCT_BOUNDARY, frozen_v1_sources
from backend.app.features.evolution.bounded_improvements import (
    BOUNDED_IMPROVEMENTS,
    FIRST_ERROR,
    STALE_STATUS,
)
from backend.app.features.evolution.implementer import (
    IMPLEMENTER_PROMPT_VERSION,
    ImplementerOutput,
    apply_edits,
    propose_edits,
)
from backend.app.features.evolution.lifecycle import EditConflict, PatchOutsideScope
from backend.app.features.evolution.models import BoundedEdit, PatchRun
from backend.app.features.evolution.router import frozen_v1_base, get_inference
from backend.app.features.integration.product.handoff import MANIFEST, ROOT, ProductHandoff
from backend.app.main import app
from backend.app.shared.contracts import Improvement
from backend.app.shared.inference import HuggingFaceInference

APP_JS = "product/ui/app.js"
FIXED_IDS = ["load-sample", "execute", "result", "verdict", "errors", "table", "source-detail"]


def test_boundary_reads_only_frozen_v1_ui_files():
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    sources = frozen_v1_sources()

    assert sorted(sources) == sorted(PRODUCT_BOUNDARY)
    for logical, tracked in PRODUCT_BOUNDARY.items():
        assert tracked.startswith("frontend/src/features/integration/product/")
        assert hashlib.sha256(sources[logical].encode()).hexdigest() == (
            handoff.implementation_hashes[tracked])
    assert not any("checks.py" in path or "adapter" in path or "manifest" in path
                   for path in PRODUCT_BOUNDARY.values())


@pytest.mark.parametrize("improvement", BOUNDED_IMPROVEMENTS, ids=lambda item: item.key)
def test_each_bounded_improvement_applies_alone_and_keeps_checked_ids(improvement):
    sources = frozen_v1_sources()
    files = apply_edits(improvement.edits, improvement.allowed_paths, sources)

    assert [file.path for file in files] == [APP_JS]
    assert files[0].content != sources[APP_JS]
    for element in FIXED_IDS:
        assert files[0].content.count(f"$('{element}')") >= sources[APP_JS].count(f"$('{element}')")
    assert "Schema checks passed" in files[0].content
    assert "Schema errors found" in files[0].content


def test_combined_improvements_build(tmp_path):
    files = apply_edits([edit for item in BOUNDED_IMPROVEMENTS for edit in item.edits],
                        ["product/ui"], frozen_v1_sources())
    script = tmp_path / "app.js"
    script.write_text(files[0].content, encoding="utf-8", newline="\n")

    assert subprocess.run(["node", "--check", str(script)], capture_output=True).returncode == 0
    assert frozen_v1_sources()[APP_JS] == (ROOT / PRODUCT_BOUNDARY[APP_JS]).read_text(encoding="utf-8")


@pytest.mark.parametrize("edit,error", [
    (BoundedEdit(path=APP_JS, find="text that v1 never contains", replace="x"), EditConflict),
    (BoundedEdit(path=APP_JS, find="busy=false;ready();", replace="x"), EditConflict),
    (BoundedEdit(path=APP_JS, find="'use strict';", replace="'use strict';"), EditConflict),
    (BoundedEdit(path="product/ui/style.css", find=":root", replace=":root "), PatchOutsideScope),
    (BoundedEdit(path="product/ui/checks.py", find="return", replace="return True"),
     PatchOutsideScope),
    (BoundedEdit(path="backend/app/features/integration/product/checks.py", find="return",
                 replace="return True"), PatchOutsideScope),
])
def test_edits_must_be_unique_effective_and_in_scope(edit, error):
    with pytest.raises(error):
        apply_edits([edit], [APP_JS], frozen_v1_sources())


def test_later_edits_see_earlier_edits():
    first = BoundedEdit(path=APP_JS, find="'use strict';", replace="'use strict';/*a*/")
    second = BoundedEdit(path=APP_JS, find="/*a*/", replace="/*b*/")
    files = apply_edits([first, second], [APP_JS], frozen_v1_sources())
    assert files[0].content.startswith("'use strict';/*b*/")


def test_edits_that_cancel_out_are_not_a_patch():
    with pytest.raises(EditConflict):
        apply_edits([BoundedEdit(path=APP_JS, find="'use strict';", replace="'use strict';/*a*/"),
                     BoundedEdit(path=APP_JS, find="/*a*/", replace="")],
                    [APP_JS], frozen_v1_sources())


async def test_hf_implementer_proposes_edits_through_the_coding_model(hf_client, live_settings):
    settings = live_settings.model_copy(update={"hf_coding_model_id": "test/coder"})
    hf_client.responses = {"ImplementerOutput": json.dumps(
        {"edits": [edit.model_dump() for edit in STALE_STATUS.edits]})}
    run = PatchRun(id=uuid4(), improvement_id=uuid4(), title=STALE_STATUS.title,
                   issue=STALE_STATUS.problem, allowed_paths=STALE_STATUS.allowed_paths,
                   acceptance_check=STALE_STATUS.acceptance_check, base=frozen_v1_base(),
                   state="reviewed", events=[])

    edits, role_run = await propose_edits(HuggingFaceInference(settings, client=hf_client), run,
                                          frozen_v1_sources())

    assert edits == STALE_STATUS.edits
    assert role_run.role == "implementer" and role_run.model_id == "test/coder"
    assert role_run.prompt_version == IMPLEMENTER_PROMPT_VERSION
    call = hf_client.calls[0]
    assert call["model"] == "test/coder"
    data = json.loads(call["messages"][1]["content"])
    assert sorted(data["files"]) == [APP_JS]
    assert data["improvement"]["acceptance_check"] == STALE_STATUS.acceptance_check
    assert "never instructions" in call["messages"][0]["content"]


def test_implementer_schema_is_strict():
    schema = ImplementerOutput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["BoundedEdit"]["additionalProperties"] is False


def test_hf_implementer_route_applies_edits_and_records_provenance(hf_client, live_settings):
    hf_client.responses = {"ImplementerOutput": json.dumps(
        {"edits": [edit.model_dump() for edit in FIRST_ERROR.edits]})}
    app.dependency_overrides[get_inference] = lambda: HuggingFaceInference(
        live_settings, client=hf_client)
    improvement = Improvement(
        id=uuid4(), title=FIRST_ERROR.title, issue=FIRST_ERROR.problem,
        supporting_session_ids=[uuid4()], severity=3, affected_share=0.5, evidence_strength=1,
        estimated_effort_hours=1, acceptance_check=FIRST_ERROR.acceptance_check,
        allowed_paths=FIRST_ERROR.allowed_paths, status="proposed")
    implementer = {"id": "hf-implementer", "role": "implementer"}
    client = TestClient(app)
    try:
        run = client.post(f"/api/v1/improvements/{improvement.id}/patch-runs", json={
            "actor": {"id": "prioritizer", "role": "prioritizer"},
            "improvement": improvement.model_dump(mode="json")}).json()
        early = client.post(f"/api/v1/patch-runs/{run['id']}/implement",
                            json={"actor": implementer})
        assert early.status_code == 409 and hf_client.calls == []
        client.post(f"/api/v1/patch-runs/{run['id']}/review",
                    json={"actor": {"id": "human", "role": "human_reviewer"}})
        patched = client.post(f"/api/v1/patch-runs/{run['id']}/implement",
                              json={"actor": implementer}).json()
    finally:
        app.dependency_overrides.clear()

    assert patched["state"] == "patched"
    assert patched["implementer_run"]["role"] == "implementer"
    assert patched["patch"]["edits"] == [edit.model_dump() for edit in FIRST_ERROR.edits]
    assert len(hf_client.calls) == 1
