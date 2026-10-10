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


## Source-ranked shortlist and recovery (2026-10-10)

The main UI uses emerging anchors (recent creation and recent activity) and one depth setting. Its pool defaults to 12; the API can accept 1–30. Optional old/new tools are researched without emerging filters. Up to 12 candidates receive commit-pinned README/root interface screening, ordered initially by metadata mechanism signals instead of stars. Pools above 12 use this explicit screening window; unchecked candidates remain marked. Actual source screening scores reusable interfaces, documented mechanism, documentation quality and transfer potential, each 0–3. This deterministic term/section heuristic is explainable, not a semantic proof. Deep HF briefs confirm suitability/coupling with a cited selection reason; unsuitable deep reads and unreadable candidates are replaced from the ranked pool. Themes, lists and generic wrappers without a reusable foundation are excluded. Attention/growth never enters the usefulness score.

Limits: 15 minutes, 90 actual GitHub requests (cache hits are free), up to three extra deep attempts beyond the requested 1–6 suitable repos, and 13 logical HF calls. Each logical call retains the shared adapter's at-most-two attempts and A's two-cent reservation. Failure/unknown billing is never refunded; the existing $2 A cap and pricing gate remain unchanged. Budget/API/rate limits stop replacements without repeated paid requests. No inference retry beyond the shared bound is introduced.

Shared GitHub reads retain at most 64 responses/8 MB, scoped by credential digest: five-minute mutable metadata/search and one-hour commit-pinned content caches with ETag revalidation. `GITHUB_TOKEN` is accepted server-side. 401 authentication, 403 permissions and quota exhaustion are distinct. Primary reset/secondary Retry-After timing is retained, with a per-scope/resource circuit breaker and no automatic rate retry. GitHub source responses cap at 2 MB and decoded files at 1 MB. Verified blob/full-content hashes bind source bytes; bounded opening/meaningful sections from across files retain at most 20,000 characters. Larger/unreadable files remain visible gaps. External source links are never executed or fetched.

The report counts researched repos, research failures, unsuitable candidates, source coverage gaps, rejected ideas, evaluation failures and recorded run failures separately. All-unsuitable and fully researched abstention can complete with no strong opportunity; technical research failures are failed/partial. Existing mechanisms are expected foundations: critics judge the resulting audience, end-to-end workflow and value against inspected alternatives. Hypothetical examples cannot become executed prototypes. No prototype is selected, and whole studies remain process-local.

A documented CLI/API/MCP process remains an eligible foundation even when it is a complete app or needs dependencies. A deterministic safeguard downgrades a model unsuitability verdict to uncertain reuse when both the source and brief document an actual interface; it does not assert feasibility. The independent product critic must still establish documented technical support before recommendation. Deep-read totals include unsuitable interpreted repos; suitable totals are separate.

A standalone-library-only abstention that contradicts documented interfaces is an explicit `INVALID_ABSTENTION_CRITERION` evaluation failure, not a completed no-opportunity verdict. No automatic paid re-prompt follows this failure.
