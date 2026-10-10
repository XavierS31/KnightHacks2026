"""QA role checks. Offline cases need Node.js only; real cases need Docker and Chromium.

Set C_PATCH_TESTS=1 and C_PATCH_IMAGE_ID to a locally built SourceTable runtime image.
A local rebuild is not the frozen v1 image; the evidence says so.
"""

import json
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from backend.app.features.evolution.boundary import PRODUCT_BOUNDARY, frozen_v1_sources
from backend.app.features.evolution.bounded_improvements import (
    BOUNDED_IMPROVEMENTS,
    BUSY_BUTTON,
    BUSY_LABEL,
    FIRST_ERROR,
    RERUN_STATUS,
    STALE_STATUS,
)
from backend.app.features.evolution.implementer import apply_edits
from backend.app.features.evolution.models import BoundedEdit, IsolatedPatch, PatchFile
from backend.app.features.evolution.qa import (
    QaUnavailable,
    frozen_image_id,
    run_regression,
    serve_patch,
)
from backend.app.features.evolution.router import frozen_v1_base, get_qa_image
from backend.app.features.integration.product.handoff import MANIFEST, ROOT, ProductHandoff
from backend.app.main import app
from backend.app.shared.contracts import Improvement

APP_JS = "product/ui/app.js"
MISSING_IMAGE = "sha256:" + "0" * 64
IMAGE = os.environ.get("C_PATCH_IMAGE_ID", "")
real = pytest.mark.skipif(os.environ.get("C_PATCH_TESTS") != "1" or not IMAGE,
                          reason="Set C_PATCH_TESTS=1 and C_PATCH_IMAGE_ID for Docker/Chromium QA")


async def test_build_failure_fails_every_fixed_check_and_keeps_v1():
    before = frozen_v1_sources()
    broken = apply_edits([BoundedEdit(path=APP_JS, find="'use strict';", replace="'use strict';{")],
                         [APP_JS], before)

    results = await run_regression(frozen_v1_base(), IsolatedPatch(files=broken, sha256="0" * 64),
                                   MISSING_IMAGE)

    assert [result.check_id for result in results] == frozen_v1_base().fixed_check_ids
    assert not any(result.passed for result in results)
    assert all(result.evidence.startswith("build: node --check app.js failed") for result in results)
    assert frozen_v1_sources() == before


async def test_unavailable_runtime_records_nothing():
    files = apply_edits(STALE_STATUS.edits, STALE_STATUS.allowed_paths, frozen_v1_sources())
    with pytest.raises(QaUnavailable, match="real adapter did not run"):
        await run_regression(frozen_v1_base(), IsolatedPatch(files=files, sha256="0" * 64),
                             MISSING_IMAGE)


async def test_changed_check_catalog_or_unknown_file_cannot_be_checked():
    patch = IsolatedPatch(files=[PatchFile(path=APP_JS, content="'use strict';")], sha256="0" * 64)
    with pytest.raises(QaUnavailable, match="check catalog"):
        await run_regression(frozen_v1_base().model_copy(update={"fixed_checks_sha256": "a" * 64}),
                             patch, MISSING_IMAGE)
    with pytest.raises(QaUnavailable, match="check catalog"):
        await run_regression(frozen_v1_base().model_copy(update={"fixed_check_ids": ["weaker"]}),
                             patch, MISSING_IMAGE)
    outside = IsolatedPatch(files=[PatchFile(path="product/ui/checks.py", content="")],
                            sha256="0" * 64)
    with pytest.raises(QaUnavailable, match="outside the product boundary"):
        await run_regression(frozen_v1_base(), outside, MISSING_IMAGE)


def test_qa_requires_the_frozen_v1_image(tmp_path):
    with pytest.raises(QaUnavailable, match="not configured"):
        frozen_image_id(tmp_path)
    record = tmp_path / "integration-product-runtime.json"
    record.write_text(json.dumps({"image_id": "sha256:" + "d" * 64}))
    with pytest.raises(QaUnavailable, match="not the frozen v1 image"):
        frozen_image_id(tmp_path)
    frozen = ProductHandoff.model_validate_json(MANIFEST.read_text()).image_id
    record.write_text(json.dumps({"image_id": frozen}))
    assert frozen_image_id(tmp_path) == frozen


