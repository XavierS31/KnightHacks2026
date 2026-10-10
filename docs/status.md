# Implementation status

Status dated 2026-10-10. Update this file with evidence after each milestone; do not infer production completion from fixture counts.

Current B runtime update: bounded corpus/population/approval, single-process spend accounting,
executor/HF policy and exact captured-frame mock viewer are implemented. Authenticated HF smoke
passed; two real public reviews were collected. Independent review rejected the first extraction,
and a fresh request failed; zero live personas/trials and no Neon persistence. Full changes,
accounting and dependency-ordered remaining work: [B runtime report](tasks/developer-b-runtime-report.md).

| Area | Current status | Evidence required to advance |
| --- | --- | --- |
| Skeleton and shared contracts | Runnable fixture scaffold; offline tests, generated contracts, typecheck/build and desktop/mobile browser smoke verified | Replace fixtures at real execution gates |
| Three developer starter slices | A discovery, B exact-session viewer/inference boundary, C grounded analysis/database helper implemented and checked | Production milestones in each starter task |
| Developer roles and project skills | Repository-local instructions prepared | Valid TOML/YAML, scoped paths and kickoff review |
| Live repository integration | SourceTable v1: pinned pdfplumber/Frictionless adapter passed fixed normal/error/compatibility/timeout checks and real browser flow | Broader PDF coverage, portable environment verification and C durable storage |
| Hosted HF inference | A authenticated Qwen/Qwen3-32B through DeepInfra; 26 cited repository interpretations and five proposal hypotheses retained locally | Complete role-output support review; B/C flows and experiment accounting remain separate |
| Review-informed persona behavior | Required schema, citation/provenance validation, fixture examples and viewer implemented; real ingestion/extraction not established | B collects relevant real software reviews, verifies HF extraction support and persists immutable source-linked population profiles with C |
| Neon persistence | Migration runner, write/read/rollback gate, session/action/feedback and analysis repositories and the job claim/lease queue verified on local TLS PostgreSQL; Neon connection not established | Run the gate in `backend/migrations/README.md` against Neon, then the repository and job tests with `TEST_DATABASE_URL` on a Neon branch, and record the output |
| Persona browser execution | Production path not established | Real Playwright task and retained action/output evidence |
| Hosted HF inference | A authenticated Qwen3-32B/DeepInfra with 26 repository interpretations and five hypotheses; B's configuration smoke validated, behavior extraction quality/reliability unresolved | Independent role-output support review; representative B/C roles, durable experiment accounting and measured pilots |
| Review-informed persona behavior | Bounded corpus/approval/population foundations; two real public reviews; extraction rejected then provider failure; no approved live profiles | Product-relevant corpus, independently supported behavior and C-persisted frozen 500-person population |
| Neon persistence | Connection not established | Actual durable write/read/migration evidence |
| Persona browser execution | Bounded executor/runtime policy and local mock task/captured-frame viewer verified; production path gated | A validated product plus C durable evidence/jobs; one real checked task |
| 500 v1 + 500 v2 trials | Not executed | Per-persona mandatory attempt + feedback on both versions |
| Product v2 | Not promoted. Three bounded UI patches passed the fixed checks in isolated QA on a local image rebuild | Evidence-linked proposals, QA on the frozen v1 image and human approval |

C starter: evidence-validating deterministic fixture analysis and readable report controls implemented; no-model/no-persistence status explicit. Lazy pooled database helper and an unapplied initial SQL migration are prepared. An in-memory patch lifecycle enforces proposed → reviewed → patched → regression → human approval, with rejection and rollback; no real patch, executed regression or v2 exists. Twenty-four focused mocked analysis/database checks passed; this does not establish a Neon connection or real engineering-agent run.

All three starter slices are now implemented. A's discovery is synchronous/in-memory with explicit fixture/live source status. B's authenticated WebSocket carries fixture state/heartbeat only, with no invented frames or actions. Root verification established typed API/build checks and desktop/mobile browser smoke including fixture discovery and exact-session switching. Real HF inference, Neon write/read, selected repository pair, product-backed browser worker and full population execution remain gated.

Fixture responses, synthetic character animation and development feedback are useful scaffolding. They are not sponsor integration evidence, observed browser behavior or completed experiments.

