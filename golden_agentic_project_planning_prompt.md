> Historical planning input. The user-approved 2026-10-10 discovery revision is defined in [docs/opportunity-discovery.md](docs/opportunity-discovery.md). Repository pairing is optional; current ownership/runtime contracts govern implementation. The original text below is preserved for provenance.

# Golden Master Planning Prompt — Three-Developer Agentic Hackathon Workflow

> **How to use:** Append this entire file after your project idea / product requirements Markdown. Give the combined document to Codex in **Plan mode**. This is a planning prompt, not a request to implement code.

## 1. Role and Objective

Act as a **Senior Software Architect, Technical Lead, AI Systems Engineer, and Hackathon Project Manager**.

Using the project concept and requirements preceding this prompt, create an implementation plan for **three human developers working simultaneously with coding agents** such as Codex, Cursor, and Antigravity.

**Do not scaffold or implement the project yet.** Your first task is to define a stable architecture, interfaces, and execution plan that enables three developers to build independent, full-stack features with minimal merge conflicts.

Analyze which of these are actually needed: frontend, backend, public/private datasets, ingestion, calculations and simulations, AI agents and LLMs, external services, persistence, and interactive visualization. Do not add a subsystem unless the product needs it.

## 2. Engineering Priorities

Prioritize, in order:

1. **Working end-to-end product:** Deliver the primary user journey before optional features.
2. **Defensible output:** Trace material results to source data, transparent calculations, validated agent outputs, or explicitly labeled assumptions.
3. **Parallel full-stack development:** Divide work into three coherent feature-based vertical slices, not predetermined frontend/backend/data roles.
4. **Stable contracts:** Approve schemas, identifiers, APIs, agent I/O, dataset features, and error behavior before implementation.
5. **Striking user experience:** Build a polished, memorable, understandable hackathon demonstration.
6. **Minimal merge conflicts:** Assign clear file, feature, endpoint, and contract ownership.
7. **Simple architecture:** Favor reliable, lightweight technology and clear documentation.
8. **Hackathon feasibility:** Optimize for a small team's limited time, not production-scale infrastructure.

Avoid unnecessary graph databases, microservices, Kubernetes, Redis, queues, multiple databases, vector stores, complex orchestration, or premature optimization. Add them only if an identified P0 need genuinely requires them.

## 3. Understand the Product Before Dividing Work

First extract from the preceding project description:

- User problem, audience, value proposition, and primary demo journey.
- Core capabilities, user actions, outputs, and success criteria.
- Datasets, data points, geographic or temporal granularity if applicable.
- AI/agent workflows and their required tools and information.
- UI, APIs, business logic, calculations, persistence, and external integrations.
- Dependencies, uncertainties, feasibility risks, and deliberate exclusions.

Identify the major **user-facing features**, not just the technical layers. For each proposed feature, document its user outcome, front-to-back execution path, inputs, outputs, dependencies, interfaces, and tests. Identify shared infrastructure separately.

## 4. Dynamically Divide the Project Into Three Feature-Based Vertical Slices

**Do not predetermine developer roles. Do not assume one person owns all frontend, another all backend, and another all data or AI.** Analyze the actual product and determine the best division into **three independent, coherent, end-to-end feature workstreams**. Each developer owns their feature across the stack as required.

### 4.1 Select workstreams from the project itself

1. Identify the major user journeys and capabilities.
2. Trace what each capability requires from UI through API, domain logic, datasets, AI agents, and tests.
3. Identify shared foundational dependencies and cross-feature interfaces.
4. Estimate implementation effort, dataset difficulty, agent/tool complexity, frontend work, external dependencies, and integration risk.
5. Group related capabilities into **three balanced workstreams**. If there are more or fewer than three natural features, split or combine them into coherent ownership areas.
6. Ensure every P0 capability has **exactly one accountable human owner**.
7. Prefer workstreams that can make visible progress concurrently and deliver independently testable functionality.
8. Explain why the proposed division minimizes coordination overhead and merge conflicts.

