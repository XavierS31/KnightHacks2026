# Full-stack ownership

The team consists of three human developers and their respective coding agents. Each owns frontend, backend, feature data, runtime prompts and tests for a single product phase. A is the integration/contract coordinator, not the author of everyone's backend.

| Responsibility | A: integration | B: personas | C: evolution |
| --- | --- | --- | --- |
| Frontend | Discover, Validation, Product, generated v1 | Population, Experiment, World, session viewer | Feedback, Evolution, review, comparison |
| Backend | GitHub adapters, capabilities/issues, research, feasibility, integration | Software-review adapters/behavior extraction, persona/scenario/task planning, sessions, worker execution, stream | Analysis, prioritization, patch workflow, regressions, retest/comparison |
| Owned paths | Both `features/integration` modules; `backend/tests/integration` | Both `features/personas` modules; `backend/tests/personas` | Both `features/evolution` modules; `backend/tests/evolution` |
| Shared stewardship | App shell, contract coordination, generated product | Shared Hugging Face adapter, browser jobs and streams | Database layer, migrations, CI |
| Produces | Evidence, proposals, validated capabilities, version briefing | Review corpus/behavior lineage, population, scenarios, tasks, sessions/actions/feedback | Clusters, improvements, reviewed v2, comparison |
| Consumes | Source docs, issue evidence, approved fixture cases | A's briefing/product/checks; C's retest request | A's manifests; B's outcomes and feedback |
| External services | GitHub and research | Hugging Face inference; permitted Reddit/HN/general review sources | Neon persistence including coordinated review/persona storage |
| First gate | Both repositories run independently | One persona executes and records a real task | Evidence-linked analysis and isolated patch state |
| P1 | Deeper existing-solution research | Richer source data, scenarios and world | Held-out checks and stronger analysis |
| P2 | More combinations | MapLibre, screencast, laptop textures | Additional improvement cycles |

## Protected shared files

The initial scaffold is created once. Later edits to shared contracts, central frontend/backend mounts, dependency manifests and environment conventions are coordinated with their steward. Feature owners can consume shared infrastructure immediately; they do not rewrite it to fit a local feature.

A reviews contract changes with consumers. C serializes database migrations from all owners. B coordinates inference adapter changes used by A and C. Generated API types are regenerated through the command, not edited by hand.

The evolution implementer can patch an explicitly approved generated-product area in isolation. This is a task-specific boundary crossing reviewed by A, not permission for C's normal feature work to edit integration internals.

## Coding-agent rules

Every task names objective, allowed files, prohibited areas, inputs, outputs, dependencies, checks and Done criteria. Inspect current files before editing. Use contract-compatible fixtures before upstream producers exist. Keep current fixture status visible; no credential-free scaffold may claim real Hugging Face or Neon execution.

Parallel coding-agent work must use disjoint files or separate worktrees. Do not reset another agent's changes. Do not send external messages, publish, push, or deploy without the human's authorization. Human review is required for product v2 promotion; completing local bounded coding work is already authorized.

Real GitHub owner handles have not been supplied. This file is the current ownership authority; configure CODEOWNERS once the humans identify valid accounts rather than adding invented accounts.

