# API contract

The backend Pydantic models in `backend/app/shared/contracts.py`, feature-owned integration models, and exported `shared/openapi.json` are authoritative for implemented routes, exact fields, enums and validation. Generated frontend types live in `frontend/src/shared/api-types.ts`. The target production table does not mean every endpoint is implemented by the scaffold. Inspect `/openapi.json` before consuming a route. A fixture-backed read route is not a durable production workflow.

## Current scaffold interfaces

| Route | Response / behavior |
| --- | --- |
| `GET /api/v1/health` | Process status, app mode, configuration booleans, population target and featured count; configuration is not verified external connectivity |
| `GET /api/v1/integration/summary` | `IntegrationSummary`, explicitly fixture-backed |
| `GET /api/v1/personas/summary` | `PersonaSummary`, explicitly fixture-backed |
| `GET /api/v1/evolution/summary` | `EvolutionSummary`, explicitly fixture-backed |
| `POST /api/v1/discovery-runs` | Synchronous `201 DiscoveryRun`, in-memory storage; fixture by default, bounded live GitHub read opt-in via server `APP_MODE=live` |
| `GET /api/v1/discovery-runs/{id}` | Stored in-memory discovery result; `404` for unknown IDs; not durable jobs |
| `GET /api/v1/sessions/{id}` | Fixture-only `Session`; bearer token or local fixture access, allowed-origin check; rejects live mode until storage/execution exists |
| `WS /api/v1/sessions/{id}/stream` | First-message token authentication or local fixture access, origin check, fixture state/heartbeat only; no browser frames or execution |
| `GET /api/v1/contracts/stream-event` | Registers `StreamEvent` for OpenAPI generation; returns `409 SCHEMA_ONLY`, no live frames |
| `POST /api/v1/experiments/{id}/analysis` | Known fixture experiment only; optional `AnalysisRequest` with explicit fixture sessions; synchronous `200 AnalysisReport`, deterministic grouping and no inference/persistence |
| `POST /api/v1/improvements/{id}/patch-runs` | `PatchRunCreate` (actor + `proposed` improvement with session evidence) → `201 PatchRun` in `proposed`, based on A's frozen v1 manifest and its fixed check IDs; in-memory only |
| `GET /api/v1/patch-runs/{id}` | Stored in-memory `PatchRun` with state, events, patch, regression results and v2 candidate |
| `POST /api/v1/patch-runs/{id}/review` | Human reviewer accepts the scope: `proposed` → `reviewed` |
| `POST /api/v1/patch-runs/{id}/patch` | Implementer submits full files: `reviewed` → `patched`. Each file must be inside the approved paths and in C's product boundary (`product/ui/app.js`, `index.html`, `style.css`, which map to A's SourceTable UI files). The patch is held in the record, not written to v1 |
| `POST /api/v1/patch-runs/{id}/edits` | Implementer submits bounded find/replace edits. Each `find` must occur once in the frozen v1 text. The server applies them and records files and edits: `reviewed` → `patched` |
| `POST /api/v1/patch-runs/{id}/implement` | The HF implementer role (coding model, B's adapter) proposes bounded edits. They are applied as above, and the role provenance is stored in `implementer_run` |
| `POST /api/v1/patch-runs/{id}/qa` | QA reviewer (not the implementer) runs the fixed checks in an isolated workspace: `node --check`, a real-adapter probe and A's three Chromium checks. Results are recorded for the patch digest: → `regression_passed` or `regression_failed`. If the configured image is not the frozen v1 image, or the checks cannot run, the response is `503 QA_UNAVAILABLE` and nothing is recorded. Callers cannot post their own results |
| `POST /api/v1/releases` | Human reviewer composes two or three distinct `regression_passed` bounded-edit runs on one base → `201 PatchRun` in `reviewed` |
| `POST /api/v1/patch-runs/{id}/compose` | Implementer applies every component's edits, in order, to frozen v1: `reviewed` → `patched`. The release then needs its own QA and human approval. No component implementer may approve it |
| `POST /api/v1/patch-runs/{id}/approve` | Human reviewer (not the implementer) approves `regression_passed` → `approved` and registers a v2 candidate; one active v2 per base |
| `POST /api/v1/patch-runs/{id}/reject` | Human reviewer rejects any open run → `rejected` |
| `POST /api/v1/patch-runs/{id}/rollback` | Human reviewer retires an approved v2 → `rolled_back`; v1 is active again |
| `POST /api/v1/patch-runs/{id}/retest-requests` | `RetestRequestCreate` (fixture v1 `ExperimentRun`) → `201 RetestRequest` for an `approved` run: frozen v1 identities, fixed checks, v1 inference profile and a v1 record digest; `409` if v2 is not approved; live mode `503` until identities are persisted |
| `GET /api/v1/retest-requests/{id}` | Stored in-memory `RetestRequest` |
| `POST /api/v1/retest-requests/{id}/comparison` | `ComparisonSubmission` (fixture v1 and v2 runs) → `ComparisonReport`: pairs by persona, separate outcome and error buckets over 500, paired rates, inference changes, separate continuation and agent time that is not human time |

Owners may add bounded starter routes while development proceeds; the generated OpenAPI remains current truth.

## Emerging opportunity discovery — implemented additive interfaces

The [opportunity discovery revision](opportunity-discovery.md) supersedes forced two-repo matching. These synchronous routes are mounted under `/api/v1`; reports/snapshots remain bounded in memory. They are not durable jobs or trial launches.

| Route | Input → response / gate |
| --- | --- |
| `POST /discovery-runs` | `DiscoveryRequest` now accepts `discovery_mode=emerging` alongside Popular/Trending; returns `DiscoveryRun` with additive `momentum` signals. Emerging defaults to recent-created/recent-pushed search sorted by total stars, not growth |
| `POST /discovery-runs/{run_id}/repositories/{repository_id}/sources` | `SourceRequest` with up to three documentation paths and 0–10 issues → `201 SourceSnapshot`; requires live server and live discovery, with repository membership checked |
| `GET /source-snapshots/{snapshot_id}` | Retained `SourceSnapshot`; unknown/evicted IDs return `404` |
| `POST /opportunity-reports` | `OpportunityRequest`: one `anchor_snapshot_id`, zero to two distinct `supporting_snapshot_ids`, optional `interests` (300 characters) → `201 OpportunityReport`; existing snapshots required, shared HF/live configuration and approved A budget gates apply |
| `POST /integration/opportunity-demo` | No input → `201 OpportunityReport` containing an explicitly fictional feature-extension teaching example; no HF, GitHub, validation or trial execution |
| `GET /opportunity-reports/{report_id}` | Retained `OpportunityReport`; `404` after restart/eviction or for unknown IDs |
| `POST /opportunity-reports/{report_id}/cards/{card_id}/decision` | `OpportunityDecision` with `shortlisted`/`rejected` and nonblank `note` (up to 1,000 characters) → updated report; verifies card membership. This mutable review does not promote a product or start a trial |

`OpportunityReport` carries anchor identity/commit, mode, creation time, up to two model hypotheses, an abstention reason when none are proposed, research leads, inference provenance/reservation and limitations. Each card has a UUID, `kind=feature_extension|integration`, `need_basis=issue_report|inferred_workflow`, audience/problem/current/proposed value, why investigate, implementation boundary, hypothetical input/output/check, risk and server-resolved evidence. Cards remain `status=hypothesis`, `novelty=unresolved`, `feasibility=unreviewed`, and `example_status=illustrative_not_executed` even after shortlisting. An integration must use supplied supporting snapshots with documented capability citations; a feature extension uses none. Citation IDs are checked for existence/ownership, not approved semantic support.

`DiscoveryRun.momentum` includes current/baseline observations, status, nullable net star/fork deltas, elapsed hours and an explanatory note. An unavailable baseline is not zero growth. Local count history survives process restart; discovery results and opportunity reports do not. No growth-ranked search, automated alternatives/issue-PR research, prototype generator or new opportunity trial is established by these routes.

Legacy extraction/proposal-preview routes remain available for existing consumers. A selected opportunity must pass research and real implementation/fixed-check gates before producing the existing validated `ProductHandoff`; B/C must not treat a report or illustrative example as that handoff. The frozen SourceTable v1 API/manifest remains unchanged.



`Persona.software_behavior` is required in `PersonaSummary`: `SoftwareBehaviorProfile` contains corpus/generation versions, patterns and `SoftwareReviewEvidence`. Patterns define tendency, trigger, agent policy and source IDs; review records preserve platform, permalink, dates, normalized-content hash, software context and report type. Reddit, Hacker News and general review categories are supported. Current responses are explicit behavior fixtures, not collected reviews. Live summaries reject fixture behavior. See [software behavior](software-behavior.md) for semantics and remaining collection work. This schema addition requires older persona payload producers to supply the new field; frontend types are regenerated.

The analysis starter defaults to the known fixture sessions, which currently have no feedback. It returns zero clusters without inventing evidence. Submitted fixture feedback must reference existing same-session actions and correct persona/experiment identities. Its score denominator is supplied sessions with feedback. It is not the planned asynchronous production agent pipeline.

The discovery starter is synchronous and retains results only in memory. The stream starter authenticates before sending session data; a configured `VIEWER_TOKEN` is transmitted in the first WebSocket message, not the URL. Default local fixture access is restricted to loopback clients. Explicit stored fixture state and heartbeats do not imply Playwright screenshots.

## Conventions

All domain routes use `/api/v1`. Internal IDs are UUIDs. Reads return `200`, durable job creation returns `202` with job identity, malformed bodies return `422`, unknown records return `404`, and invalid lifecycle transitions return `409`. WebSockets are session-specific and require authorization before externally exposed deployment.

```json
{
  "error": {
    "code": "VERSION_NOT_VALIDATED",
    "message": "This version has not passed integration checks.",
    "retryable": false,
    "details": {}
  },
  "request_id": "da9d7a7b-c89a-43a5-89ce-daeef9df20bf"
}
```

Production errors must not leak tokens, database connection strings or unredacted external exceptions. The developer startup default is local-only; production authentication is required before publishing external controls or streams.

## Target endpoints

| Owner | Method / route | Input → output / consumer |
| --- | --- | --- |
| A | `POST /discovery-runs` | Mode/filter/limit → job; discovery UI |
| A | `GET /discovery-runs/{id}` | ID → progress, candidates/proposals |
| A | `POST /proposals/{id}/checks` | Selected opportunity → research/feasibility job (target only; no automated research route in this slice) |
| A | `POST /integration-runs` | Selected feature-extension/integration opportunity and fixture references → validation job |
| A | `GET /integration-runs/{id}` | ID → source/adapter/check evidence |
| A | `GET /products/{id}/versions/{version}` | Product/version → immutable manifest/briefing; B/C |
| A | `POST /products/{id}/versions/{version}/execute` | Capability/payload/session scope → operation result; product UI |
| B | `POST /populations` | Cohort/assumption configuration, frozen review corpus/extraction versions, count 500 → job; reject unsupported behavior and fixture sources in live mode |
| B | `GET /populations/{id}` | ID → persona/provenance/generation status |
| B | `POST /experiments` | Population/version/task/config → experiment job |
| B | `GET /experiments/{id}` | ID → exact counters and health |
| B | `POST /experiments/{id}/cancel` | ID → cooperative cancellation state |
| B | `GET /sessions/{id}` | ID → persona/scenario/task/timeline/feedback/artifacts |
| B | `WS /sessions/{id}/stream` | Session/last sequence → state, executed events and frames |
| C | `POST /experiments/{id}/analysis` | Experiment → evidence clusters/ranked proposals job |
| C | `POST /improvements/{id}/patch-runs` | Approved patch scope → isolated patch/check job |
| C | `POST /patch-runs/{id}/approve` | Human review → registered v2, only after checks |
| C | `POST /experiments/{id}/retests` | Original experiment + v2 → matched experiment job |
| C | `GET /comparisons/{id}` | ID → matched results/denominators/evidence |

An execution payload is validated against the selected capability's registered schema. Do not invent a universal adapter payload before an opportunity and its capability interfaces are selected.

Target experiment request:

```json
{
  "population_id": "01c78c2a-b9ab-4b13-8f08-f3a5ef777c84",
  "product_version_id": "bdab604d-ee41-4afc-9b69-d0a3af4b81ef",
  "task_set_id": "faeb16d2-e941-46ad-85c9-9e4e23308e50",
  "mandatory_trial": true,
  "optional_continuation": false,
  "browser_concurrency": 4
}
```

## Generated contracts

```powershell
python -m backend.scripts.export_openapi
npm --prefix frontend run generate:api
npm --prefix frontend run check:contracts
```

Do not edit generated TypeScript manually. A coordinates: propose change → identify consumers → approve → update Pydantic → export and regenerate → update fixtures → verify → notify owners. Prefer additive changes. Feature routers and their tests stay feature-owned; central mounts are coordinated once.



## Automatic research studies

- `POST /api/v1/research-studies`: `StudyRequest` (discovery, research_limit 1–6/default 3, optional interests) → 202 `ResearchStudy`; starts discovery/research/proposals/equivalent searches/critic automatically. Live mode requires configured HF and an approved budget; fixture mode calls no external services.
- `GET /api/v1/research-studies/{id}`: progress/report, 404 after restart/eviction.
- `POST /api/v1/research-studies/{id}/cancel`: cancel pending work, retaining completed evidence.

One active study per API process; another start returns 409. A 15-minute bound and 100-record memory retention apply. RepositoryResearch contains pinned source evidence, explanatory brief, research status/coverage/failure and discovery/supporting-tool origin. EvaluatedProduct contains proposed substantial use, original-use difference, illustrative examples/checks, automatic AlternativeSearch evidence, scope/novelty CritiqueOutput and recommended_for_prototype/research_needed/rejected status. Recommendations are not approved capabilities or uniqueness guarantees. No prototype/persona execution follows automatically.