2026-10-10 software-behavior update verified: 99 backend tests (28 new provenance/behavior cases), backend lint, OpenAPI/TypeScript drift checks, typecheck/build and desktop/mobile fixture smoke pass. The viewer exposes behavior/source lineage, and the persona grid handles desktop-to-mobile resizing. Agent definitions and both updated persona/evolution skills validate. Real reviews and live behavior extraction remain P1 milestone work; no migration or paid inference was run.


2026-10-10 A source inspection: commit-pinned README/license/explicit documentation reads and bounded issue snapshots are implemented with visible partial failures and memory-only retention. A real psf/requests collection returned pinned files and three issue records without HF inference or code execution. 121 backend tests, lint, OpenAPI/type drift checks, frontend typecheck/build passed. This verifies source collection only; it does not establish a selected pair, licensing approval, proposal extraction, durable Neon storage or a validated adapter. Docker CLI is present; the daemon was unavailable during local readiness checking.

Source inspection desktop/mobile browser check passed, including expanded source excerpts and no horizontal overflow at 390px. Local captures are under ignored artifacts/.
2026-10-10 B mock A handoff verified: 127 backend tests pass with `B_BROWSER_TESTS=1`, including
seven actual local Chromium checks for mock-page success/failure, cancellation, target validation,
action limits, initial-state mismatch and context isolation/recovery. Backend lint, OpenAPI drift,
frontend generated-contract check, typecheck and build pass. The standalone mock browser command
observed navigation, two clicks, a deterministic check and four captured frames in memory. The new
500-person fixture builder configures distinct persona/scenario/task identities but records zero
mandatory trials; nothing is persisted. No API/viewer routes or shared schemas were changed.
The opt-in HF smoke command is prepared, not executed. Doctor still reports HF and Neon unconfigured
and Docker absent from PATH. Production population, review ingestion/extraction, spend enforcement,
durable jobs, real A integration, session feedback/streams and the 1,000-session experiment remain open.

2026-10-10 B review-corpus follow-up verified: 182 combined backend tests pass with Chromium checks
enabled, including 33 new offline corpus/extraction checks. Lint, OpenAPI/type drift, frontend
typecheck and build pass. Feature-local HN/manual intake, privacy/excerpt curation, deduplication,
immutable canonical snapshots and HF draft extraction are prepared. All source responses and HF
outputs in verification were mocked; no real review ingestion or live model request is established.
Extractions remain pending independent semantic-support review and cannot become approved live
persona behavior through these helpers. HF configuration is now present locally, but live mode and
positive authorized budget are absent. C persistence and full population/trial gates remain open.

2026-10-10 B runtime foundations verified: **317 backend tests** pass with Chromium enabled,
including six review-driven regressions for DOM target identity and cancellation at reset/check/
feedback boundaries. Six Node stream-validation checks, Ruff, typecheck/build and OpenAPI/generated
type drift checks pass. Actual desktop/mobile UI smoke renders exact mock captures and preserves
pending execution across selection; 390 px layout has no horizontal overflow. A coordinated the
additive canonical-Session mock route; no contract, dependency or migration changes.

Real external evidence now supersedes earlier configuration notes: HF configuration smoke succeeded
on Qwen/Qwen3-32B/deepinfra and two public HN reviews were collected. Independent support review
rejected the extracted behavior; a fresh extraction failed at the provider boundary. Zero approved
live profiles/trials. Conservative aggregate accounting $0.01836714 of the $4 small-request approval
(not provider invoice), with unknown/failure charges retained. No further paid calls. Local app remains
fixture; all experiment counters zero. A validated product, C durable evidence/reviewer identity/
spend/jobs, reliable supported extraction and measured pilot/soak gates remain open. Full changes
and next tasks: [B runtime report](tasks/developer-b-runtime-report.md).


2026-10-10 A discovery/proposal checkpoint: Popular search now supports explicit created/pushed date filters; genuine daily/weekly/monthly GitHub Trending uses a bounded HTML snapshot plus repository metadata verification. A live one-row Trending smoke passed. HF extraction attaches exact numbered source excerpts and proposal previews keep novelty/feasibility unresolved. Persistent local reservations bound A to the approved $2/model/provider configuration; they are not provider billing or experiment-wide accounting. API records remain in memory.