async def test_preview_serves_patched_ui_over_unchanged_api_and_checks_origin():
    files = apply_edits(STALE_STATUS.edits, STALE_STATUS.allowed_paths, frozen_v1_sources())
    async with serve_patch(IsolatedPatch(files=files, sha256="0" * 64), MISSING_IMAGE) as origin:
        async with httpx.AsyncClient(base_url=origin, trust_env=False) as client:
            script = await client.get("/assets/app.js")
            page = await client.get("/")
            sample = await client.get("/api/v1/sample")
            hidden = await client.get("/assets/checks.py")
            foreign = await client.post("/api/v1/execute", json=sample.json(),
                                        headers={"origin": "http://127.0.0.1:8001"})
            own = await client.post("/api/v1/execute", json=sample.json(),
                                    headers={"origin": origin})

    assert RERUN_STATUS in script.text
    assert page.text == (ROOT / PRODUCT_BOUNDARY["product/ui/index.html"]).read_text()
    assert sample.json()["columns"][0]["name"] == "Item"
    assert hidden.status_code == 404
    assert foreign.status_code == 403
    # A's API ran the request under its own origin; the missing image fails at execution.
    assert own.status_code == 422
    assert own.json()["detail"]["code"] in {"SOURCE_PROCESS_FAILED", "DOCKER_UNAVAILABLE"}


@real
@pytest.mark.parametrize("improvement", BOUNDED_IMPROVEMENTS, ids=lambda item: item.key)
async def test_each_improvement_alone_passes_fixed_checks(improvement):
    files = apply_edits(improvement.edits, improvement.allowed_paths, frozen_v1_sources())
    results = await run_regression(frozen_v1_base(), IsolatedPatch(files=files, sha256="0" * 64),
                                   IMAGE)

    assert [result.check_id for result in results] == frozen_v1_base().fixed_check_ids
    assert all(result.passed for result in results), [result.evidence for result in results]
    assert all("not the frozen v1 image" in result.evidence for result in results)


@real
async def test_regressing_patch_fails_its_fixed_check():
    shifted = apply_edits([BoundedEdit(path=APP_JS, find="td.dataset.row=r+2;",
                                       replace="td.dataset.row=r+1;")], [APP_JS],
                          frozen_v1_sources())
    results = await run_regression(frozen_v1_base(), IsolatedPatch(files=shifted, sha256="0" * 64),
                                   IMAGE)

    outcome = {result.check_id: result.passed for result in results}
    assert outcome["sourcetable-normal-v1"] is False
    assert outcome["sourcetable-recovery-v1"] is True


@real
async def test_stale_status_acceptance():
    files = apply_edits(STALE_STATUS.edits, STALE_STATUS.allowed_paths, frozen_v1_sources())
    async with serve_patch(IsolatedPatch(files=files, sha256="0" * 64), IMAGE) as origin:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.goto(origin + "/")
            await page.click("#load-sample")
            await page.wait_for_function("() => !document.querySelector('#execute').disabled")
            await page.click("#execute")
            await page.wait_for_selector("#result", state="visible")
            await page.select_option('[aria-label="Column 1 type"]', "integer")
            status = await page.text_content("#status")
            hidden = await page.is_hidden("#result")
            await browser.close()

    assert status == RERUN_STATUS and hidden


@real
async def test_first_error_acceptance():
    files = apply_edits(FIRST_ERROR.edits, FIRST_ERROR.allowed_paths, frozen_v1_sources())
    async with serve_patch(IsolatedPatch(files=files, sha256="0" * 64), IMAGE) as origin:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.goto(origin + "/")
            await page.click("#load-sample")
            await page.wait_for_function("() => !document.querySelector('#execute').disabled")
            await page.select_option('[aria-label="Column 1 type"]', "integer")
            await page.click("#execute")
            await page.wait_for_selector("#result", state="visible")
            selected = await page.text_content("td.selected")
            cell = await page.get_attribute("td.selected", "data-row"), await page.get_attribute(
                "td.selected", "data-column")
            detail = await page.text_content("#source-detail")
            await browser.close()

    assert (selected, cell) == ("Apples", ("2", "1"))
    assert detail.startswith("Page 1")


@real
async def test_busy_button_acceptance():
    files = apply_edits(BUSY_BUTTON.edits, BUSY_BUTTON.allowed_paths, frozen_v1_sources())
    async with serve_patch(IsolatedPatch(files=files, sha256="0" * 64), IMAGE) as origin:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            held = []

            async def hold(route):
                held.append(route)

            await page.route("**/api/v1/execute", hold)
            await page.goto(origin + "/")
            await page.click("#load-sample")
            await page.wait_for_function("() => !document.querySelector('#execute').disabled")
            await page.click("#execute")
            await page.wait_for_function("() => document.querySelector('#execute').ariaBusy")
            during = (await page.text_content("#execute"),
                      await page.get_attribute("#execute", "aria-busy"))
            await held[0].continue_()
            await page.wait_for_selector("#result", state="visible")
            after = (await page.text_content("#execute"),
                     await page.get_attribute("#execute", "aria-busy"))
            await browser.close()

    assert during == (BUSY_LABEL, "true")
    assert after == ("Extract & validate", None)


