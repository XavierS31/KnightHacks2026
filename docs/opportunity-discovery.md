# Emerging open-source opportunity discovery

User-approved product revision, 2026-10-10. This supersedes requirements to always pair two repos in historical briefs and earlier A selection notes. RepoFusion serves a developer who does not yet know what to build. It discovers promising projects and evidence-backed opportunities to extend them, then tests a selected example. It does not require the developer to supply a problem statement.

## Current automatic flow — revision 2026-10-10

The user rejected the manual anchor inspector and routine issue-driven feature suggestions. The default UI is now one **Discover & research** action. It automatically discovers candidates, reads pinned source docs/interface manifests, produces explanatory repo briefs, proposes substantial new uses of the underlying technology, researches equivalents and critiques product scope. No manual source paths, anchor selection, supporting-repo checkboxes or second inference button appear in this flow.

Research aims for a materially different audience/workflow, including uses not intended by the original creators. A proposed extension must amount to a substantial new product; cosmetic changes, small issue fixes, generic wrappers and existing capabilities are rejected. Issues are not collected in automatic studies. The existing manual APIs are retained for compatibility, not used by the main dashboard.

## Historical anchor workflow (superseded in the main UI)

1. Find emerging repositories. Star/fork attention is a candidate signal, not demand evidence.
2. Inspect an anchor's documented capabilities, current users/problems and limitations. Preserve commits and collection-time issue states.
3. Suggest a specific useful feature/workflow, or an integration with necessary complementary tools. A second repo is optional; return no opportunity when the evidence is weak.
4. Investigate equivalent solutions, issue currency/linked PRs, actual interfaces, licensing and effort. Source citations resolve facts; they do not automatically establish semantic support or value.
5. Show an explicitly illustrative input/outcome preview. A simulated preview cannot pass integration correctness gates.
6. Select one opportunity; independently execute its source tool(s), implement a narrow real prototype, validate fixed checks and freeze the normal A product manifest/task handoff.
7. B runs relevant synthetic browser trials against that validated product. C aggregates evidence, proposes bounded improvements, and retests a human-approved v2 while preserving v1.

Examples and persona trials investigate hypotheses. Real execution can establish sample correctness; synthetic opinions cannot prove adoption, demand or profitability. An unhelpful opportunity is a valid rejection, not a reason to manufacture positive feedback.

## Earlier implemented discovery slice (retained compatibility)

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

Bounded GitHub equivalent-product research is now implemented in automatic studies. Full-web/commercial-product novelty coverage, release/contributor enrichment, durable Neon study storage, growth-ranked discovery, automated prototype generation and a new selected-opportunity simulation remain unimplemented. The new UI exposes these gaps rather than treating a model suggestion as a validated product. The existing source executor/manifest, B browser runtime and C evolution pipeline are reusable once a new selected prototype passes their established contract.


## Automatic study implementation and limits

`POST /api/v1/research-studies` accepts a DiscoveryRequest, research_limit (1–6, default 3) and optional interests, returns 202 immediately, and automatically starts the pipeline. Defaults discover and research three candidates. Larger pools (up to 30) are explicit; candidates beyond the research limit are labeled not researched. `GET /research-studies/{id}` exposes current progress/report; `POST /research-studies/{id}/cancel` retains completed evidence and cancels pending work. One study runs per API process, bounded to 15 minutes and 100 retained records. Reloading the browser reconnects to the job; API restart loses memory state and never silently restarts paid requests.

Source research reads the pinned README/license, root contents and optional docs index, selects up to two relevant local docs plus one root interface manifest, and never executes source code or fetches routine issues. Repo briefs explain original purpose, distinctive mechanism, inputs/outputs, usable interfaces, portability/coupling and evidence. GitHub taglines stay metadata, not final summaries. Interpretations are not independently approved capabilities.

One HF phase proposes zero to two substantial products (preferring one) across researched capabilities. Necessary old/new supporting tools can be suggested and are automatically source-researched before recommendation. Another phase independently critiques product scope/interface assumptions and alternatives. Minor features, already-present functions, unsupported reuse and close equivalents are rejected. Failed/unread alternatives remain inconclusive. All calls use B’s shared HF adapter and A’s existing reservation guard; no paid persona experiment is launched. Worst-case logical calls are research_limit + 1 generator + 4 supporting briefs + 2 critics (up to 13); every request, including failed/rejected output, reserves two cents against the existing A cap. No allowance increase is made by this revision.

For each proposed product, two purpose-based GitHub queries search names/descriptions/READMEs without emerging/date/star restrictions, returning at most two projects each. Matched READMEs are pinned and inspected automatically. These are limited open-source searches, not comprehensive web or commercial-product research. No-close-match findings never guarantee uniqueness. Source citations must resolve; semantic support, value, feasibility and usefulness remain hypotheses pending developer review and real prototype checks.

The final report separates researched repo summaries, products recommended for a prototype, rejected/inconclusive ideas, illustrative input/outcome/checks, search evidence, failures and limitations. Generator enthusiasm is not the executive verdict: final text reflects the actual critic results. B/C consume only the existing validated product handoff after a selected prototype is built and checked, not this research report.


After integrating current master persistence, automatic studies use the existing DiscoveryRepository for live discovery runs and SourceStore.add for pinned snapshots when a database is configured. Suggested external tools receive an actual bounded metadata discovery run before their source snapshot is stored; no invented zero-star metadata is persisted. Storage failures remain visible and do not silently fall back to successful writes. The new study job, briefs, product hypotheses and critiques themselves remain process-local; no new migration or durable study claim is introduced.