A inspected 27 pinned public candidates (16 established, six recent-query, five weekly Trending), retained 26 HF extractions and five unique-pair hypotheses, and recorded primary-source overlap/criticism in [candidate research](research/developer-a-candidates-2026-10-10.md). Missing README and failed model attempts remain visible. The two preferred sources, pdfplumber and Frictionless, passed independent known/invalid fixture probes in offline nonroot Docker containers; no adapter or product operation has been validated yet. This machine now has a verified running Docker daemon. Neon storage and immutable handoff to B remain open.

Final A branch verification against current master: 208 combined backend tests passed with `B_BROWSER_TESTS=1`, including the existing Chromium checks; lint, OpenAPI/type drift, frontend typecheck and production build passed. Desktop/mobile UI replay checked real recorded citations and proposal rendering, two-selection gating, separate Trending controls and no horizontal overflow at 390px. Replay routes made no additional GitHub/HF calls. Captures are local under ignored `artifacts/ui-proposals/`. The browser's two retained console errors were an earlier failed discovery request and a missing favicon. The existing large persona-bundle warning remains.

B PR #6 reconciled merged A PR #5 without changing A feature implementation: regenerated combined
OpenAPI/types, retained both owners' status evidence, and passed **343 combined backend tests** with
Chromium, Ruff, frontend type/build and contract drift. Initial PR CI passed before the upstream merge;
the reconciled commit triggers fresh CI. No additional live inference or spending during reconciliation.
2026-10-10 A product v1: selected the Python pdfplumber/Frictionless pair after independent execution and overlap research. SourceTable’s separate port-8001 page calls the real offline Docker adapter; types are validated from extracted strings and errors retain source page/cell geometry. Normal rows, wrong types, required missing values, wrong headers, malformed PDF, no table and actual timeout cleanup passed. Installed source archive metadata and container adapter fingerprint were checked. Input/output, process resources, wall time and stdout are bounded; operations have no shared server records.

A’s real-browser verification covered normal output, schema-error mapping, recovery, separate-context state, reload reset and 390px no-overflow layout. These are product checks, not persona trials. The frozen v1 manifest contains implementation commit/fingerprints, immutable local image ID, source pins, schemas, initial state and three browser check/task templates. Port-8001 `/api/v1/handoff` returns it only when local fingerprints match; the dashboard readiness route reports compatibility separately from process availability. All 220 backend tests passed with real Docker/Chromium checks enabled; lint, generated contracts and frontend typecheck/build passed. No additional HF calls were needed; A’s local reserved allowance remains $0.92.

Remaining cross-owner gates: C must provide Neon-backed evidence/version persistence; B must consume the handoff, bind tasks to actual scenario identities, retain browser/session outcomes and verify review-grounded population generation before trials. No v2, persona outcomes, public deployment or full experiment has been produced by this A work.

2026-10-10 A version-storage preparation: added an immutable version repository over C’s existing table/pool contract, with explicit live CLI opt-in, JSONB bound values, bounded transactions, idempotent save and conflicting-rewrite rejection. Eight offline cases and real disposable local PostgreSQL 17.11 roundtrip/idempotency/conflict/concurrent-save checks passed; the temporary database was removed. 228 combined backend checks pass. This is prepared A persistence code, not a verified Neon connection; no migration/shared-database code was changed. A’s alternate uploaded City/People/date PDF also passed adapter and UI checks, preserving frozen v1.

2026-10-10 C Neon gate preparation (E1): added an ordered, checksummed migration runner (`python -m backend.migrations.runner`) and a write/read/rollback gate (`python -m backend.migrations.roundtrip`), both through `NeonDatabase`. `001_initial.sql` no longer holds its own `BEGIN`/`COMMIT`, so each file and its `schema_migrations` row commit together. `002_persistence_checks.sql` adds an append-only probe table. Against a disposable local PostgreSQL 14.18 with TLS, both files applied, a rerun applied none, an edited checksum was refused, a failed file rolled back all pending files, and the gate read a committed row through a new pool and found the aborted row absent. Seven new checks pass with `TEST_DATABASE_URL` set (four skip without it). This is not Neon evidence. No Neon URL was configured, so no migration ran against Neon. A and B persistence stays blocked until someone runs the gate on Neon and records its output here.

