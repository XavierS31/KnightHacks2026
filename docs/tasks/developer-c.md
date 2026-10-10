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

## Progress log

2026-10-10 starter complete: deterministic fixture analysis validates session/action/persona references, groups product/infrastructure/relevance feedback and exposes heuristic inputs. Empty known feedback returns no clusters; irrelevant outcomes remain relevance context even if barriers are supplied. The frontend can request the report; approval denies promotion with `409 REVIEW_REQUIRED`. Lazy `NeonDatabase` has mocked pool/transaction tests; `001_initial.sql` establishes initial provenance and job lease tables but is not applied. Twenty-four focused tests passed; combined schema/type/build checks passed. Live persistence, five HF engineering workflows, reviewed improvements and matched retest remain open. Next: authorized Neon round trip and real persisted feedback repository, then structured HF role analysis.


2026-10-10 E1 gate preparation: migration runner, `002_persistence_checks.sql` and the write/read/rollback gate are implemented and verified on a disposable local TLS PostgreSQL. The gate procedure is in `backend/migrations/README.md`. Neon is still not configured or migrated. Next: run the runner and the gate against the intended Neon database, then record the output in `docs/status.md`.
