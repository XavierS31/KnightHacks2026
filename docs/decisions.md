# Decisions and dependency register

Accepted on 2026-10-10 from the latest user instructions and revised plan. New decisions record owner, rationale, affected contracts and evidence; original briefs remain historical inputs.

| Decision | Rationale / owner |
| --- | --- |
| Exactly three full-stack product phases | A integration; B personas/world; C feedback/improvement. User-requested ownership |
| HF Inference Providers is the sole runtime inference integration | No self-hosted GPU inference or hardware reservation. B owns adapter |
| Neon powers persistent production state | C owns database/migrations; fixture state is explicitly temporary |
| One FastAPI app and React/Vite dashboard | Keeps handoffs small and independently owned feature modules |
| Pydantic/OpenAPI → generated TypeScript | One canonical schema; A coordinates changes |
| Four browser contexts initially | Local resource/provider benchmark before increasing. B |
| 500 personas per version, ten visualized | Mandatory execution count is distinct from the world and population setup. B/C |
| Six actions mandatory; eight optional-task actions | Protects coverage capacity; early verified success/blocking failure stops. B |
| Balanced synthetic coverage | Dataset access unverified; no representative-human claims. B |
| Required review-informed persona software behavior | User requirement: real software-review reports inform tendencies/triggers/trial policies with source lineage; separate from demographic enrichment and executed defect evidence. Schema/fixture/viewer implemented; collection/extraction open. B, with C storage |
| Human review before v2 promotion | Runtime implementer cannot approve itself; A/C |
| Separate product origin/process, Docker target | Integration/browser isolation; A/B |
| Local artifact bytes, Neon metadata | Keeps DB small and replay traceable. B/C |
| No external publication by kickoff alone | Work is local scaffolding/development; deployment requires human authorization |

## Open bounded gates

| Gate | Owner | Resolve through |
| --- | --- | --- |
| Selected repo pair | A | Candidate evidence, independent execution, narrow adapter fixture acceptance |
| Search access | A | Available search provider or manually recorded searches; retained uncertainty |
| HF token/model/provider/spending limit | B | Server-side config and representative smoke evaluation; no automatic paid full batch |
| Neon connection | C | Configured TLS Postgres connection and migration round trip |
| Docker/deployment machine capacity | A/B | Availability plus resource measurements, rather than assumed installation |
| Source exports and geography | B | Accessible aggregate sources/vintages; explicit assumptions when absent |
| Real review corpus and supported behavior extraction | B/C | Permitted Reddit/HN/general collection, deduplication, checked citations/context, HF extraction and frozen corpus/profile persistence; schema fixtures do not satisfy this gate |
| Real developer names/GitHub handles | Humans | Map logical A/B/C owners; add CODEOWNERS only with valid accounts |

These gates do not block independent fixture-backed development. They do block claims of live execution, completed production persistence, true integration or full experiment coverage.

