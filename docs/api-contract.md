# API contract

The backend Pydantic models in `backend/app/shared/contracts.py` and exported `shared/openapi.json` are authoritative for implemented routes, exact fields, enums and validation. Generated frontend types live in `frontend/src/shared/api-types.ts`. The target production table does not mean every endpoint is implemented by the scaffold. Inspect `/openapi.json` before consuming a route. A fixture-backed read route is not a durable production workflow.

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
| `POST /api/v1/patch-runs/{id}/approve` | Always `409 REVIEW_REQUIRED` in starter; no patch is promoted |

Owners may add bounded starter routes while development proceeds; the generated OpenAPI remains current truth.

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
| A | `POST /proposals/{id}/checks` | Proposal → research/feasibility job |
| A | `POST /integration-runs` | Proposal/fixture references → validation job |
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

An execution payload is validated against the selected capability's registered schema. Do not invent a universal adapter payload before the pair is selected.

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

