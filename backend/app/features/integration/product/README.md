# SourceTable — A's real product v1

A narrow CPU-only integration of pinned pdfplumber and Frictionless. The separate product origin is `http://127.0.0.1:8001`. The dashboard remains at port 5173. This is local development; no public deployment or production authentication is provided.

## Build and run

From the repository root, with Docker running and the shared Python environment installed:

```sh
docker build --tag repofusion-a-product:v1 backend/app/features/integration/product/runtime
# Record the immutable image identity without editing shared settings.
.venv/bin/python -c "import json,subprocess; from pathlib import Path; from backend.app.shared.settings import Settings; p=Settings().artifact_root; p.mkdir(parents=True,exist_ok=True); image=subprocess.check_output(['docker','image','inspect','repofusion-a-product:v1','--format','{{.Id}}'],text=True).strip(); (p/'integration-product-runtime.json').write_text(json.dumps({'image_id':image}))"
.venv/bin/python -m uvicorn backend.app.features.integration.product.app:app --host 127.0.0.1 --port 8001
```

On this machine, source commits, archive hashes, base digest and dependency versions are pinned. The Dockerfile's Python base is a multi-platform digest; the validated environment is Linux arm64. Other platforms must run the independent and adapter checks. A rebuilt image can have a different identity and cannot inherit another machine's validation record.

## Operation

Load sample PDF or upload a machine-generated ruled PDF. Set column names in exact header order, choose string/integer/number/date and required values, then Extract & validate. Select a cell or error to inspect original text and top-origin PDF coordinates. Download CSV is a display-safe derivative; formula-like values have an apostrophe prefix. Validation uses the original strings, not the modified export.

Limits: 1 MB, three pages, exactly one table, 1–100 data rows, 12 columns, 500 characters per cell. Blank cells use Frictionless missing-value semantics. No OCR, arbitrary file paths, network fetches, semantic inference, or numerical/accounting correctness claim. Wider PDF coverage remains unmeasured.

Every operation gets a fresh nonroot Docker container, immutable image ID, no network/host mounts/log driver/capabilities, read-only root, one CPU, 256 MiB, 64 PIDs and 16 MiB temporary storage. Two requests may execute concurrently. Execution has a 15-second wall-clock deadline and bounded stdout; cancellation/timeout removes the container. Browser state and results are page-local; server state is not retained across operations. Reload resets the page.

## Validation and freeze

```sh
A_PRODUCT_TESTS=1 B_BROWSER_TESTS=1 .venv/bin/python -m pytest backend/tests
# Requires the implementation to be committed, then runs real fixed Docker checks.
.venv/bin/python -m backend.app.features.integration.product.freeze
```

The freeze command checks normal rows, wrong types with exact source mapping, required missing values, wrong headers, malformed PDF, no ruled table and real timeout cleanup. It freezes `v1/manifest.json` with implementation commit/fingerprints, image/source IDs, schemas, initial state, check catalog and limitations. It makes no HF requests and cannot promote v2. Preserve frozen v1 before editing the product. A changed implementation must not silently reuse its identity.

`GET /api/v1/handoff` on port 8001 returns the validated handoff only if local source fingerprints and configured image match. The dashboard's `GET /api/v1/integration/product-readiness` reports manifest compatibility, not service availability. `checks.py` exposes the rendered-DOM observation and deterministic evaluator for B; B must still record actual browser actions/screenshots/outcomes, assign task/scenario identities and persist through C. No persona experiment counters are incremented by A checks.

C owns durable evidence storage. This stateless product and tracked version manifest do not establish Neon persistence. Neither provider spend nor the 1,000-session experiment is started here. A's adapter uses no HF credits.