2026-10-10 C repositories and durable jobs (E1, #10): `003_records_and_job_leases.sql` adds job attempt limits, session lifecycle columns, screenshot-safe action constraints and analysis role records. `SessionRepository` (shared) stores live sessions, sequenced actions and single feedback. Feedback must cite actions from its own session and persona. `AnalysisRepository` (evolution) stores append-only analyst/prioritizer/UX outputs whose cited sessions and actions resolve inside the experiment. `JobQueue` (shared) claims with `FOR UPDATE SKIP LOCKED`, fences each lease by owner and attempt, and recovers expired leases. Recovery requeues the job while attempts remain and fails it visibly after that. Against a disposable local PostgreSQL 14.18 with TLS, 24 claims from four pools on five jobs leased each job exactly once, a 0.5-second lease expired and was reclaimed as attempt 2 while the old holder was refused, and invalid cross-session evidence was rejected with nothing written. Removing the row lock made the race test fail (8 claims for 5 jobs), and removing `SKIP LOCKED` made the locked-row test fail. With `TEST_DATABASE_URL`: 261 passed, 8 skipped. Without it: 241 passed, 28 skipped. This is not Neon evidence. No Neon URL was configured.
PR #6 merge reconciliation with A PRs #7/#8 preserves the frozen product and both owners' evidence.
A coordinated test-only Windows portability fixes: bounded pytest IDs and synthetic temporary
manifest/source fingerprints, with image/set/content drift rejection retained. This does not validate
the Linux-frozen runtime on Windows. **362 combined tests passed with Chromium; one opt-in real
Docker test skipped** because Docker is unavailable on this host. Ruff, six stream-validation checks,
frontend type/build and generated-contract drift passed. B's next A-dependent task is consuming the
now-available [SourceTable handoff](handoffs/developer-a-v1.md), not waiting for its creation.

PR #6 also reconciled C's merged improvement-lifecycle PR #21 by regenerating combined contracts.
Latest verification: **387 backend tests passed, one opt-in Docker test skipped**, Chromium checks
enabled; Ruff, frontend type/build and generated-contract drift passed. C feature code was preserved.

2026-10-10 C structured role analysis: live analysis reads persisted session evidence and runs the analyst, prioritizer and UX reviewer roles through the shared HF adapter, with deterministic reference and category checks. 269 backend tests pass (real-database cases against a disposable local PostgreSQL; HF responses from a scripted provider client). Lint, OpenAPI/type drift, typecheck, build and a 1280px/390px browser render of the heuristic inputs pass. No Neon request or live HF analysis has run; analysis records are not yet persisted.


2026-10-10 A discovery revision: emerging anchor discovery now replaces forced repo pairing in the main UI. Recent/active search, local timestamped star/fork observations with source lineage, source/issue-based HF opportunity hypotheses, optional integrations, abstention, illustrative previews, shortlist/reject reasons and JSON export are implemented. Historical briefs are annotated; roadmap/ownership/API/data/agent/B/C handoffs describe the revision. Frozen SourceTable v1 and existing persona/evolution contracts are unchanged.

Verification before latest C merge: 493 combined backend tests passed with browser/Docker opt-ins (16 environment-gated cases skipped), 14 final opportunity regression cases passed, lint/contracts/typecheck/build passed. Desktop/mobile real-browser fixture preview/review/export checks passed with no horizontal overflow at 390px; exported JSON retained decision and illustrative status. A fresh emerging GitHub read collected star/fork metadata with honest insufficient-history status. Fresh browser-use/video-use sources were pinned to 43cfc566833548093455c9d4a46bd69913b7e552; a live Qwen3-32B/DeepInfra call returned a cited feature-extension hypothesis. Earlier provider failure and unsupported-evidence output were rejected, not recorded as successes. This is discovery evidence, not an approved opportunity, executed new prototype or persona trial. Existing-solution automation, linked-issue/PR verification, new opportunity Neon persistence and a selected new prototype remain open.
