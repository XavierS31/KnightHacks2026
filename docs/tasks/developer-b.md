# Developer B kickoff — AI personas and world

Use `developer_b_personas` and `$repofusion-personas`. Read root AGENTS.md, ownership, architecture, runtime/data contracts and roadmap. Inspect current files before repeating completed starter work.

Read [software behavior](../software-behavior.md). Every live persona requires real-review-informed software behavior. B owns source collection, corpus deduplication, HF extraction/assignment and provenance UI; C owns durable storage. B's bounded intake/extraction/population/runtime foundations now exist. Real source intake and HF smoke are demonstrated; approved behavior and product-backed execution remain gated. See the [runtime report](developer-b-runtime-report.md) for changes, checks and remaining work.

## Boundaries and inputs

Own both `features/personas` modules, `backend/tests/personas/**` and `backend/app/shared/inference.py` with focused tests. Coordinate shared contracts with A and persistence with C. Do not edit integration/evolution or migrations. Inputs are canonical persona/scenario/task/session records, explicit fixture population and A's validated briefing/check catalog when available.

## Emerging opportunity consumer handoff — 2026-10-10

Read [opportunity discovery](../opportunity-discovery.md). A now discovers an emerging anchor and suggests a feature extension or optional integration; a two-repo pair is no longer required. `OpportunityReport`/shortlist/illustrative examples are hypotheses, not verified capabilities or a trial launch. This revision does not complete a new population, persona trial or simulation.

Consume only a subsequently validated A ProductHandoff with immutable product/check/task identities, factual supported capabilities and scoped initial state. Use the selected opportunity's audience/problem to choose relevant review sources, personas and scenarios; preserve assumptions and negative relevance rather than engineering favorable feedback. Reject unsupported proposed features from task planning. Existing browser isolation, viewer, mandatory coverage and matched retest contracts remain unchanged. SourceTable's frozen v1 remains the earlier runnable experiment, not automatic evidence for a newly proposed opportunity.

Coordinate the factual briefing/task mapping with A and persistence with C before launching a selected-opportunity pilot. Keep five-person pilot, 20-person soak and full-batch evidence distinct; no new live execution is claimed by the discovery UI. Historical progress entries below retain their original evidence and configuration dates.

## First three tasks

1. **Population and inference:** verify the shared async HF adapter, bound retries/concurrency and report sanitized failures/usage. Collect relevant real software reviews with canonical IDs/URLs/dates/hashes/context, then extract checked tendencies/triggers/trial policies through HF. Generate 500 contextual personas with required `software_behavior`, immutable corpus/generation versions and explicit attribute provenance. Done: source support/citation/context checks pass; offline tests cover invalid schemas, duplicates, unsupported interpretations, fixture leakage and missing sources, plus inference failures; no client receives HF_TOKEN. Live inference needs an authenticated representative smoke test. Do not count ten fixture profiles as a completed population generator.
2. **One real trial:** execute a supported task using isolated Playwright context and scoped product state. Persist actual bounded actions/outcome/feedback with honest initial/post-trial relevance. Done: one real browser interaction plus deterministic check and saved evidence; action target validation, failure and cancellation are tested. Do not claim execution from the fixture timeline.
3. **Exact session viewer:** connect one character to its actual persona/session, then reuse it for ten. Use readable DOM selection alongside 3D selection. Done: selected frames/actions are exact, timestamps/mode/staleness visible, switching selection does not cancel work. Run five-person pilot and 20-person soak before 500.

## Dependencies, checks and scaling

HF credentials/model/budget and A's real product are live gates. Fixture development can proceed meanwhile. Start four workers; measure tokens/calls, sessions/hour, CPU/memory and provider rate limits. Reserve both 500-person batches plus 30% contingency. Optional continuation must not consume mandatory coverage capacity.