@real
def test_three_improvements_become_one_human_approved_v2_and_failure_keeps_v1():
    before = frozen_v1_sources()
    app.dependency_overrides[get_qa_image] = lambda: IMAGE
    client = TestClient(app)
    human = {"id": "human-reviewer", "role": "human_reviewer"}
    qa = {"id": "qa-runner", "role": "qa_reviewer"}
    implementer = {"id": "implementer", "role": "implementer"}
    try:
        passed = []
        for improvement in BOUNDED_IMPROVEMENTS:
            record = Improvement(
                id=uuid4(), title=improvement.title, issue=improvement.problem,
                supporting_session_ids=[uuid4()], severity=3, affected_share=0.5,
                evidence_strength=1, estimated_effort_hours=1,
                acceptance_check=improvement.acceptance_check,
                allowed_paths=improvement.allowed_paths, status="proposed")
            run = client.post(f"/api/v1/improvements/{record.id}/patch-runs", json={
                "actor": {"id": "prioritizer", "role": "prioritizer"},
                "improvement": record.model_dump(mode="json")}).json()
            client.post(f"/api/v1/patch-runs/{run['id']}/review", json={"actor": human})
            client.post(f"/api/v1/patch-runs/{run['id']}/edits", json={
                "actor": implementer, "edits": [edit.model_dump() for edit in improvement.edits]})
            checked = client.post(f"/api/v1/patch-runs/{run['id']}/qa", json={"actor": qa}).json()
            assert checked["state"] == "regression_passed", checked
            passed.append(run["id"])

        failing = Improvement(
            id=uuid4(), title="Shift rows", issue="Deliberate regression",
            supporting_session_ids=[uuid4()], severity=1, affected_share=0.1, evidence_strength=1,
            estimated_effort_hours=1, acceptance_check="None", allowed_paths=[APP_JS],
            status="proposed")
        bad = client.post(f"/api/v1/improvements/{failing.id}/patch-runs", json={
            "actor": {"id": "prioritizer", "role": "prioritizer"},
            "improvement": failing.model_dump(mode="json")}).json()
        client.post(f"/api/v1/patch-runs/{bad['id']}/review", json={"actor": human})
        client.post(f"/api/v1/patch-runs/{bad['id']}/edits", json={"actor": implementer, "edits": [
            {"path": APP_JS, "find": "td.dataset.row=r+2;", "replace": "td.dataset.row=r+1;"}]})
        failed = client.post(f"/api/v1/patch-runs/{bad['id']}/qa", json={"actor": qa}).json()
        assert failed["state"] == "regression_failed"
        assert client.post(f"/api/v1/patch-runs/{bad['id']}/approve",
                           json={"actor": human}).status_code == 409
        assert frozen_v1_sources() == before

        release = client.post("/api/v1/releases", json={"actor": human, "run_ids": passed}).json()
        assert release["state"] == "reviewed"
        early = client.post(f"/api/v1/patch-runs/{release['id']}/approve", json={"actor": human})
        assert early.status_code == 409
        own_release = client.post(f"/api/v1/patch-runs/{release['id']}/compose",
                                  json={"actor": {"id": human["id"], "role": "implementer"}})
        assert own_release.status_code == 403
        composed = client.post(f"/api/v1/patch-runs/{release['id']}/compose",
                               json={"actor": {"id": "release-implementer",
                                               "role": "implementer"}}).json()
        assert len(composed["patch"]["edits"]) == 4
        checked = client.post(f"/api/v1/patch-runs/{release['id']}/qa", json={"actor": qa}).json()
        assert checked["state"] == "regression_passed", checked["regression"]
        self_promotion = client.post(f"/api/v1/patch-runs/{release['id']}/approve",
                                     json={"actor": {"id": "implementer", "role": "human_reviewer"}})
        assert self_promotion.status_code == 403
        approved = client.post(f"/api/v1/patch-runs/{release['id']}/approve",
                               json={"actor": human, "note": "Reviewed diff and check evidence."})
        candidate = approved.json()["candidate"]
        assert candidate["base_version_id"] == release["base"]["version_id"]
        assert candidate["patch_sha256"] == composed["patch"]["sha256"]
        rolled_back = client.post(f"/api/v1/patch-runs/{release['id']}/rollback",
                                  json={"actor": human}).json()
        assert rolled_back["state"] == "rolled_back"
    finally:
        app.dependency_overrides.clear()
    assert frozen_v1_sources() == before
