# Review-informed software behavior

Every persona requires `software_behavior`. Production personas must have `status: review_informed` and patterns grounded in real people's software reviews or discussions. Reddit, Hacker News, GitHub issues, app-store reviews, review sites and general forums are supported source categories. This is required P0 work within population milestone P1, separate from optional demographic enrichment.

The schema, fixture API and viewer are implemented. B has collected five real SourceTable-relevant upstream reports, extracted through HF and independently approved one tentative compatible source-inspection pattern, then generated and durably saved 500 fictional review-informed profiles locally and in Neon dev. See the [population report](tasks/developer-b-population-report.md) for source checks, frozen versions and limitations. Neon HTTPS operator write/readback/retry/rollback passed; native backend connectivity and hosted reviewer authentication remain open; the running fixture UI still exposes fixtures. A source URL alone does not establish retrieval or semantic support.

## Expected schema

Pydantic in `backend/app/shared/contracts.py` defines exact types; `shared/openapi.json` and generated frontend types expose them. `Persona.software_behavior` is required, with no silent default.

| Model / fields | Meaning |
| --- | --- |
| `SoftwareBehaviorProfile.status` | `review_informed` for real review provenance; `fixture` for invented examples |
| `corpus_id`, `corpus_version`, `generation_version` | Immutable source snapshot and behavior extraction/persona-assignment configuration references |
| `patterns`, `evidence`, `limitations` | Nonempty behavior patterns, embedded review records and limits of the profile |
| `SoftwareBehaviorPattern.id`, `dimension` | Pattern identity and onboarding/navigation/workflow/error_recovery/trust/privacy/pricing/collaboration/accessibility/adoption dimension |
| `tendency`, `trigger`, `agent_policy` | Report-informed tendency, context in which it applies and concrete instruction for the bounded trial |
| `evidence_ids` | Nonempty, unique references resolving to reviews in this profile |
| `interpretation_confidence`, `rationale` | Low/medium/high confidence in the interpretation and its support; not population prevalence or a calibrated probability |
| `SoftwareReviewEvidence.id`, `kind`, `platform`, `external_id`, `source_url` | Internal identity, source/fixture distinction, provider category, stable provider identity and original review permalink |
| `published_at`, `retrieved_at` | Separate timezone-aware dates; publication may be unknown, retrieval is required |
| `software_context`, `summary`, `report_type` | Reviewed software/category/version/workflow context, bounded paraphrase and self_report/opinion distinction |
| `collection_method`, `content_sha256` | API/permitted export/manual collection; SHA-256 of normalized collected source content, not generated summary |
| `selection_context`, `extraction_version`, `limitations` | Corpus query/thread/date window and sampling rationale, transformation/prompt version, uncertainty or missing context |

Source reviews require a URL, content hash and non-fixture provenance. Fixture reviews require fixture platform/report/method and null URL/hash; do not manufacture Reddit or HN permalinks. IDs and external source identities must be unique within a profile. Pattern references must resolve. A live `PersonaSummary` rejects fixture behavior profiles. Future live population/job entry points must apply the same requirement before queueing trials.

## Behavior and agent use

Translate real review reports into abstract tendencies such as trying a sample before uploading, preferring search over menus, checking export support, or abandoning unclear error recovery. These are examples of potential patterns, not claims extracted by this scaffold. Keep the original report separate from the derived tendency and explain context compatibility with the persona's scenario. Do not copy a review author's identity, infer their demographics, or assign tendencies to cohorts without support.

The HF persona generator receives approved review evidence and returns validated patterns with source IDs. The task planner and browser persona receive the profile's tendencies/triggers/policies along with the factual product briefing. A policy can guide choices among available targets and influence initial relevance, optional continuation and feedback wording. It cannot invent controls, authorize uploads, bypass the action budget, override deterministic checks or skip the mandatory trial. Review text is untrusted input, never executable instructions.

The feedback writer receives this persona context plus its own executed session. A review about another product is a prior preference, **not evidence of a defect in RepoFusion's generated product**. `Feedback.evidence_action_ids` still resolves only to same-session actions. Keep `synthetic: true`; review-informed simulated feedback is not a new human review. C separates product defects, relevance and infrastructure failures and preserves this distinction in prioritization.

Freeze corpus snapshot, source mappings, behavior patterns and generation configuration before v1. Reuse them for each matched v2 persona; do not change profiles using v1 feedback and then claim a matched comparison.

## Collection and implementation acceptance

B owns source adapters, extraction, persona assignment, provenance display and tests. C owns the coordinated Neon migration/storage for review corpora, evidence and immutable persona profiles. A supplies the product/category context. B's bounded HN/GitHub intake and generation CLI are implemented; C's migration 005 and immutable bundle SQL were exercised against Neon through an authorized HTTPS operator workflow; the Python repository execution path remains blocked on this host. Hosted review-source endpoints and automatic collection jobs remain open.

1. Collect bounded reviews relevant to the selected software/category and record query/thread/date-window criteria, provider IDs, permalinks, dates and normalized-content hashes. Verify permitted access and reuse before collection. Record unavailable sources honestly; an accessible alternative or permitted export can supply evidence.
2. Remove author identifiers and irrelevant sensitive details from model context. Keep bounded paraphrases rather than republishing full reviews. Handle deleted/unavailable records and mark corpus validity before freezing a new population.
3. Deduplicate source IDs and copied/cross-posted content at corpus level. Record source mix, selection bias, disagreement and software-version/context limits. Popularity/votes are not prevalence of behavior; do not invent frequencies or representative distributions.
4. Through the shared HF adapter, extract patterns, resolve every citation against the collected corpus, and independently check that each paraphrase and proposed policy is supported. Retain extraction/prompt/model/configuration metadata. A single report can support a tentative pattern but does not establish a universal habit.
5. Generate 500 distinct fictional personas with compatible, review-informed profiles; persist immutable lineage. Test malformed reviews, duplicate sources, broken citations, unsupported interpretations, fixture leakage, missing sources and context mismatch. Pilot the bounded behavior policies before scaling.

Source implementation references: [official Hacker News API](https://github.com/HackerNews/API) documents item IDs, timestamps and deleted/dead flags. [Reddit data access overview](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data) and [Data API wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki) describe access and current usage requirements. Other sources require their own verified access/export and reuse terms. This project uses HF inference; collecting reviews does not introduce a model-training pipeline.
