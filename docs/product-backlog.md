# Product backlog

Updated 2026-10-10. This is the prioritized implementation backlog; [roadmap](roadmap.md) defines sequencing and [status](status.md) records verification evidence. Each developer owns frontend, backend and tests for their phase.

**Current count: 13 required milestones, 1 complete (F1), 12 remaining.** Seven remaining milestones have partial work; five are not started. B now has bounded corpus/population/runtime/budget foundations and exact mock captures, plus real HF smoke/source reads. Production review approval, persistence and trials remain unfinished. See [B runtime report](tasks/developer-b-runtime-report.md). Checklists do not increase milestone counts.

Priority **P0** means required for the complete demo, **P1** means improvement after P0, and **P2** means stretch. A milestone named `P1` is a persona milestone ID, not a priority. “Partial” means some code exists but the full acceptance criteria have not passed. Configured persona records, fixture sessions and passing scaffold tests do not establish executed trials.

## Completed foundation

| ID | Priority / owner | Outcome | Status and evidence |
| --- | --- | --- | --- |
| F1 | P0 / A coordinating, all contributing | Developers can work concurrently against a runnable shared app and contracts | Complete: three feature mounts, Pydantic/OpenAPI/generated types, explicit fixtures, three developer agents/skills, documentation, CI and local checks. 99 backend tests after the behavior-schema update, lint, contract checks, typecheck/build and desktop/mobile browser smoke pass. |

## Phase 1 — Project scraping and integration

Owner: **A**, using `developer_a_integration` and `$repofusion-integration`.

| ID | Priority / status | User outcome and work remaining | Dependencies | Acceptance and verification |
| --- | --- | --- | --- | --- |
| I1 | P0 / Partial | Discover 20–30 candidates and approximately five complementary proposals. Bounded Popular discovery and commit-pinned README/license/documentation collection with sampled issues are implemented; live collection has been checked. Complete HF extraction/critic, truthful Trending snapshot support, 20–30 real candidates/about five proposals and durable evidence storage. | F1; B's verified HF client; C's persistence interface; GitHub access | Candidates and proposals have source references, collection times, inspected commits and explicit adapter boundaries. Test extraction, provenance, malformed inputs, missing sources, quotas and Popular/Trending separation; demonstrate real source reads. |
| I2 | P0 / Not started | Select one useful, feasible pair after researching exact integrations and equivalent products. Show overlaps, proposed advantages and unresolved assumptions. | I1; research access; source runtime inspection | Persist queries/results and a reviewed selection with interface semantics, dependencies, licensing notes and known independent-execution fixtures. Test gate decisions against evidence; no unsupported uniqueness claim. |
| I3 | P0 / Not started | Run both sources independently and connect one narrow real workflow through an adapter. | I2; Docker/isolated execution; approved fixtures | Known input produces checked output through both sources. Independent, normal, invalid-input, incompatible-output and timeout checks pass; commits/environment and tolerances are recorded. |
| I4 | P0 / Not started | Use the integrated product through a real frontend and provide personas a factual briefing. | I3; shared version/task contracts | Product UI calls the real operation and handles loading/error/empty states. Immutable v1 manifest and validated capability inventory match the implementation. A browser smoke verifies the operation; B receives fixture state, task templates and deterministic checks. |

### Next tasks for A

- [x] **I1 source collector:** Pin commits and fetch bounded documentation/issues with provenance; mocked failure checks and a real public-repository read passed. Full candidate/proposal coverage remains open.
- [ ] **I1:** Use the shared HF adapter for validated capability extraction and complementary proposals, with offline tests first.
- [ ] **I2:** Record novelty/feasibility research and approve a small CPU-friendly pair.
- [ ] **I3/I4:** Establish independent execution, adapter correctness and the product-to-persona handoff.

**Inputs → outputs:** GitHub/research evidence → reviewed proposal → tested adapter → immutable product manifest/briefing. Investigation and UI can proceed against fixtures in parallel; real adapter execution waits for selection. If both sources cannot run within six hours of integration work, simplify or switch the pair. Reduce proposal breadth before sacrificing the real integration.

## Phase 2 — AI personas

Owner: **B**, using `developer_b_personas` and `$repofusion-personas`.