Do not balance by feature count alone; balance by complexity, uncertainty, and expected engineering effort.

### 4.2 Full-stack responsibility per developer

Depending on the assigned feature, an owner may implement:

- Frontend views, components, and state.
- Backend services and API endpoints.
- Feature-specific database access or persistence.
- Data ingestion, transformations, calculations, or simulation logic.
- AI agents, prompts, tools, validation, and orchestration.
- Tests, fixtures, and feature documentation.

**One feature owner does not mean one separate application.** Keep a shared app shell, design system, backend application, contract definitions, and canonical identifiers wherever appropriate.

### 4.3 Shared foundation versus feature-owned implementation

**Shared foundation (created once, before branching):** repository skeleton, frameworks, app shell, design tokens/components, API conventions, canonical schemas and identifiers, generated types, configuration, shared fixtures/mocks, test/build tooling, basic integration flow, and `AGENTS.md` instructions.

**Feature workstreams (built in parallel afterward):** the approved vertical slices, each owned by a developer with explicitly scoped files and APIs.

```
                  APPROVED SHARED FOUNDATION
                            |
              +-------------+-------------+
              |             |             |
         DEVELOPER 1   DEVELOPER 2   DEVELOPER 3
         Feature A     Feature B     Feature C
         UI + API      UI + API      UI + API
         Logic/Data/AI as required for each slice
         Tests         Tests         Tests
              |             |             |
              +-------------+-------------+
                            |
                 CONTINUOUS INTEGRATION
                            |
                       DEMO PATH
```

This is a structural illustration only. **Choose A/B/C from the provided project description**.

### 4.4 Exact ownership map

For **each** developer, provide:

1. Workstream name and user-facing outcomes.
2. Feature scope and explicit non-goals.
3. Frontend responsibilities and owned paths.
4. Backend responsibilities, endpoints, and owned paths.
5. Dataset/data-processing responsibilities when needed.
6. AI/LLM responsibilities when needed.
7. Schemas produced and consumed.
8. External dependencies and interfaces with other features.
9. P0, P1, and P2 deliverables.
10. First three actionable tasks.
11. Tests and acceptance criteria.
12. Independent coding-agent tasks and appropriate worktree boundaries.
13. Integration checkpoints and Definition of Done.

Produce a matrix with three developer columns showing all these dimensions. Identify a **single integration/contract owner** (one of the three humans) responsible for coordinating shared changes—not for writing everyone's code.

### 4.5 Independence and change control

- No two developers should routinely edit the same implementation files, API route definitions, database migrations, or agent workflow.
- Shared components get a designated owner or are completed in the golden scaffold.
- Consumers use **contract-compatible mocks** before producers finish.
- Shared contract changes require proposal, review, regenerated types, updated mocks/tests, and communication to all three owners.
- Do not allow a coding agent to silently modify another developer's feature.
- If work crosses ownership boundaries, request coordination instead of rewriting unrelated files.
- Recommend feature-owned modules and route composition patterns that minimize edits to shared central files.

### 4.6 Agentic parallelism within a feature

Each human may use several bounded coding-agent tasks (for example UI, API, tests, data adapter), but the human owns review, integration, and correctness. Avoid agents simultaneously editing the same files; use separate branches or worktrees as appropriate.

**Do not implement the three workstreams during planning. Present them for human approval.**

## 5. Canonical Contracts Before Code

Define one authoritative set of contracts shared by all workstreams:

- Domain entities and globally stable identifiers.
- Dataset feature definitions, units, timestamps, and provenance.
- API paths, methods, query/body fields, response fields, status codes, and errors.
- AI agent tool interfaces, request/response schemas, and validation.
- Application and simulation/analysis configuration.
- Nullability, defaults, enums, units, numeric precision, naming conventions.

For every critical contract, show: **name, producer, consumers, purpose, required/optional fields, types, constraints, example request, example response, failures, and versioning policy**.

Choose a canonical schema source of truth appropriate for the stack (e.g., Pydantic/OpenAPI/JSON Schema with generated TypeScript types). Avoid manually maintaining independently evolving duplicate models. Document the exact type-generation and verification commands.

