# Integration workflow

## Shared contracts and handoffs

A coordinates shared schemas and central mounts. B owns inference/stream infrastructure. C serializes migrations and CI. Prefer additive contracts and contract-compatible fixtures while a producer is unfinished.

Contract change: record goal and affected consumers → obtain A's coordination → edit authoritative Pydantic → export OpenAPI → regenerate frontend types → update fixtures and consumers → run checks → notify owners. Don't edit generated types or another owner's feature without coordination.

| Handoff | Required evidence |
| --- | --- |
| A → B | Immutable product version/URL, source commits, validated capability briefing, initial-state fixture and deterministic task/check catalog |
| B → C | Experiment configuration, frozen persona/behavior/corpus/task/session identities, actual actions/outcomes, synthetic feedback and artifacts, explicit missing/failure counts; upstream reviews are preference context |
| C → A | Bounded improvement evidence, approved path scope, isolated patch and fixed regression results |
| C → B | Human-approved v2, original task/config references and matched retest request |

## Verification checkpoints

1. Offline baseline: API fixture reads, three feature views, contracts, tests and frontend build work without tokens.
2. One real path: product operation → persona browser action → saved outcome/feedback → selected-session viewer.
3. Pilot/soak: state isolation, recovery, provider limits, cost and throughput measured.
4. Improvement path: evidence → bounded patch → deterministic regressions → human review → preserved v1/v2.
5. Full coverage: 500 mandatory attempts with feedback per version, matched identities and denominators.
6. Demo freeze: full startup rehearsal, readable evidence, actual sponsor execution, labeled live/replay modes.

## CI and external environments

CI must run offline checks, never require developer secrets or make paid model calls. Export/generate contracts and fail if tracked generated output drifts. Run Python tests, TypeScript checks and frontend build. Live smoke tests are explicit local/integration checks with configured credentials.

Docker execution should use pinned source commits and bounded resources. Source-license review and runtime compatibility are part of pair feasibility. Avoid selecting a combination whose dependency or model-download footprint exceeds the measured schedule.

## Demo and rollback

Discover/select → show evidence/gates → execute real app → select library persona → inspect screen/actions/feedback → inspect reviewed change → open v2 → inspect matched retest → compare all 500.

Preserve v1 artifacts and commit/version identity before patching. Failed patches remain rejected and cannot enter matched retests as approved v2. A replay is acceptable demo fallback only when labeled and backed by executed evidence. Never present prerecorded or fixture frames as live.