| ID | Priority / status | User outcome and work remaining | Dependencies | Acceptance and verification |
| --- | --- | --- | --- | --- |
| P1 | P0 / Partial | Bounded corpus/extraction, independent approval and exact-500 population foundations exist. Real category reviews collected; extraction rejected then provider failure. Finish product-relevant supported behavior and live generation/persistence. | A product context; source/access verification; representative HF evaluation; C storage | Exactly 500 distinct source-linked review-informed profiles with frozen corpus/behavior/generation versions. Tests cover unsupported interpretation, duplicates, fixture leakage and scenario mismatch; no representativeness claim. |
| P2 | P0 / Partial | HF smoke, conservative in-memory reservations, bounded runtime/executor and mock Chromium evidence exist. Finish representative role evaluation, C durable queue/accounting/evidence and A product-backed execution. | I4; C persistence/jobs; reviewed model/prices/budget; Chromium | One real checked task with durable actions/feedback. Observed targets pinned; cancellation/failure tested. Unknown inference charges retained conservatively; full experiments need durable accounting. |
| P3 | P0 / Not started | Run mandatory v1 trials and feedback for all 500 personas, including initially uninterested ones. | P1, P2; five pilots; 20-person soak; measured capacity | 500 persona-linked executed attempts and feedback records exist. Honest counters distinguish success, product/infrastructure failure and stopping. Verify throughput/cost forecast, state isolation, resume behavior and population coverage; retain version/task configuration. |
| P4 | P0 / Partial | Ten featured characters, exact-session state/actions and actual mock PNG captures with stale labels are verified. Finish ten product-backed sessions and action-driven world behavior. | P2 durable real execution; artifact/stream pipeline | Selected session's exact captured frames/actions, timestamps and live/replay/stale labels. Switching preserves work and rejects foreign/obsolete frames. No independent iframe substitutes for controlled browser. |

### Next tasks for B

- [x] **P2 foundation:** Real HF configuration smoke (`Qwen/Qwen3-32B` / `deepinfra`), conservative single-process reservations and failure accounting. Durable experiment spend/representative role evaluation remain open.
- [x] **P1 foundation:** Bounded HN/manual intake, curation/dedup/frozen corpora and checked extraction; two real public comments collected. First draft independently rejected; fresh provider request failed. No approved live behavior.
- [x] **P1 foundation:** Exact-500/pilot population generator, independent approval gate and immutable lineage tested with fake HF; no live population generated or persisted.
- [x] **P2/P4 foundation:** Bounded executor, runtime HF decision/feedback policy and exact PNG viewer; local mock API/UI smoke passed with zero mandatory counts.
- [ ] **P1 live:** Resolve extraction/model reliability, collect A-relevant corpus and independently approve supported policies; protected reviewer identity/storage with C.
- [ ] **P1/P2 live:** Generate/persist 500 profiles, wire A's validated product/reset/check catalog and C's durable evidence/atomic ledger/leases, then one real trial.
- [ ] **P3/P4:** Five real pilots and twenty-person soak; measure capacity/cost, authorize full batches, execute v1 and match ten actual sessions.

**Inputs → outputs:** A's validated briefing/checks + population configuration → persona/scenario/task records → executed sessions/actions/feedback/frames. Population logic, worker tests and world UI can develop concurrently using fixtures; live trials require the real product. Start four workers and increase only after measurement. Cut optional continuation and visual detail before mandatory coverage; never replace the agreed 500 with an undisclosed smaller run.

## Phase 3 — Feedback agents and improvement

Owner: **C**, using `developer_c_evolution` and `$repofusion-evolution`. B owns execution of the retest within E3; C owns comparison and orchestration.

