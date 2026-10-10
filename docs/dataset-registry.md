# Dataset and evidence registry

Sources below are candidates from the briefs, not a claim of current retrieval or verified access. No dataset has been established as ingested by this skeleton. Verify current links, licenses, exports and vintage when implementing adapters.

| Source | Metric and fields | Transform / consumer | Quality and priority |
| --- | --- | --- | --- |
| GitHub REST repositories | Repo ID/name, stars, topics, license, default branch, commit, README | Preserve source IDs and commits; A discovery/capabilities | P0. Rate limits, missing licenses, docs may be stale. Stars indicate Popular, not Trending. |
| Cached GitHub Trending snapshot | Listed repositories, language/period, retrieval timestamp | Preserve exact snapshot and discovery mode; A | P0 when Trending is used. Not interchangeable with star sorting. |
| GitHub issue samples | Issue number/body/state/time, linked capability evidence | Bounded capability/problem extraction; A | P0. Sample bias and model interpretation must remain visible. |
| Existing-solution searches | Query, URL/title, retrieval time and similarity findings | Exact pair and equivalent-purpose records; A | P0. Empty search is not proof of novelty. |
| UCF Common Data Set / IPEDS | Published student cohort counts/definitions and academic year | Preserve published categories/vintage; B cohort context | P1 enrichment. Do not invent unavailable joint distributions. |
| UCF reporting library | Accessible staff/faculty aggregate counts and vintage | Document raw-to-canonical categories; B | P1. Mark restricted/unavailable exports. |
| ACS five-year estimates | Regional population, age/employment/household estimates, uncertainty, geography | Preserve estimates and denominator; B context | P1. Geographic and vintage mismatches; no unsupported 20-mile reconstruction. |
| Scenario configuration | Role, skill/device/time constraints, fictional locations | Explicit assumption IDs; B planner/world | P0. Intentionally balanced coverage; fictional traits never become observed demographics. |
| Reddit software reviews/discussions | Stable post/comment ID, original permalink, publication/retrieval dates, software context, normalized-content hash, bounded paraphrase | B review corpus → evidence-linked behavior patterns; HF extraction after access/reuse verification | P0 behavior source candidate. Approved access/export required; unavailable source is explicit. Self-selection, deleted posts and context limits; no review-author demographics. |
| Hacker News software discussions | Item/comment IDs, parent/thread context, timestamps, permalink and deletion/dead state | B bounded official-API collection → canonical review evidence and behavior | P0 behavior source candidate. Developer audience and thread selection are biased; opinion is distinct from self-reported use. |
| General software reviews | GitHub issues, app-store/review-site reviews or public forums; original ID/URL/dates/context/hash | B source-specific permitted adapters/exports → common review schema | P0 alternative/complementary sources. Verify relevance and access; deduplicate copied content and disclose selection. |
| Playwright evidence | Executed action, product output, deterministic outcome, timestamp | Session-linked evidence; B → C | P0. Retries and missing observations retained; screenshots outside Neon. |

## Source URLs

- [GitHub repositories API](https://docs.github.com/en/rest/repos/repos)
- [GitHub Trending](https://github.com/trending)
- [Official Hacker News API](https://github.com/HackerNews/API)
- [Reddit data access overview](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)
- [Reddit Data API wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [UCF Common Data Set](https://analytics.ucf.edu/institutional-research/common-data-set/)
- [UCF IPEDS](https://analytics.ucf.edu/institutional-research/ipeds/)
- [UCF reporting library](https://analytics.ucf.edu/data-literacy/reporting-library/)
- [ACS API](https://www.census.gov/programs-surveys/acs/data/data-via-api.html)

## Adapter acceptance

Review collection/extraction is not implemented by the schema. Follow [software behavior](software-behavior.md): preserve review reports separately from derived behavior, validate every citation against actually collected content, and freeze the corpus before v1/v2. Corpus selection/deduplication/source mix is explicit; review frequency or votes must not become a human-population estimate. Real reviews inform persona preferences; actual session actions remain the evidence for generated-product feedback.

Store source publication/retrieval dates, units, geography and category definitions. Validate duplicates, missing values and denominator consistency before generating personas. Record raw fields and transformations. Keep observed facts separate from inference and synthetic details. Each source adapter supplies a small known fixture and a missing-data case; consumers use canonical records without embedding source-specific transformations.

