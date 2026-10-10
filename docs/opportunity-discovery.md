# Emerging open-source opportunity discovery

User-approved product revision, 2026-10-10. This supersedes requirements to always pair two repos in historical briefs and earlier A selection notes. RepoFusion serves a developer who does not yet know what to build. It discovers promising projects and evidence-backed opportunities to extend them, then tests a selected example. It does not require the developer to supply a problem statement.

## Product flow

1. Find emerging repositories. Star/fork attention is a candidate signal, not demand evidence.
2. Inspect an anchor's documented capabilities, current users/problems and limitations. Preserve commits and collection-time issue states.
3. Suggest a specific useful feature/workflow, or an integration with necessary complementary tools. A second repo is optional; return no opportunity when the evidence is weak.
4. Investigate equivalent solutions, issue currency/linked PRs, actual interfaces, licensing and effort. Source citations resolve facts; they do not automatically establish semantic support or value.
5. Show an explicitly illustrative input/outcome preview. A simulated preview cannot pass integration correctness gates.
6. Select one opportunity; independently execute its source tool(s), implement a narrow real prototype, validate fixed checks and freeze the normal A product manifest/task handoff.
7. B runs relevant synthetic browser trials against that validated product. C aggregates evidence, proposes bounded improvements, and retests a human-approved v2 while preserving v1.

Examples and persona trials investigate hypotheses. Real execution can establish sample correctness; synthetic opinions cannot prove adoption, demand or profitability. An unhelpful opportunity is a valid rejection, not a reason to manufacture positive feedback.

## Implemented discovery slice

- Emerging uses GitHub search, sorted by total stars, with default created >= 90 days ago and pushed >= 30 days ago. Users can override dates. This is a recent/active candidate pool, not a measured growth ranking.
- Popular remains star-sorted; Trending remains a timestamped GitHub Trending page snapshot. Neither is renamed as measured momentum.
- Search collects stars and forks when supplied. Trending currently supplies stars with fork count unknown. A-owned `artifacts/integration-momentum.json` atomically retains up to 100 repos × 8 observations across local restarts. Locks/corruption fail visibly; cached timestamps do not create growth. Fixtures never enter history.
- Compare net star/fork counts with the earliest retained observation at least one minute earlier within 30 days. Show baseline/current timestamps, source references and interval. Negative changes are preserved. First reads show insufficient history. Releases, contributors and historical star-event backfill are not implemented.
- Source collection remains fixed-host/read-only, commit-pinned, size-bounded and nonrecursive. Sampled issue state/update metadata is retained. Issue comments, discussions, releases and linked PR inspection remain a research gate.
- Opportunity generation consumes one anchor snapshot plus zero to two inspected supporting snapshots, using B's shared HF adapter and A's existing bounded budget. Opportunity requests use at least a 60-second per-attempt timeout; shared B/C defaults remain unchanged. It samples across docs and issues, supports feature extensions/integrations, and allows abstention. Optional interests constrain discovery; no problem statement is required.
- Server attaches exact supplied evidence excerpts/URLs and rejects unknown citation IDs, wrong-anchor needs, invented supporting repos, unsupported pair roles and forced second-repo extensions. Citation support still requires review.
- Dashboard shows problem/audience/current/proposed value, why investigate, implementation boundary, uncertainty, evidence, illustrative input/output/check, pending gates, shortlist/reject with a reason, and JSON export. Reports/decisions are bounded in memory and lost on restart/eviction; export preserves hypotheses, not a validated briefing.
- Existing pair APIs remain compatible for consumers and historical records. They are not the default new UI. SourceTable's frozen v1 and B/C consumers remain unchanged as an earlier experiment.

## Cross-owner handoff

A owns discovery, momentum fallback, opportunity contracts/UI and selected prototype. Additive Pydantic models live within the integration feature and are exported into OpenAPI/generated TS. No change is required to B/C's existing ProductVersion, ProductHandoff, browser checks or retest schemas.

B: a future selected opportunity must be converted into the existing immutable, validated product manifest, factual briefing, initial state and fixed checks. An OpportunityReport alone must not be used as verified capabilities, a trial launch or a completed session. Persona selection should reflect the audience/problem, not be steered toward favorable feedback. No B runtime code is rewritten here.

C: serialize any new Neon migrations after consumer review. Needed persistence concepts are repository observations (repo/time/stars/forks/source), opportunity reports (anchor commit/snapshots, type, optional support repos, problem evidence, inference lineage), reviews/decisions, research results and links to a subsequently validated product version. Keep hypotheses, illustrative previews, executable validation and trial results separate. This slice writes no new Neon schema and claims no Neon roundtrip. JSON export/local count history are explicit temporary storage.

## Remaining gates

Automated existing-solution research, current-issue/PR verification, release/contributor enrichment, durable Neon opportunity storage, growth-ranked discovery, automated prototype generation and a new selected-opportunity simulation are not implemented. The new UI exposes these gaps rather than treating a model suggestion as a validated product. The existing source executor/manifest, B browser runtime and C evolution pipeline are reusable once a new selected prototype passes their established contract.
