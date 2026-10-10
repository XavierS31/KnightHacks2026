# A → B/C: SourceTable v1

Implementation commit: `d120f429a2fdb27c43c0b88dfb29cd5c5ca1ee42`. The tracked [v1 manifest](../../backend/app/features/integration/product/v1/manifest.json) contains the immutable version/capability identities, schemas, initial state, image ID, source pins, fingerprints and check templates. Product startup and validation: [README](../../backend/app/features/integration/product/README.md).

Product URL on the validated demo computer: `http://127.0.0.1:8001`. Handoff JSON: `/api/v1/handoff`. These loopback addresses require a local process on the executing machine; they are not publicly deployed services. Manifest compatibility is separately available at the dashboard API `/api/v1/integration/product-readiness`.

## Validated operation

One machine-generated ruled PDF → detected table strings → Frictionless validation with the supplied column names/types/required flags → rows/errors with source page/table/cell identity and PDF boxes → display-safe CSV. Source repositories are pdfplumber and frictionless-py at the exact commits in the manifest. Python 3.12/Linux arm64 source execution and the separate-origin UI passed fixed checks.

No OCR, free-form event inference, arbitrary URL fetches, automatic column inference, guarantee of faithful transcription, financial correctness, or claim of unique market demand is included. The CSV derivative prefixes formula-like text; the original extracted string and schema-validation input remain unchanged. Missing cells use empty-string/missing-value semantics. Units are PDF points with top-origin geometry; CSV/source row 1 is the header.

## B consumption

Use the three frozen templates: normal extraction plus source inspection; intentional Item integer error plus source inspection; recovery to Item string. Each starts from the public `sample-inventory-v1` input. Navigation to a freshly loaded product page resets browser state, then Load sample PDF installs that exact sample. The budgets include navigation and a final check; B supplies task/scenario/persona IDs according to the canonical Task contract.

`backend/app/features/integration/product/checks.py` supplies a rendered-DOM observation script and deterministic evaluator. It requires exact known rows plus the expected selected source cell for the normal/error checks. It does not read an internal JavaScript output object, generate browser actions or create saved outcomes. B must whitelist the product origin, use fresh contexts, record actual bounded actions/screenshots/checks, and distinguish model/infrastructure failures from application failures.

A’s actual browser verification covered normal/error/source mapping/recovery, two independent contexts, reload reset and no horizontal overflow at 390px. All 220 backend tests passed with explicit real Docker/Chromium checks enabled; lint, generated types, typecheck and build passed. This is no evidence that a persona has completed a trial or that a real review-grounded population exists. All 500+500 experiment counters remain unexecuted by A.

## C persistence dependency

Persist candidate/source snapshots and interpretations/proposals from I1, then this immutable product manifest/check/initial-state catalog with version identities, source commits, schema/fingerprint references and artifact metadata. The existing discovery/extraction APIs retain records only in memory; the product executor itself is stateless. C owns database/migrations/job storage. No Neon credentials/connection are configured on this A machine, and A has not changed C’s implementation or migrations.

Maintain immutable v1 identity and task/check references before later patches/retests. Modified product fingerprints must invalidate v1 readiness. Product v2 promotion still needs human review. Pin the v1 implementation commit/image when starting B’s matched experiment; do not silently run a changed working copy under the same version ID.

The current manifest freezes the validated computer's local image identity. Rebuilding on another architecture or changing dependencies requires independent environment validation; it cannot inherit the original image’s proof. Source MIT license notices were found in both installed distributions. Complete dependency-wide licensing review and broader PDF coverage remain open.

## Budget boundary

This adapter and its validation make no HF calls. The earlier discovery/proposal ledger reserves $0.92 against A’s approved $2 allowance; that is reserved capacity, not billed spend. The user permits increasing A’s allowance if needed, but no increase or additional calls were necessary here. B must separately forecast/enforce population/trial use; A’s approval does not launch the paid full experiment.

## Prepared version repository

A’s `backend/app/features/integration/version_repository.py` consumes C’s existing `product_versions` table and pooled `NeonDatabase` helper. It stores only validated live handoffs, uses bound SQL/JSONB values and short statement/lock timeouts, performs idempotent inserts, and rejects any attempt to rewrite a frozen identity. Reads reject fixture records and header/manifest disagreements. It creates no tables, changes no migration, and makes no connection at import.

Once C has configured the intended Neon database and applied its reviewed schema, explicitly run:

```sh
.venv/bin/python -m backend.app.features.integration.version_repository --live
```

The command requires `APP_MODE=live` and a server-side `DATABASE_URL`; it then saves the locally verified v1 and reads back exact equality. It refuses fixture/missing configuration before any request. Current checks: eight offline repository cases plus real roundtrip/idempotency/conflict/concurrent-save checks against a disposable local PostgreSQL 17.11 instance. That local test is not Neon connection evidence. The test container was removed afterward. Candidate/source/proposal persistence still requires C’s feature-table/storage contract.

Additional product verification used a different uploaded PDF with City/People/date headers and Paris/Rome rows. Both the real adapter and upload UI returned the expected values; the real-Docker regression covers this alternate input, including date validation. This did not change frozen v1 implementation bytes or use HF credits.