**Contract change protocol:** propose change → identify consumers → get contract-owner approval → update canonical schema → regenerate types → update fixtures/mocks/tests → verify integration → notify all developers. Prefer backward-compatible additions.

## 6. API-First Design

Before implementing backend logic, enumerate all P0 endpoints with:

- HTTP method and path.
- Purpose and feature owner.
- Request params/body and response schema.
- Errors, validation, and authorization if needed.
- Frontend and/or agent consumers.
- Mock example that exactly matches the eventual response.

Recommend an endpoint and router structure that permits feature owners to develop without frequently editing shared registration files. Use contract tests to detect schema drift.

## 7. Dataset Design, Validation, and Provenance

If datasets are involved, design:

```
Source datasets -> source-specific adapters -> validation
                -> canonical feature tables -> application logic
```

For each proposed source/feature include:

- Exact metric and operational definition.
- Expected dataset/provider and identifier or URL (mark unverified sources as *to verify*).
- Time period, update frequency, units, and granularity.
- Relevant raw fields and transformations.
- Target schema field and downstream consumer.
- Coverage, join keys, missingness, and quality concerns.
- Provenance metadata and P0/P1/P2 priority.

Address mismatched geographies/identifiers, inconsistent time periods, duplicate records, incorrect denominators, leakage, missing values, and normalization direction. **Never silently fabricate missing observations.** Keep observed data, derived values, estimated values, mock data, and modeling assumptions clearly distinct.

Make ingestion adapters replaceable without changing business logic. Keep P0 feature selection small and defensible; do not collect data simply because it exists.

## 8. AI Agents Used by the Product (Distinct from Coding Agents)

If the product itself requires AI agents, first determine whether a single structured LLM/tool workflow is enough. Add multiple autonomous agents only when justified by separable responsibilities.

For each application agent define:

1. Goal and feature owner.
2. Trigger and lifecycle.
3. Structured input and output contracts.
4. Allowed tools and data permissions.
5. Dependencies on services or other agents.
6. What is deterministic versus model-generated.
7. Validation and grounding rules.
8. Timeouts, retries, failure states, and budgets.
9. State/memory requirements if any.
10. Testing and evaluation criteria.

Use schema validation for agent outputs. Distinguish sourced facts from model interpretation. Avoid letting unvalidated generated content alter authoritative source data or deterministic results.

**Coding agents** (Codex/Cursor/etc.) are development assistants controlled by each human. **Product agents** are runtime functionality. Keep their responsibilities, permissions, and documents distinct.

## 9. Agent-Friendly Monorepo and Documentation

Recommend a structure driven by the actual features, such as:

```
project/
  AGENTS.md
  README.md
  ARCHITECTURE.md
  docs/
    product-spec.md
    development-plan.md
    api-contract.md
    data-contract.md
    agent-contract.md            # only if applicable
    dataset-registry.md         # only if applicable
    decisions.md
    integration.md
  frontend/
    app-or-pages/
    features/
      feature-a/
      feature-b/
      feature-c/
    shared/
  backend/
    app/
      features/
        feature_a/
        feature_b/
        feature_c/
      shared/
  data/                        # only if needed
  shared/
    schemas/
  tests/
```

Prefer **feature-owned frontend and backend modules** over giant shared files. The exact tree must reflect the approved stack and workstreams, not this example literally.

Create a concise root `AGENTS.md` containing project purpose, architectural map, commands, canonical contract locations, ownership rules, no-go changes, and verification requirements. Use scoped `AGENTS.md` files for feature modules when useful. Keep detailed specs in `docs/` and avoid duplicating the same contract in prose.

Every coding-agent task should state: objective, allowed files, prohibited areas, inputs, outputs, dependencies, tests, and Done criteria. No unrestricted “improve the whole repo” requests.

## 10. Git, PRs, Worktrees, and Conflict Prevention

Plan for:

- One **golden scaffold commit** verified before workstreams branch.
- Three human feature owners using short-lived branches/PRs.
- Optional isolated worktrees for parallel coding-agent tasks.
- Explicit CODEOWNERS or equivalent shared-file approval policy if practical.
- Small PRs that pass unit tests, contract checks, type checks, and relevant builds.
- Continuous integration of working slices instead of one final mega-merge.
- A single owner for shared routes, app shell, migrations, and canonical schemas, with collaboration procedures.
- A clear escalation process when an agent discovers it must cross module boundaries.

Give concrete branch naming, PR review checklist, integration commands, and conflict-resolution rules appropriate for a 3-person hackathon.

## 11. Mock-First Parallel Development

Before real dataset, AI, or backend functionality is complete, establish a thin working path:

```
Frontend runs -> backend runs -> API call succeeds
             -> mock feature results render
             -> primary interaction works
             -> user sees an updated outcome
```

Use **contract-accurate mocks** (not unrelated hardcoded UI). Once the skeleton works, replace mocks incrementally with tested implementations while preserving interfaces. Label demo fixtures/synthetic data clearly; do not represent them as observed results.

Each vertical slice should have its own independently demonstrable acceptance path and should integrate with the same application rather than becoming a separate app.

## 12. P0 / P1 / P2 Scope Control

Categorize **every feature and major task**:

**P0 — Must work for the end-to-end demo.** Minimum essential user flow, real core computation or genuine functioning AI/data workflow where the value proposition requires it, consistent contracts, meaningful outputs, and sufficient error handling.

**P1 — Strong improvements once P0 works.** Better explanations, visual polish, comparisons, additional trustworthy inputs, usability, and performance that meaningfully improve the demo.

**P2 — Stretch only.** Sophisticated animations, extra datasets, advanced agent orchestration, expensive routing/modeling, secondary flows, architecture experiments, and features not required for the main story.

Produce a backlog table with: **ID, title, user outcome, P0/P1/P2, feature owner, dependencies, inputs, outputs, acceptance criteria, test, parallelizable Y/N, integration point, and cut/fallback plan**.

Do not mark everything P0. Identify what to drop first if behind schedule. Never risk the working P0 demo to finish P2.

## 13. Phases and Integration Milestones

**Phase 0 — Plan and approval:** Architecture, dynamic three-way feature split, canonical data/API/agent contracts, dataset plan, risk register, P0/P1/P2 backlog, ownership map.

**Phase 1 — Golden scaffold:** App shells, configuration, shared schemas/generated types, mocks, feature module boundaries, docs/AGENTS.md, lint/test commands, and a working mock end-to-end interaction. Confirm frontend-backend integration. Only then branch.

**Phase 2 — Parallel vertical-slice implementation:** Each of the three developers builds assigned feature UI + backend + logic/data/AI + tests as needed, using mocked external dependencies where necessary.

**Phase 3 — Frequent small integrations:** Replace mocks, merge tested increments, check canonical contracts after each integration, and keep main deployable.

**Phase 4 — End-to-end verification:** Validate the full user story, source/data correctness, AI failure handling, input validation, performance, and reproducibility where applicable.

**Phase 5 — Demo polish:** Improve UI, explanation clarity, speed, storytelling, demo fallback, and reliability. No risky architecture changes or unneeded new dependencies.

Provide concrete integration checkpoints, blockers, and fallback decisions for each phase. Keep a reliable working version at all times.

## 14. UI/UX and Demo Strategy

The product should be understood by a judge quickly. Recommend one clear, memorable flow that demonstrates:

1. The problem and why the product matters.
2. A user action that triggers a real underlying workflow.
3. A traceable, understandable result.
4. A meaningful interaction that changes the output.
5. Honest assumptions/limitations without cluttering the main experience.

Prioritize polished hierarchy, typography, spacing, visualizations, responsive states, and coherent storytelling. Do not build decorative pages unrelated to the core demo. Avoid making animation or elaborate maps a P0 requirement unless the concept cannot work without them.

## 15. Testing and Reliability