Test session isolation, bounded actions/stopping, evidence references, worker recovery and stream selection. Run relevant pytest and frontend typecheck/build. Coordinate and regenerate schemas. Preserve persona/behavior/corpus/task/check identity for C's v2 retest. Review patterns guide available-action choices and relevance; they cannot skip the mandatory trial or serve as defect evidence in feedback. Keep feedback synthetic and linked to executed session actions.

## Progress log

2026-10-10 runtime foundation follow-up: population/independent support review, conservative spend
reservations, bounded executor/HF action+feedback policy and exact selected mock captures are built.
317 backend tests with Chromium, six stream checks and lint/type/build/contracts pass; desktop/mobile
UI smoke passed. Real HF smoke and two HN reviews demonstrated, but extraction rejected then provider
failure; no approved live population/trials. See [runtime report](developer-b-runtime-report.md) for
changes, budget evidence and dependency-ordered work still open. P1/P2/P4 partial, P3 unexecuted.

2026-10-10 review-corpus follow-up: bounded fixed-endpoint HN intake and manual/permitted-export
records, explicit privacy/paraphrase curation, normalized source-content hashes, corpus-level dedup,
immutable snapshot lineage and schema/citation/excerpt-checked HF draft extraction are implemented
in B's feature modules. Proposals remain pending independent support review; literal quotation
matching cannot establish semantic support or produce approved live profiles. Thirty-three focused
offline tests use fake HTTP/HF and invented source records. No real collection, paid inference,
source-permission claim, population generation or Neon persistence is established. HF configuration
is present locally; live mode and a positive authorized budget are still absent. Next gates: explicit
HF smoke authorization/budget, relevant real review selection and independent support review,
C-coordinated storage and live persona generation. This follow-up is stacked on the mock-handoff PR.
Combined validation: 182 backend tests with Chromium enabled, backend lint, OpenAPI/type drift,
frontend typecheck and build pass. Existing frontend large-chunk/deprecation warnings remain.

2026-10-10 mock A handoff slice: B-owned `mock_handoff.py`, `mock_product.py`, `mock_worker.py`
and `kickoff.py` supply a complete synthetic handoff category set, 500 deterministic fixture
persona/scenario/task identities, isolated loopback Chromium mechanics, actual in-memory screenshots,
fixed output checks and explicit failure/cancellation/action-limit handling. Source commits are
honestly unavailable, capability validation stays false and completed trial counts stay zero.
The opt-in `--hf-smoke` command is ready for user-supplied token/model/provider and authorized budget;
no paid call was made. See `backend/app/features/personas/README.md` for commands and credential gates.
Real review collection/extraction, HF persona generation, dollar spend enforcement, C-coordinated
durable storage, A's validated real product, streamed production frames/feedback and pilots/full
batches remain open. This slice does not complete P1/P2/P3/P4.
Verification: 127 combined backend tests pass with local Chromium checks enabled, plus backend lint,
OpenAPI/generated TypeScript drift checks and frontend typecheck/build. The standalone browser smoke
passes its mock output check with four actual in-memory frames. HF/Neon remain unconfigured.
PR preparation rebased this slice onto A's merged source-inspection work: 149 combined backend
tests, lint, OpenAPI/type drift, typecheck and build pass. API types were regenerated to normalize
Windows checkout line endings; the generated content is unchanged.

2026-10-10 behavior schema update: required review evidence/profile/pattern contracts, honest fixture example, provenance viewer and lineage validation added. Open P1 work: collect real reviews, independently verify extraction support, implement HF generation/assignment and persist the 500-person population. The contract does not establish real review ingestion.

2026-10-10 starter complete: owned HF adapter scaffolding and focused offline tests, authenticated fixture session detail/WebSocket state and heartbeat, and exact-session character/viewer switching are implemented. No captured frames/actions are fabricated. Combined schema/type/build checks passed; desktop/mobile browser smoke verified session selection. Real HF access, product-backed Playwright worker, persisted evidence and all 1,000 mandatory trials remain gated. Next: authenticate representative inference and execute one real task against A's validated product.

