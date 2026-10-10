# Developer B online data and pilot wiring — 2026-10-10

## Evidence established

- A fresh official Neon HTTPS readback returned the immutable 500-record SourceTable population, version `9b54b97f703dc637d3bf56bba3e5a1891fce1bfd16638a75988b8aaf4821e535`, population ID `0361b64e-75aa-5e0d-bc5c-b721a631ba9b`. The snapshot hash and exact count were checked. Completed trials: **0**.
- One record was bound to A's frozen normal6 task and sent to the configured Hugging Face provider through the existing guarded spending journal. The structured response echoed its exact persona, task, behavior-pattern and cited-review IDs and proposed **simulated** initial relevance. The diagnostic succeeded; it did not open a browser, observe demand, approve a new behavior pattern or complete a trial. Conservative journal charge for that request was `$0.00018378`; aggregate journal charge became `$0.03935208` within the existing `$3.98163286` cap. These are reservations/accounting, not a provider invoice.
- B-owned code now checks the population/task identity before inference; supplies a normal Python `PopulationRepository` read path; queues and executes at most one pilot lease; uses A's local handoff and fixed check; connects C's `JobQueue` and `SessionRepository`; and writes actual captured PNGs with action references. The pilot path is prepared, not executed.

## Exact gates and next actions

1. **P0 / C transport:** Native Python `NeonDatabase` cannot connect to the configured Neon endpoint on this Windows host (port 5432), although the official HTTPS operator path works. C must provide and verify a normal runtime database transport or an approved deployment environment. The temporary operator readback is ignored local evidence, not the application repository path.
2. **P0 / A product runtime:** Verify the frozen SourceTable image/process locally and provide `integration-product-runtime.json` matching A's manifest. Docker is unavailable on this host. The pilot gate checks the running handoff endpoint and rejects a mismatched process.
3. **P0 / A+C experiment setup:** Register the exact product version and experiment durably before a session insert, and establish the hosted reviewer identity. B's one-job helper requires those rows and a claimed lease. C should confirm an atomic terminal session/feedback transaction and the analysis reader's stop-reason source: the session repository writes a `stop_reason` column while the evidence reader looks in provenance.
4. **P0 / B pilot:** Evaluate representative context/action/feedback outputs with the approved model, forecast guarded cost, then execute one real normal6 browser trial and inspect its stored actions, frames, feedback and fixed result. Follow with five pilots, a 20-person soak and capacity measurement. Obtain separate authorization and a durable multiworker spend ledger before the paid 500 v1 and 500 matched v2 runs.
5. **P0 / B viewer:** Show ten actual product-backed sessions with their own action/frame timestamps and stale/replay labels after real evidence exists. The current ten-character and mock-frame foundation remains partial.

P1 richer source/scenario coverage and world polish, and P2 regional map/screencast, remain optional. P1/P2/P4 milestone IDs remain **partial**; P3 remains **unexecuted**. No configured persona is counted as a trial.

## Checks

The B persona suite passed 268 tests with 21 gated skips; B Ruff passed. A local opt-in Chromium executor run passed 43 checks earlier in this work. Across the repository, 563 backend tests passed, 95 skipped and one pre-existing Windows-only A/C source-freeze check failed because `implementation_hashes()` returns backslash path keys while the frozen manifest uses forward slashes. LF working-tree bytes match the frozen hashes. Ruff, OpenAPI and generated TypeScript drift checks, frontend typecheck and build passed. Native Python Neon read failed before any new HF request. The guarded HTTPS readback→HF diagnostic succeeded once and its ignored sanitized report remains in `artifacts/sourcetable-generation/online-context-hf-report.json`.
