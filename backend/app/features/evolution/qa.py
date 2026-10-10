"""The QA role: run A's fixed v1 checks against a patch in an isolated workspace.

The workspace is a temporary copy of the frozen v1 UI files with the patch applied. The v1
tree is only read. Checks run in three stages:

1. Build: `node --check` parses the patched script.
2. Integration: the patched UI is served in front of A's unchanged product API and the real
   Docker adapter. A probe must extract the sample before any UI check runs.
3. UI: each fixed check runs in a fresh Chromium context with a fixed action procedure.
   A's rendered-DOM observation and evaluator decide the result.

A build failure fails every fixed check. If the infrastructure cannot run the checks,
`QaUnavailable` is raised and nothing is recorded, so a good patch is never failed for it.
The check catalog, procedures and evaluator sit outside the patchable boundary.
"""

import asyncio
import socket
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from backend.app.features.evolution.boundary import PRODUCT_BOUNDARY, frozen_v1_sources
from backend.app.features.evolution.lifecycle import fixed_checks_digest
from backend.app.features.evolution.models import BaseVersion, CheckResult, IsolatedPatch
from backend.app.features.integration.product.app import create_product
from backend.app.features.integration.product.checks import EXPECTED_ROWS, OBSERVE_SCRIPT, evaluate
from backend.app.features.integration.product.executor import (
    DockerExecutor,
    ExecutionError,
    configured_executor,
)
from backend.app.features.integration.product.handoff import MANIFEST, FixedCheck, ProductHandoff

# A's product accepts only its own origin. The workspace checks its own origin first.
PRODUCT_ORIGIN = b"http://127.0.0.1:8001"
STEP_TIMEOUT_MS = 20_000
ITEM_TYPE = '[aria-label="Column 1 type"]'
LOAD = [("navigate", "/", None), ("click", "#load-sample", None)]
EXECUTE = ("click", "#execute", None)
# One fixed procedure per frozen check. The final observation counts as one more action.
CHECK_STEPS = {
    "sourcetable-normal-v1": [
        *LOAD, EXECUTE, ("click", 'td[data-row="2"][data-column="2"] button', None)],
    "sourcetable-type-error-v1": [
        *LOAD, ("select", ITEM_TYPE, "integer"), EXECUTE, ("click", "#errors .error-item", None)],
    "sourcetable-recovery-v1": [
        *LOAD, ("select", ITEM_TYPE, "integer"), EXECUTE, ("select", ITEM_TYPE, "string"),
        EXECUTE],
}
SETTLED = "() => !document.querySelector('#load-sample').disabled"
SHOWN = ("() => !document.querySelector('#execute').disabled && "
         "(!document.querySelector('#result').hidden || !document.querySelector('#error').hidden)")


class QaUnavailable(RuntimeError):
    """The checks could not run. This is no evidence against the patch."""


def frozen_image_id(artifact_root: Path) -> str:
    """The configured product image, only when it is the image frozen in the v1 manifest."""
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    try:
        image_id = configured_executor(artifact_root).image_id
    except ExecutionError as failure:
        raise QaUnavailable(f"The product image is not configured: {failure.code}.") from None
    if image_id != handoff.image_id:
        raise QaUnavailable("The configured product image is not the frozen v1 image.")
    return image_id


def _fixed_checks(base: BaseVersion) -> list[FixedCheck]:
    checks = ProductHandoff.model_validate_json(MANIFEST.read_text()).checks
    if fixed_checks_digest([check.model_dump(mode="json") for check in checks]) != (
            base.fixed_checks_sha256) or [check.id for check in checks] != base.fixed_check_ids:
        raise QaUnavailable("The frozen check catalog differs from the run's base.")
    for check in checks:
        if check.id not in CHECK_STEPS or len(CHECK_STEPS[check.id]) + 1 > check.action_budget:
            raise QaUnavailable(f"No fixed procedure fits check {check.id}.")
    return checks


def _materialize(patch: IsolatedPatch, root: Path) -> Path:
    files = {**frozen_v1_sources(), **{item.path: item.content for item in patch.files}}
    if not files.keys() <= PRODUCT_BOUNDARY.keys():
        raise QaUnavailable("The patch names a file outside the product boundary.")
    for logical, text in files.items():
        target = root / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return root / "product/ui"


async def _build(ui: Path) -> tuple[bool, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            "node", "--check", str(ui / "app.js"),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise QaUnavailable("Node.js is required for the build check.") from None
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), 15)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise QaUnavailable("The build check timed out.") from None
    if process.returncode:
        lines = [line for line in stderr.decode(errors="replace").splitlines() if line.strip()]
        detail = next((line for line in lines if "Error" in line), lines[-1] if lines else "")
        return False, f"node --check app.js failed: {detail[:300]}"
    return True, "node --check app.js passed"


