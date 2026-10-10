import json
import subprocess
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.features.evolution.implementer import (
    IMPLEMENTER_PROMPT_VERSION,
    ImplementerOutput,
    apply_edits,
    propose_edits,
)
from backend.app.features.evolution.lifecycle import EditConflict, PatchOutsideScope
from backend.app.features.evolution.models import BoundedEdit, PatchRun
from backend.app.features.evolution.router import frozen_v1_base, get_inference
from backend.app.main import app
from backend.app.shared.contracts import Improvement
from backend.app.shared.inference import HuggingFaceInference
from backend.tests.prototype_fixtures import (
    BOUNDED_IMPROVEMENTS,
    FIRST_ERROR,
    SOURCES,
    STALE_STATUS,
)


def frozen_v1_sources():
    return dict(SOURCES)


APP_JS = "product/ui/app.js"
def test_synthetic_edits_build_without_changing_base(tmp_path):
    sources = frozen_v1_sources()
    files = apply_edits([edit for item in BOUNDED_IMPROVEMENTS for edit in item.edits], ['product/ui'], sources)
    script = tmp_path / 'app.js'
    script.write_text(files[0].content)
    assert subprocess.run(['node', '--check', str(script)], capture_output=True).returncode == 0
    assert sources == SOURCES


@pytest.mark.parametrize("edit,error", [
    (BoundedEdit(path=APP_JS, find="text that v1 never contains", replace="x"), EditConflict),
    (BoundedEdit(path=APP_JS, find="busy=false;ready();", replace="x"), EditConflict),
    (BoundedEdit(path=APP_JS, find="'use strict';", replace="'use strict';"), EditConflict),
    (BoundedEdit(path="product/ui/style.css", find=":root", replace=":root "), PatchOutsideScope),
    (BoundedEdit(path="product/ui/checks.py", find="return", replace="return True"),
     PatchOutsideScope),
    (BoundedEdit(path="product/checks.py", find="return",
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
