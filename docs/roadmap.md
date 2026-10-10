# Three-phase roadmap

Current gate (2026-10-10): no prototype is selected. Historical populations and database evidence remain preserved, but require new product-relevant task/corpus review before reuse. Generic B/C infrastructure remains available; generation and catalog binding are not executed trials.

2026-10-10 B online-data update: a fresh exact Neon HTTPS readback of the 500-record frozen population fed one review-linked persona/task context to guarded Hugging Face inference. The structured response cited the supplied pattern/review IDs; completed trials remain zero. B's one-pilot lease, fixed-check and durable evidence wiring is prepared. Native Python Neon connectivity, a newly selected verified prototype process and durable experiment registration still gate a real pilot. P1/P2/P4 remain partial and P3 unexecuted. See the [online data report](tasks/developer-b-online-data-report.md).

This is the implementation roadmap. The [product backlog](product-backlog.md) tracks prioritized implementation work, owners and acceptance; status evidence lives in [status](status.md). The skeleton is a starting point; production feature milestones below remain open until demonstrated.

## Phase 1 — Project scraping and integration (A)

| ID | Priority | Deliverable | Dependency and acceptance |
| --- | --- | --- | --- |
| F1 | P0, all | Shared scaffold, contracts, fixtures, mounts and local checks | Runnable fixture views, generated types and passing offline checks |
| I1 | P0 | Automatic Emerging/Popular/Trending research, explanatory briefs and substantial repurposing opportunities | Source links/commits, truthful Popular/Trending distinction |
| I2 | P0 | Existing-solution and feasibility gates | Recorded queries/results and independently runnable selected source tool(s) |
| I3 | P0 | Narrow real extension or adapter | Known outputs, invalid input, incompatible result and timeout cases pass |
| I4 | P0 | Generated product v1 and validated briefing | Actual UI calls I3; supported tasks/checks handed to B |

Collect 20–30 candidates, investigate anchor repositories, and allow zero worthwhile opportunities. Feature extensions need no second repo; integrations require necessary complementary capabilities. Select one opportunity using problem evidence and existing-solution/feasibility research, then execute a narrow real prototype. CPU-friendly fixtures constrain implementation, not idea generation. See [opportunity discovery](opportunity-discovery.md).

## Phase 2 — AI personas (B)

| ID | Priority | Deliverable | Dependency and acceptance |
| --- | --- | --- | --- |
| P1 | P0 | 500-person population with provenance and real-review-informed software behavior | Bounded Reddit/HN/general review corpus, resolvable citations and contextual tendencies/trial policies; intentional coverage and fictional details labeled; no claimed representativeness |
| P2 | P0 | Shared Hugging Face adapter and real browser worker | Model evaluation, structured-output checks, isolated state and saved evidence |
| P3 | P0 | v1 mandatory trials and feedback for all 500 | I4, five pilots and 20-person soak; exact counters and budget forecast |
| P4 | P0 | World and selected-session viewer | Ten persona-linked characters; correct real frames/timeline; stale/replay labels |

World detail can develop against fixtures while A establishes the product. Fixture interactions never become observed persona outcomes. Start with four workers; select higher concurrency only from measured CPU/memory and provider rate limits.

2026-10-10 B mock development evidence: an owned in-memory A handoff and loopback browser harness
now support 500 unique fixture persona/task records, bounded observed-target actions, real mock-page
screenshots and deterministic checks. All experiment execution counters remain zero. The explicit HF
configuration smoke command is prepared but has not made a live request. P1/P2/P4 remain partial;
P3 remains unexecuted. Commands and limitations: `backend/app/features/personas/README.md`.

B's subsequent P1 slice adds source-intake/curation, deduplicated frozen in-memory corpora and
checked HF extraction drafts (33 new offline tests; 182 combined with Chromium). No actual source
collection/model extraction or approved behavior assignment has been demonstrated. P1 remains
partial; independent support review, live HF verification, population generation and C storage
are still required before production acceptance.

Current B evidence supersedes the earlier slice notes above: bounded population/approval, budget,
executor/runtime policy and exact captured-frame foundations are implemented; actual HF configuration
smoke and two public review reads occurred. The extracted policy was independently rejected and
the revised request failed; no behavior approved or live population generated. Local mock API/UI
executes real Chromium mechanics with zero mandatory counts. P1/P2/P4 remain partial and P3
unexecuted. See [runtime report](tasks/developer-b-runtime-report.md) for accounting, checks and A/C
blockers. Real review grounding is P0; freeze versions before v1 and preserve them for v2.

## Phase 3 — Feedback agents and improvement (C)

2026-10-10 issue #13 follow-up: live E1 reports now persist with inference provenance and
session/action fingerprints. Live E2 intake requires an exact supported stored proposal,
executed frozen-v1 feedback and a bounded UI scope; caller-edited or changed evidence is
rejected. Native read-only Neon access succeeded, but the queried database has zero live
sessions/feedback/analysis/version records. The frozen image is absent locally. E2 remains
partial: no evidence-backed improvement or human-approved v2 was created. See
[the issue #13 handoff](tasks/issue-13-handoff.md).

| ID | Priority | Deliverable | Dependency and acceptance |
| --- | --- | --- | --- |
| E1 | P0 | Analyst, prioritizer and UX roles | P3 evidence; valid session/action references and explicit categories |
| E2 | P0 | Implementer and QA; two or three bounded changes | Isolated patch scope, fixed checks, human approval, preserved v1 |
| E3 | P0, B/C | v2 matched 500-person retest and comparison | Approved v2; fixed persona/behavior/corpus/scenario/task/check identities; honest denominators |
| Q1 | P0, all | Demo freeze, labeled replay and startup rehearsal | Build/tests/contracts pass; external usage evidenced |

## Parallel schedule and gates

| Elapsed time | Target milestone |
| --- | --- |
| H0–H2 | Scaffold and fixtures; HF authentication/model evaluation; Neon and Docker availability checks |
| H2–H6 | Sources running; one real browser session; fixture-backed evolution workflow |
| H6–H8 | Integration gate, factual briefing and five-person pilot |
| H8–H14 | Soak and full v1 batch; C analyzes accumulating evidence |
| H14–H17 | Reviewed improvements, fixed regressions and v2 |
| H17–H22 | Full matched v2 batch and comparison |
| H22–H24 | Feature freeze, replay capture, rehearsal and submission |

The 24-hour target depends on measured throughput. With 36 hours, reserve the extra time for coverage and reliability. Before launching all 500, forecast cost and duration for **1,000 mandatory sessions plus pilots**, with a 30% time contingency. Do not spend the v2 capacity on optional v1 continuation.

Cut optional tasks, detailed geometry, extra discovery, MapLibre and screencasting first. If mandatory coverage cannot fit, report the shortfall and incomplete state rather than silently reducing the requirement.

## Later priorities

P1: richer population sources/scenarios, deeper novelty research, held-out checks and world polish. P2: separate regional map, screencast, laptop textures and additional integrations. No hardware-inference setup phase remains.

## Handoffs and completion

A hands B a version manifest, product URL, validated briefing and fixed task/check catalog. B hands C persisted session/actions/feedback. C requests A's review of approved-boundary patches and B's matched retest. All owners verify the combined demo journey.

Completion requires one real validated opportunity prototype, all 500 evidence-backed mandatory trials and feedback per version, ten exact selectable sessions, five engineering roles, reviewed improvements, preserved versions, substantive HF/Neon execution and honest matched results. Large configured fixture populations do not satisfy these gates.
