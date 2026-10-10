# Developer C kickoff — feedback and improvement

Use `developer_c_evolution` and `$repofusion-evolution`. Read root AGENTS.md, ownership, architecture, API/data/runtime contracts and roadmap. Inspect current files before selecting the first unfinished task.

## Boundaries and inputs

Own both `features/evolution` modules, `backend/tests/evolution/**`, shared `database.py`, `backend/migrations/**` and CI workflows. Coordinate canonical contracts with A and inference with B. Do not edit integration/personas or their fixtures without coordination. Inputs are canonical feedback/actions/session outcomes and explicit fixtures; outputs are evidence-linked clusters/improvements/review states/comparison.

Coordinate B's required [review-informed software behavior](../software-behavior.md): add ordered corpus/review/immutable-persona storage when implementing persistence. External reviews are upstream preference context, not generated-product defect evidence. Freeze behavior/corpus/generation versions for the matched comparison. The schema addition does not imply these tables or real collection already exist.

## First three tasks

1. **Persistence foundation:** establish a secret-safe pooled Postgres boundary, ordered migration mechanism and durable record/job semantics. Build offline tests for absent configuration/transaction behavior and document the Neon write/read gate. Done: no external connection is claimed without an actual configured round trip; other modules can consume clear interfaces without storing screenshots in rows.
2. **Analysis vertical slice:** group feedback and separate relevance/product/infrastructure issues; rank bounded improvements and expose evidence in the UI. Use structured analyst/prioritizer/UX outputs through B's inference adapter where live, with explicit fixtures otherwise. Done: invalid/cross-session references are rejected, heuristic priority inputs are visible, and missing evidence does not become a supported proposal.
3. **Improvement lifecycle:** enforce proposed/reviewed/isolated patch/regression/human approval states. Preserve v1 and fixed checks; request B's matched v2 retest and compute denominators honestly. Done: disallowed patch paths fail, implementer cannot self-promote, regression failure blocks v2, and unmatched/missing outcomes remain visible.

## Dependencies and verification

Neon configuration and B's actual feedback are live gates; proceed with fixture-backed tests/UI while absent. Runtime roles use only the shared HF adapter. Product patches cross into A's approved generated-product boundary only after coordination. Human review is required before v2 promotion.

Run database/evolution tests plus frontend typecheck/build. CI runs offline pytest, generated-contract drift, typecheck and build without secrets or inference cost. Compare identical persona/behavior/corpus/scenario/task/check versions; do not interpret model time as human time.

## Q1 demo evidence (C slice)

`python -m backend.app.features.evolution.demo_evidence --out artifacts/evidence/c-slice.json` prints one JSON report. It is read-only. It never prints `DATABASE_URL`. Each check is `pass`, `fail` or `not_established`. The command exits 1 only when a check fails.

| Check | Mode | Pass condition |
| --- | --- | --- |
| `v1_source_preserved` | offline | A's frozen v1 manifest is `validated`, and every source fingerprint matches the working tree. |
| `fixture_analysis_labeled` | offline | Fixture analysis says `fixture`, uses no inference and creates no proposal or invented cluster. |
| `neon_usage` | live | The host is `*.neon.tech`, `schema_migrations` has rows, and Neon holds non-fixture sessions with actions. |
| `v1_registered` | live | The `product_versions` row for v1 has the frozen ID, commit and `validated` status. |
| `v2_registered` | live | An approved non-fixture v2 row exists, and the v1 row is still unchanged. |
| `replay_labeled` | live | Every stored session has a valid stream label, and only fixture rows say `fixture`. |

A local PostgreSQL is not Neon evidence: `neon_usage` fails on any other host. CI runs the command offline, so the live checks report `not_established`.

Rehearsal on the intended machine:

1. Run the checks in "Verify the scaffold" in the README.
2. Start the API and UI. Run `python -m backend.scripts.smoke_ui`. The Evolution view must show `fixture analysis` in fixture mode.
3. Stop and start the API again. Run the smoke again.
4. Put `APP_MODE=live` and the Neon `DATABASE_URL` in the git-ignored `.env`. Run the evidence command with `--out`. Record the statuses and row counts in `docs/status.md`. Do not commit the JSON file.

## Progress log

2026-10-10 starter complete: deterministic fixture analysis validates session/action/persona references, groups product/infrastructure/relevance feedback and exposes heuristic inputs. Empty known feedback returns no clusters; irrelevant outcomes remain relevance context even if barriers are supplied. The frontend can request the report; approval denies promotion with `409 REVIEW_REQUIRED`. Lazy `NeonDatabase` has mocked pool/transaction tests; `001_initial.sql` establishes initial provenance and job lease tables but is not applied. Twenty-four focused tests passed; combined schema/type/build checks passed. Live persistence, five HF engineering workflows, reviewed improvements and matched retest remain open. Next: authorized Neon round trip and real persisted feedback repository, then structured HF role analysis.

2026-10-10 E2 lifecycle (issue #12): `evolution/lifecycle.py` enforces proposed → reviewed → patched → regression → approved, plus rejected and rolled back. Only `proposed` improvements with session evidence can start. Each run copies A's frozen v1 identity and fixed check IDs/digest and never changes them. Patch files must sit inside the improvement's approved `product/` paths. Regression results must cover each fixed check once for the exact patch digest; any failure is terminal and blocks v2. A human reviewer approves; the implementer cannot review its scope, record its regression or promote its patch. Approval registers one active v2 candidate per base; rollback makes v1 active again. Records live in memory and actor identity is caller-asserted until authentication exists. Open: durable runs/v2 records after E1, real isolated patch execution and fixed-check runs against A's product.

2026-10-10 structured role analysis (E1, #11): in live mode, `POST /experiments/{id}/analysis` reads persisted sessions, actions and feedback from the 001 tables in one read-only snapshot. Then it runs the analyst, prioritizer and UX reviewer roles through B's shared HF adapter. Models see only F/A/C reference labels. Deterministic checks reject unknown, duplicate and cross-session references. They also reject findings that cross the product/infrastructure/relevance boundary that the session outcome sets, and proposals outside a product cluster's evidence. Affected share, evidence strength and the score are computed; severity and effort are prioritizer estimates, and the UI labels each source. A product cluster without action evidence for every member does not reach UX review. A draft without cited evidence is recorded as unsupported. Live mode refuses submitted sessions; fixture mode keeps the deterministic path. One request holds at most 30 feedback items. The row convention is in `repository.py`, and persistence writers must follow it. Verification: 73 evolution tests, which include the real-database cases against a disposable local TLS PostgreSQL through `TEST_DATABASE_URL`. HF responses came from a scripted provider client. No Neon request or paid inference ran. Open: persist analysis records and role provenance (#10), batch for the full population (P3), and run a first live HF analysis on real B feedback.

2026-10-10 Q1 C-slice validation (#15): `evolution/demo_evidence.py` reports the C demo slice as one read-only JSON report. The offline checks prove that the v1 sources match A's frozen manifest and that fixture analysis stays labeled and claims nothing. The live checks read one Neon snapshot: server, migration history, row counts, stored v1/v2 rows and session stream labels. CI now pins fixture mode and empty credentials, and it runs the offline report. `smoke_ui.py` had two stale Evolution steps; it now passes again and checks the `fixture analysis` label. Rehearsal on this development Mac: tests, lint, contract drift, typecheck, build and the desktop/mobile smoke passed, and the smoke passed again after an API restart. The live report ran against a disposable local TLS PostgreSQL; `neon_usage` correctly failed because the host is not Neon. Verification: 22 new tests (8 need `TEST_DATABASE_URL`); 437 passed with a local database and 425 passed without one. No mocks. No Neon request or HF inference ran. Open: run the live report against Neon after #9/#10, rehearse on the intended demo machine, and register v1/v2 rows when versions persist.
