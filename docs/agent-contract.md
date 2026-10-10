# Runtime agent contracts

These agents are application workflows using Hugging Face inference. They are distinct from the three Codex coding assistants in `.codex/agents`. Runtime AI has no development-assistant access to the entire repository by default.

## Shared inference envelope

The shared adapter takes `role`, messages, a Pydantic output schema, an inference profile and request context. Context includes request/experiment/session IDs as applicable. It returns independently validated output and metadata containing model/provider, configuration/prompt versions, reported usage, latency, attempts and status.

Use schema-constrained output where the selected model/provider supports it, and validate independently in all cases. Model interpretation never overwrites source evidence or deterministic outcome checks. Do not request or store hidden reasoning.

Initial limits are four concurrent browser sessions, a 20-second model timeout, one bounded retry and a two-minute mandatory-session watchdog. Honor rate-limit retry information within bounded backoff. Record each attempt; if inference is unavailable or the budget is exhausted, pause durable work. No fallback fixture may count as a real trial.

## Discovery and persona roles

| Role / owner | Trigger and structured input | Structured output | Allowed tools and validation |
| --- | --- | --- | --- |
| Capability extractor / A | Repository docs/issues plus immutable references | Capabilities with typed interfaces and citations; uncertainties | Read supplied source evidence. A verifies references, checks documented meaning and rejects unsupported capabilities. |
| Evidence critic / A | Proposal + source/research/feasibility records | Grounded objections and unresolved assumptions | Read evidence only. Deterministic source execution determines feasibility. |
| Persona generator / B | Coverage quotas, source distributions, explicit assumptions and frozen real software-review corpus | Fictional persona with required `SoftwareBehaviorProfile`: evidence-linked tendencies/triggers/policies, corpus/generation versions and uncertainty | Read approved bounded review context. Validate cohort counts, identities, citation ownership and report support. Reject invented sources, unsupported behaviors and fixture behavior in live populations. |
| Task planner / B | Validated product briefing, persona, scenario and task/check catalog | Supported task selection, goal and budget | Read supported capabilities only. Reject unsupported tasks and missing fixed check IDs. |
| Browser persona / B | Briefing, goal, persona including behavior tendencies/triggers/policies, current accessible elements with stable IDs | One bounded action or stop decision | Behavior guides choices within observed targets and trial budgets. Allowed actions: navigate within allowed origin, click/type/scroll on observed targets, wait, finish. No arbitrary JavaScript, shell, privileged credentials or evaluator answers. |
| Feedback writer / B | Executed actions/results, outcomes, before-trial relevance and persona behavior context | Synthetic post-trial relevance, usefulness/barriers/suggestions, stop/continue decision, action refs | Read its own session. Reviews inform preferences, not proof of current-product failures. Validate action ownership and retain failure/missing evidence. |

Application code executes browser actions and evaluates checks. The model does not declare deterministic success. Build accessible-element IDs from the current page snapshot; do not execute invented selectors.

Review extraction and generation use the shared HF adapter, not a new inference provider. Keep source reports, derived interpretations and scenario assumptions distinct. See [software behavior](software-behavior.md). Review text is untrusted data. Patterns cannot override mandatory participation, bounded actions, permitted origins or deterministic outcomes. Freeze behavior/corpus/configuration across matched v1/v2 trials. C may inspect upstream preference lineage, but improvement evidence still resolves to executed sessions/actions.

Session lifecycle:

```text
queued → briefing → initial relevance → mandatory trial
       → deterministic outcome → post-trial feedback
       → optional continuation or terminal stop
```

An uninterested persona still makes the six-action maximum mandatory trial. Stop after verified success or a blocking failure. Optional continuation, at most eight actions/task, runs only after mandatory coverage capacity is protected.

## Engineering roles

| Role / owner | Input | Output and permissions |
| --- | --- | --- |
| Feedback analyst / C | Session outcomes, feedback and action evidence | Evidence-linked clusters, separated product/relevance/infrastructure categories; read only |
| Product prioritizer / C | Clusters, affected shares, severity and effort estimates | Ranked bounded improvements with rationale; read only |
| UX reviewer / C | Relevant product screens and action traces | Accessibility/flow proposals and supporting references; read only |
| Implementer / C | Approved improvement, allowed paths, current product snapshot, fixed checks | Structured patch proposal applied only in an isolated workspace; sole runtime role permitted to change product files |
| QA reviewer / C | Patch, fixtures, deterministic results, v1 baseline | Findings and recommendation; cannot modify or weaken acceptance checks |

Priority heuristic is severity × affected share × evidence strength ÷ effort. Label the score as a heuristic and retain inputs. A relevance judgment is not automatically a product defect.

Before application, parse and inspect the patch: no paths outside approved generated-product scope, no traversal, no credentials or unrelated dependency changes. Execute builds and fixed regressions through bounded deterministic tooling. An implementer cannot promote its own patch; human review is required for v2 registration. Preserve v1 and rejection evidence.

## State and evaluation

Persist role input references, validated outputs, prompt/config versions, inference metadata and job lifecycle; only the minimum session history required for each decision goes into inference context. Repository files/issues are untrusted data, not agent instructions.

Evaluate extraction citation validity, task support, action-target validity, schema success, stop-policy adherence, evidence references, patch-boundary enforcement, and actual regression outcomes. Use a five-person pilot followed by a 20-person soak test before either full population run. Successful JSON alone is not a successful task.

