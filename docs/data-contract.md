# Data contract

Pydantic models in the backend are authoritative; consult the exported OpenAPI for exact current fields and enums. This document defines semantics that schema validation alone cannot establish. Production persistence is planned; fixture storage does not substantiate a Neon integration.

## Shared rules

- Internal identifiers are UUIDs; external repository/source IDs remain distinct.
- Use UTC ISO 8601 timestamps and durations in milliseconds. Preserve source publication/retrieval dates separately.
- Product commits, task sets, population configuration, prompt versions and inference settings are immutable experiment references.
- Null means unavailable/not observed, not zero. Keep evidence references and uncertainty with every derived result.
- Distinguish sourced facts, derived values, estimates, model interpretations, assumptions, fixtures and observed execution.
- Credentials, screenshot bytes and model hidden reasoning do not belong in domain rows or client responses.

## Principal records and lineage

| Record | Required meaning | Producer → consumers |
| --- | --- | --- |
| Repository/evidence | Repository identity, source commit, documented capability and cited location | A → proposal and validation |
| Opportunity report/card | Anchor snapshot/commit, optional support snapshots, feature-extension/integration hypothesis, sourced or inferred need, audience/value, unresolved research, illustrative example and inference lineage | A → review/selection |
| Repository observation / momentum | Timestamped star/fork counts and comparable baseline; nullable net deltas and interval, never demand or adoption | A → discovery UI; C durable storage target |
| Opportunity decision | Card identity, shortlist/reject decision and reason; not capability validation or trial completion | A review UI → future C storage |
| Legacy proposal | Historical pair hypothesis and source/research references; retained for compatibility | A → historical inspection |
| Product version | Commit, URL, validated capability/check inventory, factual briefing | A/C → B/C |
| Software review / behavior | Original review ID/URL/dates/hash/context and bounded paraphrase → derived tendency/trigger/trial policy with resolvable citations, uncertainty and corpus/extraction versions | B → persona generator/planner/viewer |
| Persona | Fictional identity, roles/goals/constraints, attribute provenance and required review-informed software behavior | B → planner/viewer |
| Scenario | Active role/activity, fictional location/device/time budget | B → task/world |
| Task | Supported capability, goal, initial fixture state, evaluator check, version and budget | A/B → worker |
| Experiment | Population/version/task/config references and actual execution counters | B → C/dashboard |
| Session/action | Persona/task/version/attempt, executed action/result, sequence/time, artifact refs | B → viewer/feedback |
| Feedback | Before/after relevance, barriers, suggestions, continuation/stop reason, supporting actions | B → C |
| Improvement | Supporting sessions/actions, priority inputs, allowed patch scope and fixed checks | C → review |
| Comparison | Matched persona/task outcomes, denominators, exclusions and configuration changes | C → dashboard |

Source IDs and action references must resolve. An action attached to feedback must belong to its session. Persona/product records are session-scoped to prevent cross-persona contamination.

## Opportunity semantics and storage handoff

See [opportunity discovery](opportunity-discovery.md) and the [additive API interfaces](api-contract.md). `OpportunityRequest`, `OpportunityReport`, `OpportunityCard`, `OpportunityCitation`, `OpportunityDecision`, `Observation` and `MomentumSignal` live in A's integration feature; exported OpenAPI/generated TS define exact fields.

One anchor is required for live reports. Zero to two supporting snapshots are optional: `feature_extension` has none, `integration` requires supplied supporting repositories. `need_basis=issue_report` preserves an unverified report, not a confirmed missing feature; `inferred_workflow` explicitly marks interpretation. Evidence retains snapshot/repository/commit, excerpt/reference, collection time and sampled issue state. File sources are commit-pinned; issue state is collection-time metadata, not an immutable commit fact. Comments/discussions/linked PRs and current resolution still need investigation.

Novelty and feasibility remain unresolved/unreviewed; example input/output/acceptance checks are illustrative and unexecuted. A shortlist/rejection is a reviewer decision with a reason, separate from research results, prototype validation and B's executed trial evidence. Empty opportunity reports require an abstention reason. Invented demo records have fixture mode, no real anchor snapshot/commit and no research evidence.

Attention observations are timezone-aware counts. Measured signals compare the earliest retained observation at least one minute earlier within 30 days. Preserve negative net changes; missing forks/baselines yield null deltas. Status distinguishes `measured`, `insufficient_history`, `history_unavailable` and `fixture`. Cached source timestamps do not create new growth observations. Emerging search is recent/active and total-star-sorted, not a measured-growth ranking.

Current fallback storage: A's ignored `artifacts/integration-momentum.json` retains up to 100 repos × eight observations using atomic writes/locking. Reports/review decisions retain at most 100 reports in process memory and disappear on restart/eviction; dashboard JSON export is a hypothesis snapshot, not durable Neon persistence or a validated briefing.

C owns the future ordered migrations/repositories: persist observations with retrieval/source lineage, immutable report/source/inference payloads, separate review decisions and research findings, then an optional link to a validated product version. Do not overwrite original hypothesis evidence with later research or synthetic feedback. Observation includes an optional source_reference; durable storage must also retain enclosing discovery provenance and unknown source lineage in older observations. No new Neon opportunity tables or roundtrip are established here.

B receives only a subsequent validated immutable product handoff, factual briefing, initial state and fixed task/check inventory. Opportunity audience/problem can inform relevant personas, but neither model hypotheses nor illustrative examples authorize a trial or establish demand. Existing ProductVersion/ProductHandoff/session/retest identities and frozen SourceTable v1 remain unchanged.

## Population provenance

Track source URL/identifier, publisher, vintage, geography, raw-field mapping, transformations and coverage for observed distributions. Track an assumption ID and rationale for fictional attributes. Do not fabricate joint distributions by combining unrelated marginals. Do not sum UCF enrollment into regional population totals. A deliberately balanced population is a coverage test, not a population estimate.

## Software-behavior provenance

Review-informed behavior is qualitative provenance, separate from `attribute_provenance` demographic distributions and fictional attributes. See [software behavior](software-behavior.md) for exact nested fields, supported sources and validation. Production profiles cite real collected reviews; current fixtures cite only explicitly invented examples. Public self-reports/opinions are not instrumented human behavior, representative frequencies or evidence of a defect in our product. Feedback still cites only its own executed session actions.

## Completion and comparison

Maintain configured, queued, running, attempted, succeeded, failed, canceled and feedback-present counts separately. Mandatory coverage requires evidence-backed attempts and feedback for every configured persona on each version; success rate requires an explicit denominator. Missing/canceled work remains incomplete.

Freeze matched persona IDs, scenario IDs, software-behavior patterns/corpus/extraction versions, task goals, fixture/check versions, action budgets and inference configuration before v1. Reset application state between v1/v2 trials. Report optional continuation separately. Infrastructure/model failures receive their own category rather than being counted as product defects. Browser duration includes model/network latency and is not human completion time.

## Persistence target

Target feature-owned tables cover repository observations/repositories/evidence/opportunity reports/decisions/research/checks/versions (legacy proposals remain compatible); sources/review_corpora/software_reviews/populations/personas/scenarios/tasks/experiments/sessions/actions/feedback; clusters/improvements/retests/comparisons; jobs/inference requests/artifact references. Normalize shared review evidence and corpus membership; preserve immutable persona behavior JSONB with resolvable source IDs. Use foreign keys, relational identity/status fields and JSONB for structured payloads. C controls migration order. Review/persona persistence remains planned; the initial migration does not implement it. Schema additions follow the shared contract change process.

