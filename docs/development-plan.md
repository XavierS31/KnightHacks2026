# Development plan

## Local setup

Follow the root README for installed runtime prerequisites and startup. Keep credentials in the ignored local environment file, never frontend variables. Use fixture mode for offline scaffold work; live mode requires actual Hugging Face and Neon configuration.

Required verification commands, from repository root:

```powershell
python -m pytest backend/tests
python -m backend.scripts.export_openapi
npm --prefix frontend run generate:api
npm --prefix frontend run check:contracts
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

These commands target the scaffold under construction; check the root README/manifests for executable installation instructions. Re-export/regenerate only after coordinated contract edits. Frontend typecheck/build does not prove browser-worker or repository-integration behavior.

## Human and coding-agent kickoff

Use [coding-agents](coding-agents.md) to activate the role, then its self-contained starter task. Each developer owns both sides of their module. Start A/B/C concurrently after the baseline fixture shell is available. Do not wait for live credentials to implement contracts, views, bounded error paths and offline tests.

Initial milestones are: A's discovery/validation view, B's exact persona/session selector and world, C's feedback/evolution view. Their fixture-backed state is a visible baseline, not the actual full pipeline. Next replace each upstream fixture with a real producer at its gate.

## Branches and merges

Use `codex/integration`, `codex/personas`, and `codex/evolution` for normal feature branches. Use separate worktrees only when disjoint-file collaboration is insufficient; do not copy an uncommitted scaffold into competing branches. Never reset another developer's work. Preserve small verified checkpoints and review shared-boundary changes with their steward.

Each PR states resulting behavior, contracts changed, fixture/live status and performed validation. Merge small functional increments; do not save all integration for the end. Creating or publishing remote PRs requires the human's authorization.

## Production dependency gates

Population P1 also requires [real-review-informed software behavior](software-behavior.md): permitted source collection, checked evidence-linked extraction, contextual persona assignment and immutable corpus/profile storage. This is required independently of optional demographic enrichment. The schema/viewer fixtures do not establish source ingestion. Freeze behavior and corpus versions alongside tasks before the matched experiment.

Before full execution: select/validate an anchor opportunity and its source tool(s); verify Docker or an acceptable isolated execution environment; verify a served HF model's authentication/schema/action/patch behavior and available spending limit; connect Neon; test actual Chromium/session isolation; measure pilot throughput. If any gate is absent, report it and continue independent local work without fabricating results.

Before the complete comparison: freeze tasks/checks/configuration; finish v1 evidence; apply two or three reviewed patches; register immutable v2; execute matched retest; validate denominator calculations and failures. See the timed gates in [roadmap](roadmap.md).