def _workspace_app(ui: Path, image_id: str, origin: str):
    shell = FastAPI()

    @shell.get("/")
    def index():
        return FileResponse(ui / "index.html")

    @shell.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "style.css"}:
            raise HTTPException(404)
        return FileResponse(ui / name)

    # A's unchanged API, size limits and error mapping serve everything else.
    shell.mount("/", create_product(DockerExecutor(image_id)))

    async def app(scope, receive, send):
        if scope["type"] == "http":
            sent = dict(scope["headers"]).get(b"origin")
            headers = [(key, value) for key, value in scope["headers"] if key != b"origin"]
            if sent is not None:
                if sent != origin.encode():
                    response = JSONResponse({"error": {"code": "ORIGIN_REJECTED"}}, status_code=403)
                    await response(scope, receive, send)
                    return
                headers.append((b"origin", PRODUCT_ORIGIN))
            scope = {**scope, "headers": headers}
        await shell(scope, receive, send)

    return app


@asynccontextmanager
async def _serve(ui: Path, image_id: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(
        _workspace_app(ui, image_id, origin), lifespan="off", log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.05)
        else:
            raise QaUnavailable("The isolated product server did not start.")
        yield origin
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)
        sock.close()


@asynccontextmanager
async def serve_patch(patch: IsolatedPatch, image_id: str):
    """Serve frozen v1 with the patch applied from a temporary workspace, for human preview."""
    with tempfile.TemporaryDirectory(prefix="repofusion-preview-") as directory:
        async with _serve(_materialize(patch, Path(directory)), image_id) as origin:
            yield origin


async def _integration_probe(origin: str, image_id: str) -> str:
    try:
        async with httpx.AsyncClient(base_url=origin, timeout=30, trust_env=False) as client:
            sample = (await client.get("/api/v1/sample")).json()
            response = await client.post("/api/v1/execute", json=sample,
                                         headers={"origin": origin})
    except (httpx.HTTPError, ValueError):
        raise QaUnavailable("The isolated product API did not answer.") from None
    if response.status_code != 200:
        body = response.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body.get("error", {})
        raise QaUnavailable(f"The real adapter did not run: {detail.get('code', response.status_code)}.")
    result = response.json()
    if result.get("status") != "valid" or result.get("rows") != EXPECTED_ROWS:
        raise QaUnavailable("The real adapter did not return the frozen sample rows.")
    frozen = ProductHandoff.model_validate_json(MANIFEST.read_text()).image_id
    identity = "frozen v1 image" if image_id == frozen else "not the frozen v1 image"
    return f"real adapter in {image_id[:19]} ({identity}) returned {len(result['rows'])} valid rows"


async def _perform(page, origin: str, kind: str, target: str, value: str | None) -> None:
    if kind == "navigate":
        await page.goto(origin + target)
    elif kind == "select":
        await page.locator(target).first.select_option(value)
    else:
        await page.locator(target).first.click()
    await page.wait_for_function(SHOWN if (kind, target) == EXECUTE[:2] else SETTLED)


async def _ui_check(browser, origin: str, check: FixedCheck) -> tuple[bool, str]:
    steps = CHECK_STEPS[check.id]

    async def same_origin_only(route):
        if route.request.url.startswith(origin + "/"):
            await route.continue_()
        else:
            await route.abort()

    context = await browser.new_context()
    try:
        await context.route("**/*", same_origin_only)
        page = await context.new_page()
        page.set_default_timeout(STEP_TIMEOUT_MS)
        for number, (kind, target, value) in enumerate(steps, start=1):
            try:
                await _perform(page, origin, kind, target, value)
            except PlaywrightError as failure:
                reason = str(failure).splitlines()[0][:200]
                return False, f"step {number} ({kind} {target}) failed: {reason}"
        try:
            observation = await page.evaluate(OBSERVE_SCRIPT)
        except PlaywrightError as failure:
            return False, f"observation failed: {str(failure).splitlines()[0][:200]}"
    finally:
        await context.close()
    passed = evaluate(check.id, observation)
    return passed, (f"{len(steps) + 1}/{check.action_budget} actions; verdict "
                    f"'{observation.get('verdict')}', {observation.get('error_count')} errors, "
                    f"selected {observation.get('selected')}")


async def run_regression(base: BaseVersion, patch: IsolatedPatch, image_id: str) -> list[CheckResult]:
    """One result per fixed check. Raises QaUnavailable when the checks cannot run."""
    checks = _fixed_checks(base)
    with tempfile.TemporaryDirectory(prefix="repofusion-qa-") as directory:
        ui = _materialize(patch, Path(directory))
        built, build_note = await _build(ui)
        if not built:
            results = [CheckResult(check_id=check.id, passed=False,
                                   evidence=f"build: {build_note}") for check in checks]
        else:
            async with _serve(ui, image_id) as origin:
                integration = await _integration_probe(origin, image_id)
                try:
                    async with async_playwright() as playwright:
                        browser = await playwright.chromium.launch()
                        try:
                            outcomes = [await _ui_check(browser, origin, check) for check in checks]
                        finally:
                            await browser.close()
                except PlaywrightError as failure:
                    raise QaUnavailable(f"Chromium could not run: {str(failure)[:200]}") from None
            results = [CheckResult(
                check_id=check.id, passed=passed,
                evidence=f"build: {build_note}; integration: {integration}; ui: {note}"[:2000])
                for check, (passed, note) in zip(checks, outcomes, strict=True)]
    frozen_v1_sources()  # Raises BoundaryDrift if v1 changed while the checks ran.
    return results