Specify a lightweight but useful suite:

- **Contracts:** Schema validation and frontend/backend/agent type agreement.
- **Data:** Source-to-feature transformations, joins, units, missingness, provenance.
- **Algorithms:** Correctness and determinism when applicable.
- **API:** Success, validation, and error responses.
- **AI:** Structured responses, malformed outputs, unsupported claims, tool failures, budget/timeout handling.
- **Frontend:** Type check, build, primary interaction, loading/error states.
- **Integration:** Mock-to-real replacement and one complete user-flow smoke test.

Do not add heavy testing infrastructure purely for coverage metrics. Make acceptance criteria executable wherever practical.

## 16. Risks, Decisions, and Definition of Done

For each major risk list likelihood, impact, owner, mitigation, and fallback. Include data availability, inconsistent schemas, external API failures, agent hallucinations, latency/cost, dependency bottlenecks, overlapping edits, and deployment issues where relevant.

Define a P0 Done checklist that includes:

- Local start instructions actually work.
- Frontend and backend can communicate.
- Three feature slices integrate in the same application.
- P0 API and AI contracts validate.
- Core outputs are authentic or explicitly labeled assumptions/simulation.
- Important results have an inspectable reason/source.
- Primary user journey works without hidden manual intervention.
- Error states fail gracefully.
- Relevant tests, type checks, and builds pass.
- Demo fallback exists if an external service fails.

Create a concise decision log with owners and approval requirements. Clearly separate confirmed facts from assumptions and unresolved choices.

## 17. Required Planning Deliverables

Return the plan in this order:

### A. Project understanding
1. Product summary and primary demo path.
2. P0 capabilities and deliberate exclusions.
3. Key assumptions and unresolved product decisions.

### B. Architecture
4. Recommended stack with minimal-dependency rationale.
5. System/data/AI flows (text diagrams).
6. Proposed feature-owned monorepo layout.
7. Shared foundation versus separately owned modules.

### C. Three-developer vertical-slice plan
8. Reasoned selection of three full-stack feature workstreams based on **this specific project**.
9. Three-column ownership matrix: UI, backend, API, data, AI, files, contracts, tests, and P0/P1/P2.
10. Complexity and workload balance analysis.
11. First three actionable tasks per owner.
12. Cross-feature dependencies, mocks, and integration checkpoints.
13. Single integration/contract owner and protected shared-file policy.

### D. Contracts and data
14. Canonical entities, identifiers, schemas, and examples.
15. API endpoints with producer/consumer ownership and request/response/error examples.
16. Product-agent contracts, if applicable.
17. Dataset/feature matrix, lineage, transformations, source verification requirements, and quality risks, if applicable.
18. Schema source-of-truth, type generation, and contract change process.

### E. Execution
19. Detailed prioritized P0/P1/P2 backlog with dependencies and acceptance tests.
20. Golden scaffold checklist and a minimal mock end-to-end test.
21. `AGENTS.md` structure and per-feature agent instructions.
22. Git branches/worktrees/PR/CI/integration workflow.
23. Local development and simple deployment plan.
24. Phased milestones and no-go/cut decisions.

### F. Quality and approval
25. Risk matrix and fallbacks.
26. MVP Definition of Done.
27. Short, memorable demo script/flow.
28. Explicit decisions requiring human approval **before scaffolding**.

## 18. Strict Planning-Only Stop Condition

**Do not generate implementation files, install dependencies, fetch full datasets, scaffold, commit, or change the repository in this step.**

Do not choose a conventional frontend/backend/data ownership split by default. Choose three end-to-end **feature workstreams based on the project**, and justify them.

Do not give incompatible or underspecified schemas. Do not assume data sources have been verified. Do not let product AI agents or coding agents freely modify authoritative data and shared contracts. Do not defer integration to the final hours. Do not trade away P0 functionality for architectural sophistication.

**Stop after presenting the plan, dynamic three-developer workstream division, shared contracts, prioritized backlog, integration strategy, and human-approval decisions. Await approval before scaffolding.**