| ID | Priority / status | User outcome and work remaining | Dependencies | Acceptance and verification |
| --- | --- | --- | --- | --- |
| E1 | P0 / Partial | Produce grounded analyst/prioritizer/UX outputs from persisted feedback. Deterministic fixture grouping and a lazy DB helper exist; finish migration execution/repositories/job semantics and HF role workflows. | Neon access; B's HF client and session evidence; P3 for full-population analysis | Real persistent write/read/rollback works; feedback/action references are valid; product defects, relevance and infrastructure remain separate. Test evidence mismatch, missing records, role schemas and heuristic inputs. Show results backed by executed sessions. |
| E2 | P0 / Partial | Use implementer/QA roles to create two or three bounded improvements, preserving v1 and requiring human approval for v2. Current path validation and approval-denial stub are only starter guards. | E1; A's approved product boundary; fixed regressions; HF access | Isolated patches stay in approved paths, pass build/integration/UI checks and receive human review before v2 registration. Test regression failure, rejected patch, unauthorized promotion and rollback. Implementer cannot weaken checks or self-promote. |
| E3 | P0 / Not started | Rerun all 500 matched personas on v2 and compare outcomes honestly. | E2; B's P1/P2 execution system; frozen v1 tasks/configuration | 500 v2 attempts/feedback match v1 identities, goals, fixture state, checks and budgets. Verify denominators, missing/unmatched results and error categories; disclose inference configuration changes. Optional continuation is compared separately. |
| Q1 | P0 / Partial | Deliver a reproducible complete demo with readable evidence and labeled replay. Scaffold startup and browser smoke pass; full product rehearsal and release artifacts remain. | I4, P3, P4, E2, E3 | Real end-to-end flow passes, services restart reliably, HF/Neon usage is evidenced, v1/v2 are preserved and replay is labeled. Run combined checks, capture executed demo evidence and rehearse on the intended machine. A coordinates; each owner validates their slice. |

### Next tasks for C

- [ ] **E1:** Apply the reviewed migration to the intended Neon database and prove persistent write/read/rollback; implement feature repositories and job claim/lease recovery.
- [ ] **E1:** Connect real session evidence to structured HF analyst, prioritizer and UX workflows.
- [ ] **E2:** Implement isolated patch/regression/review states and reviewed v2 registration.
- [ ] **E3/Q1:** Request B's matched retest, validate comparisons and coordinate final release evidence.

**Inputs → outputs:** Persisted sessions/actions/feedback → grounded clusters/proposals → tested reviewed patch → v2 → matched comparison. Database/repository and role validation work can proceed with mocks before population runs; actual improvements require real evidence. Reject unsupported patches and retain a working v1 rather than promoting failing changes.

## Optional backlog

These items do not count toward the 12 remaining required milestones.

| ID | Priority / owner | Outcome | Dependencies / acceptance | Cut policy |
| --- | --- | --- | --- | --- |
| O1 | P1 / B | Richer aggregate-source coverage and contextual scenarios | P1/P3; provenance/coverage checks and feasible data access | Defer enrichment; retain clearly labeled balanced cohorts. |
| O2 | P1 / A | Deeper issue/discussion and equivalent-product research | I1/I2; additional sourced findings | Keep bounded core research. |
| O3 | P1 / C with B | Held-out scenarios to check improvement overfitting | E2/E3; fixed new checks and separate results | Complete matched coverage first. |
| O4 | P1 / B | Refined world, animations and viewer polish | P4; accessibility and performance smoke | Preserve exact viewing and simple geometry. |
| O5 | P2 / B | Separate MapLibre regional overview | P4; attributed data and separate render surface | Drop first if behind. |
| O6 | P2 / B | CDP screencast and in-world laptop display | P4; actual frames, acknowledgments and bounded overhead | Keep selected-panel screenshots. |
| O7 | P2 / A | Additional validated repository combinations | I3/I4 and completed core cycle; same execution criteria | One real integration remains the target. |

## Backlog operating rules

1. Select the first unfinished item in the owner's phase whose dependencies permit progress. Read that owner's [starter](coding-agents.md) and inspect existing code before repeating work.
2. For each bounded coding task, name allowed paths, consumed/produced contracts, tests and acceptance evidence. Coordinate shared schemas, dependency changes and cross-owner patches.
3. Update this backlog and [status](status.md) when acceptance evidence changes. “Done” requires the row's full outcome, not fixture rendering or a partial adapter.
4. Keep GitHub/search, HF, Neon and Docker readiness visible. Missing access permits offline implementation but cannot establish live results. No secrets in logs or artifacts.
5. Preserve the 500-per-version requirement. Before paid batches, verify a supplied inference budget and forecast 1,000 mandatory sessions plus pilots with a 30% time contingency. Pause/report capacity shortfalls rather than fabricate completion.
