> Historical planning input. The user-approved 2026-10-10 discovery revision is defined in [docs/opportunity-discovery.md](docs/opportunity-discovery.md). Repository pairing is optional; current ownership/runtime contracts govern implementation. The original text below is preserved for provenance.

# RepoFusion: Codex Planning Brief

Consolidated October 10, 2026. Working name only; final project name is undecided.

This document contains the current project only. It supersedes earlier brainstorming alternatives. It is intended as input to Codex for architecture and implementation planning, not as a claim that anything has already been built or deployed.

## 1. Instruction to Codex

Plan this project for three software developers assisted by coding agents, within a 36-hour hackathon budget. Account for time already elapsed; do not assume a fresh 36 hours. Preserve the product purpose and requirements below. Separate the required demonstration from stretch goals. Identify dependencies, the critical path, unresolved hardware/data access, shared schemas, integration tests, deployment approach, and ownership of each workstream. Make implementation milestones concrete and testable.

Focus on one real, validated repository integration and one full feedback-to-improvement cycle. Additional repository combinations may be proposals with explicit evidence/status. Do not silently substitute a static mockup for a validated integration, invent results, label synthetic opinions as real demand, or call a prerecorded replay live. Do not start implementation solely because of this brief if the user asks only for planning.

## 2. Product purpose

Discover popular or trending open-source GitHub repositories, identify complementary capabilities across two or three repositories, and propose useful combined products. Before selecting a product, check whether the combination or an equivalent solution already exists and whether the proposed integration is feasible.

For the selected combination, preserve the original repositories and connect their capabilities through adapters. Validate the real integration, expose its capabilities through a usable frontend, and generate a factual product briefing from implemented and validated features.

Synthetic personas informed by UCF and surrounding-area aggregate data then try the application in real browser sessions. Their roles, skills, current activities, locations, devices, and constraints determine relevant tasks. They give evidence-linked feedback, including why the product is useful or not useful and what conditions might change that judgment.

A group of engineering-role agents aggregates this feedback, prioritizes changes, implements bounded improvements, and repeats tests on a new version. A stylized 3D UCF-area world lets viewers inspect approximately ten featured personas, their locations, animations, and actual live browser sessions while the larger experiment runs.

The product investigates software combinations and synthetic usability/relevance. Real-world adoption, profitability, representative human behavior, and production scalability are not established by synthetic users.

## 3. Agreed scope and recommended defaults

### Requirements established in the discussion

- GitHub discovery, capability analysis, and combinations of two or three repositories.
- An explicit search for existing integrations and equivalent solutions.
- Feasibility assessment before committing to integration.
- One real adapter-based integration as the central demo target.
- Validation using actual execution and correctness checks.
- Working frontend tied to the validated functionality.
- Product description and capability metadata derived from validation and implementation.
- Personas with multiple roles, skills, constraints, and contextual scenarios.
- Every persona performs a brief trial even if initially uninterested.
- Personas may stop browsing after that trial, or during extended testing, if they find no value.
- Feedback explains usefulness, barriers, possible improvements, and conditions for relevance.
- Five engineering roles analyze and improve the product, followed by retesting.
- UCF-area 3D visualization, approximately ten blocky featured characters, contextual rooms, and outdoor movement.
- Clicking a character shows its actual browser session while testing.
- Hugging Face open models, actual inference on sponsor-provided AMD hardware using ROCm, and Neon for persistent data.
- Three developers with AI coding assistance.

### Defaults proposed for planning, not immutable requirements

- Discover 20–30 repositories; retain approximately five combination proposals.
- Begin with pairs, allowing a third repo only when it has a clearly necessary role.
- Implement and validate one combination.
- Create approximately 200 persona records as the desired population; start execution with 20–50 browser personas and expand after benchmarking.
- Display ten featured characters linked to actual experiment sessions.
- Use four scenario templates and three or four reusable interior types.
- Limit browser concurrency initially to 4–8 sessions.
- Give interested personas two or three relevant tasks; allow up to five only if runtime permits.
- One v1-to-v2 improvement cycle, implementing two or three prioritized changes.
- Start screen streaming with screenshots; upgrade to Chromium screencast if stable.

Earlier discussions considered 100 or 1,000 agents. The current target discussed is around 200, with about ten featured in 3D. Distinguish persona records from completed browser tests; never imply that all configured personas have executed.

## 4. End-to-end workflow and gates

1. Acquire popular/trending repository candidates and cache source metadata.
2. Extract documented capabilities, inputs/outputs, interfaces, dependencies, and evidence; inspect issues and discussions for unmet needs that another repository could address.
3. Propose complementary combinations and a specific audience/problem.
4. Search for exact integrations, equivalent functionality, and features already present in either source repo.
5. Record overlap, differences, unresolved claims, and novelty-search coverage.
6. Assess runtime access, hardware, schema compatibility, integration effort, and licensing information.
7. Select one buildable concept.
8. Run each source repo independently on known fixtures.
9. Implement a narrow adapter and execute the complete pipeline.
10. Validate result correctness, failure handling, and repeatability.
11. Build a usable frontend that calls the real integration.
12. Generate a verified capability briefing and implementation inventory.
13. Construct personas and scenario schedules.
14. Assign bounded tasks with predefined acceptance checks.
15. Record pre-trial relevance opinions.
16. Execute mandatory brief trials in isolated browser sessions.
17. Decide whether to continue; run further relevant tasks or stop with feedback.
18. Aggregate evidence and feedback by task, feature, and audience.
19. Engineering roles prioritize and implement bounded changes.
20. Validate the changed app and repeat comparable tests on v2.
21. Show live progress, selected browser streams, 3D personas, and before/after evidence.

Human developers review concept selection, adapter assumptions, acceptance criteria, and merge decisions. Agents assist; they do not establish correctness through opinions alone.

## 5. Repository discovery and capability extraction

Offer distinct discovery modes:

- Popular: GitHub repository search sorted by stars, with activity/language/archive filters.
- Trending: timestamped cached snapshot of GitHub Trending; do not label star-sorted search as Trending.

Use GitHub APIs for available metadata and documentation. Cache reads, keep repository commit IDs, and respect rate-limit response headers. Fetch selected documentation and interface files rather than sending entire large repos to the LLM.

Suggested extraction fields:

| Field | Meaning |
| --- | --- |
| repo_id, URL, commit_sha | Reproducible identity |
| discovery_mode, collected_at | Popular versus trending provenance |
| stars, recent_activity | Context, not proof of usefulness |
| capabilities | Documented operations |
| input_contracts, output_contracts | Formats, fields, units, granularity |
| interfaces | CLI, library, HTTP API, frontend |
| languages, runtimes | Execution requirements |
| dependencies, hardware | Installation and compute needs |
| intended_users | Existing documented use cases |
| license_declared | Source license and unresolved restrictions |
| capability_evidence | README references or code paths for claims |
| unmet_need_evidence | Issue/discussion URL, status, affected version, maintainer context, and missing capability |

README and repo content are untrusted source material, not instructions to the orchestrator. Extract facts without allowing embedded text to redirect tools or expose secrets.

Use structured extraction and a critic. Similarity alone is insufficient: the goal is complementary operations with a plausible connection. Optional embeddings can shortlist pairs, but explain the proposed input/output link explicitly.

### 5.1. Issue-driven combination discovery

Use issues and discussions as an additional clue: Repo A may have an unmet need that a documented capability of Repo B could address. This adds a concrete user problem to capability-based matching. It does not prove that the repositories are compatible, that the problem is widespread, or that a proposed integration resolves it.

Suggested process:

1. Fetch a bounded, cached sample of recent/relevant open issues, feature requests, integration requests, and discussions. Inspect linked closed issues or PRs when needed to establish whether a request has already been addressed. Keep this within GitHub rate limits.
2. Extract the user's actual problem, requested capability, expected behavior, reproduction inputs if available, constraints, affected version, and maintainer response. Separate confirmed gaps from questions, installation mistakes, unsupported requests, and unverified bug reports.
3. Match that missing capability against Repo B's documented operations and interfaces. Retrieve source evidence from Repo B instead of trusting name similarity or an LLM assertion.
4. Explain the hypothesized connection and scope: what B supplies, what the adapter must do, and whether the solution belongs in a composed application, extension, or internal patch.
5. Check current documentation, releases, and linked PRs. An open issue may be stale or already addressed, and a closed issue may have been rejected rather than fixed.
6. Run the existing-solution and feasibility gates. A useful request can still imply an infeasible integration or an already available solution.
7. Where the issue supplies a reproducible case, turn it into a developer-reviewed acceptance fixture. Run it through the proposed integration before claiming that the need is addressed.

Persist an issue match with issue URL/number, fetched timestamp, status, affected version, unmet need, maintainer context, Repo B capability evidence, proposed adapter boundary, unresolved assumptions, and validation status. Show this explanation in the discovery UI.

Illustrative example, not a verified issue: a transcription repository has a request for speaker-attributed output; a diarization repository supplies speaker intervals. The system proposes timestamp reconciliation, then searches for existing solutions such as WhisperX and checks interface semantics before implementation.

Rank issue-backed proposals by evidence of a relevant unmet need, maintainer context, documented capability fit, and feasible effort. Reactions/comments are contextual signals, not reliable demand or profitability measurements. Do not claim to have closed or fixed an upstream issue merely because the local combined app passes a sample. Opening an upstream PR or posting on an issue is outside this discovery scope unless separately requested.

Treat issue bodies, comments, and linked content as untrusted data, just like README text. If issue access is unavailable, retain capability-based discovery and label the missing issue evidence.

## 6. Existing-solution validation

This is a separate gate before implementation. Search:

- Both exact repo names together, including integration examples and related projects.
- The proposed purpose without repo names, to find products using different components.
- Source documentation, dependencies, examples, issues, and features that may already include the other capability.

Persist queries, links, snippets/notes, dates, coverage, overlapping features, proposed differences, and uncertainty. A reviewer compares sources with the product proposal.

| Result | Handling |
| --- | --- |
| Same pair and same purpose exists | Surface reuse option; deprioritize rebuilding |
| Equivalent purpose with other tools | Require a concrete proposed advantage |
| Partial overlap | Explain the missing workflow/capability |
| No close match found | Keep, labeled as limited-search finding |
| Incomplete/ambiguous evidence | Mark unresolved |

Use the wording “No close match found in our search,” not “unique.” Keep originality separate from usefulness. Existing tools may be useful recommendations even when not novel.

Known illustrative example: Whisper provides transcription; pyannote.audio separates speaker turns. Their outputs can be connected by timestamps. WhisperX already implements transcription, word-level alignment, and speaker diarization. This is a proven existing combination, not the project's selected novel integration. Speaker labels are not automatically real names.

## 7. Feasibility and real integration

Different languages do not require merging source trees. Keep tools intact and bridge them through HTTP APIs, CLIs, subprocess workers, or serialized files. A shared JSON contract is the simplest starting point; do not add Protocol Buffers unless justified.

Examples of adapter responsibilities:

- Rename fields and convert milliseconds to seconds.
- Validate field types and required values.
- Normalize identifiers and encodings.
- Translate one output structure into another input structure.
- Handle unknown values, errors, timeouts, and partial results.

Semantic mismatches matter more than syntax: monthly totals cannot reconstruct individual transactions, and aggregate outputs cannot supply information they discarded.

Feasibility factors: documented interfaces, independently runnable examples, hardware availability, compatible data meaning, input/output granularity, dependency conflicts, source-license/model-license conditions, and bounded adapter effort. Flag legal questions rather than inventing definitive license compatibility.

Recommended gate: if both repos are not running independently within roughly six hours of starting the integration workstream, simplify or switch the pair.

One developer with coding agents can plausibly deliver one narrow workflow if both repos already run. Modifying internals of two large unfamiliar codebases, integrating arbitrary pairs, or delivering five unrelated integrations is high risk.

## 8. Integration validation

| Gate | Required evidence |
| --- | --- |
| Independent execution | Each repo succeeds on a known sample |
| Adapter contract | Types, required fields, units, formats, and missing values handled |
| End-to-end execution | Real input passes through all components |
| Correctness | Output matches predefined expectations or explicit tolerances |
| Failure handling | Invalid input, timeouts, and incompatible output handled |
| Repeatability | Pinned commits/environment and fixtures reproduce results |

An output file or HTTP 200 response alone is not correctness. Use small known fixtures with expected results. For stochastic model output, define meaningful tolerances and record sampling settings.

An agent can author tests and another can critique them. Developers approve the acceptance criteria; agents must not weaken checks simply to pass.

Statuses: proposed, interfaces_inspected, contract_checked, execution_passed, validated_on_samples, failed, inconclusive. Record which cases were tested; validation is bounded by those cases.

Separate integration validation from browser usability tests and from load/scalability tests.

## 9. Product frontend and capability briefing

Use a stable React shell with a constrained generated feature area. Ensure actual navigation, inputs, state changes, relevant create/edit/search/export behavior, and meaningful error/empty states.

Concept specification includes source repos, audience, problem, features, screens, flows, entities, expected outcomes, integration boundaries, and limitations. Implementation inventory separately records which features exist and which passed validation.

Generate the persona-facing briefing from both inventories. Explain the product factually without selling it or revealing exact task solutions. Include supported inputs, validated features, limitations, and fixtures.

If a real integration cannot be completed, an interactive prototype with simulated services is a fallback only. Mark simulated outputs and unimplemented integrations explicitly. Persona tests on that fallback evaluate experience, not source-repo integration correctness.

Serve generated code on a separate origin/container with restricted permissions. Do not expose database administration, GitHub, or GPU credentials in generated code or browser assets.

## 10. Population data and provenance

Use fictional personas informed by aggregate statistics, not impersonations of identifiable students or employees.

Sources to inspect:

- UCF Common Data Set: published student/enrollment characteristics.
- UCF IPEDS: institution-level enrollment and available staffing categories.
- UCF reporting library: available enrollment/faculty/staff breakdowns; check access/export feasibility.
- Census ACS five-year estimates: regional age, employment, income, household, and commuting characteristics.
- Geographic boundaries and OpenStreetMap-derived map data for visual context.

For a 20-mile radius around main campus, create a geospatial buffer and identify relevant Census tracts. A tract-centroid inclusion rule is a labeled hackathon approximation; exact radius population is not provided by the API. Preserve ACS vintage, estimates, uncertainty, and geographic selection method.

Institutional demographics do not reveal where individuals live. UCF affiliates overlap with regional residents. Do not add enrollment totals to resident population or fabricate cross-tabulated distributions unavailable in the data.

Start with a coverage panel across undergraduates, graduates, faculty, staff, and other local workers/residents. Label it intentionally balanced rather than representative. Statistical population weights should only be used if defensible from sources; otherwise report cohort-level results.

Track each persona attribute as sourced_distribution, scenario_assumption, or fictional_detail. Skills, schedules, personality, device availability, and exact locations may be assumed rather than known. Avoid demographic stereotypes when assigning competence or behavior.

## 11. Personas and contextual scenarios

Permanent persona fields: synthetic ID/name, roles, study/work context, skills, goals, constraints, device access, budget, language/accessibility needs where relevant, and source/assumption references.

A persona can be a CS student, TA, and research assistant simultaneously. Current scenario activates one role and determines the current environment.

Scenario fields:

```json
{
  "persona_id": "persona_017",
  "active_role": "teaching_assistant",
  "location_id": "classroom",
  "activity": "office_hours",
  "goal": "Help a student understand a difficult topic",
  "device": "laptop",
  "time_budget_minutes": 10,
  "assumptions": ["Fictional schedule and location"]
}
```

Example scenarios:

| Activity | Active role | Location options |
| --- | --- | --- |
| Exam preparation | Student | Library, home |
| Office hours | TA | Classroom, teaching workspace |
| Research/team meeting | Research assistant/student | Office, collaboration room |
| Work shift | Staff/local employee | Workspace, illustrative office |

Location constrains available actions and devices but does not alone determine intent. Support schedule-driven scenarios and optional location-driven scenarios. For location-driven mode, infer a plausible activity from eligible roles, display it, and let the viewer change it.

Tasks come from persona + active role + scenario + implemented capabilities, not from five universal tasks. Assign up to five relevant scenarios only if appropriate; allow no meaningful task for the product.

## 12. Task planner and acceptance checks

Use predefined task categories with LLM-adapted goals and inputs. A validator rejects unsupported tasks, impossible outcomes, incompatible devices, and missing success checks.

The planner sees the product specification. The browser persona sees only its factual briefing, task goal, and visible interface. Do not reveal navigation answers or evaluator-only fixtures.

Each task stores role/scenario, initial data, goal, action budget, outcome check, supported features, and task version. Deterministic checks evaluate relevant saved state, files, or outputs. An LLM can supplement qualitative analysis but cannot replace all checks.

Phone scenarios use mobile viewport/touch configuration. Preserve persona app state across scenarios when appropriate; reset between comparable v1/v2 experiments.

## 13. Mandatory trial and continuation policy

1. Record initial relevance judgment and reasons.
2. Require one short representative browser task even for initially uninterested personas.
3. Bound the trial, initially around six actions, with early stop for success or a blocking failure.
4. Collect post-trial relevance and evidence.
5. Continue into additional relevant tasks only when useful or reasonably promising.
6. Allow stopping during extended use if value disappears, a blocker persists, or the action budget is exhausted.

The controller enforces the minimum trial but never forces a positive opinion or invented need. An irrelevant persona can explore a supplied sample without claiming it solves a personal problem.

Distinguish current usefulness, potential usefulness requiring changes, lack of need, and inability to complete a relevant task. Allow “No plausible change would make this useful to me.”

## 14. Browser agent execution

Use Playwright + Chromium in worker processes. Each active persona has an isolated browser context and session-scoped application data. Browser isolation does not isolate records in a shared backend; scope those explicitly.

Loop: capture accessible page structure; ask the persona model for one action; validate it; execute; capture outcome; check completion; continue or stop.

Expose a bounded action vocabulary: click a currently valid element, type, select, scroll, navigate allowed routes, and stop. Build element IDs from the current page. Do not execute arbitrary model-authored JavaScript or fabricated selectors.

Save action IDs/sequence, timestamps, screenshots, errors, relevant output/state, and stop reason. Categorize infrastructure/model-action failures separately from application failures.

Initially limit ordinary tasks to roughly eight actions. Maintain timeouts, retry caps, cancellation, and a worker queue. These numbers should change only after measurement.

Maintain population-level feature coverage. Assign missing-feature tests only to personas with plausible reasons to use them. Use separate QA for capabilities without natural persona coverage.

## 15. Feedback contract

All personas, including those who stop, submit structured feedback:

```json
{
  "persona_id": "persona_017",
  "session_id": "session_042",
  "prototype_version": "v1",
  "initial_relevance": "low",
  "post_trial_decision": "stop",
  "tasks_attempted": ["task_01"],
  "features_used": ["feature_02"],
  "useful_parts": [],
  "reason_for_stopping": "No current need for this workflow",
  "conditions_that_could_make_it_useful": [],
  "remaining_barriers": ["No relevant activity"],
  "suggested_changes": [],
  "evidence_action_ids": ["action_03", "action_05"]
}
```

Separate observed task outcomes from self-reported synthetic opinions. Link feature criticism to actions where possible. Do not accept invented actions or treat unsupported opinions as executed evidence.

Report interested_before_and_after, became_interested_after_trial, and remained_uninterested_after_trial, with denominators and experiment labels. These are synthetic trial outcomes, not human adoption rates.

## 16. Engineering review and improvement cycle

Five roles can share the same model through separate prompts and structured contexts:

| Role | Output |
| --- | --- |
| Feedback analyst | Evidence-linked clusters by task/feature/cohort |
| Product prioritizer | Ranked changes and tradeoffs |
| UX reviewer | Flow and accessibility proposals |
| Implementer | Bounded code patch |
| QA reviewer | Regression results and comparison |

Only the implementer writes the shared product code; reviews can run separately. Use an isolated branch/workspace, not concurrent agents modifying the same files.

Aggregate large feedback batches hierarchically. Include successful sessions and rejection reasons, not only failures. Each improvement records issue, severity, affected share, evidence strength, estimated effort, acceptance check, supporting session IDs, and expected tradeoff.

A heuristic priority formula is severity × affected share × evidence strength ÷ effort. Define inputs; do not represent it as an empirical business model.

Apply two or three changes, build, run integration and UI regressions, preserve v1, deploy v2, and rerun matched personas/scenarios/tasks with fresh comparable state. Add a few new scenarios if time allows to check overfitting to initial tasks.

Display measured task completion, error categories, feature coverage, and changes. Browser elapsed time includes LLM/infrastructure latency and is not human task time. Monetization and expansion proposals must be hypotheses with validation steps. Production scalability needs separate load/architecture evidence; 200 persona records do not prove it.

## 17. Main dashboard

| View | Contents |
| --- | --- |
| Discover | Repos, complementary capability graph, evidence |
| Validation | Existing-solution findings, feasibility, integration status/tests |
| Product | Specification, implemented features, real preview |
| Population | Cohorts, data provenance, scenarios, synthetic locations |
| Experiment | Queue/running/completed counts, session details, live screens |
| 3D World | Campus overview, interiors, characters, selection |
| Evolution | v1/v2, patches, priorities, supporting evidence, retests |

Use readable navigation, cohesive colors/typography, and accessible DOM controls alongside the 3D view. Show experiment health, limits, cancellation, and a clear live/replay indicator.

## 18. 3D UCF-area world

Desired style: original Roblox-like/blocky low-poly characters, not photorealistic people. The 3D layer is an inspection interface for experiment data.

Two levels:

- Campus/regional overview with simplified buildings, paths, labels, markers, and cohort counts.
- Reusable interior scenes: classroom, library, home/bedroom, office/staff workspace.

Click a building to enter a scene; click a character to focus the camera and open its session panel. Outdoor walking uses predefined waypoints. Do not require a full physics engine, city-scale navigation, or accurate indoor reconstruction.

MapLibre can provide a separate regional map with building extrusions. React Three Fiber handles characters and rooms. Avoid combining two camera/rendering systems on the same canvas in the MVP. A simplified R3F campus can use cached geographic footprints and synthetic heights; label approximations and include map attribution.

Fictional office locations, including an illustrative scenario for a recent graduate working at Siemens Energy, must not imply known real employee whereabouts or accurate private-office interiors.

## 19. Featured characters and event-driven animation

Approximately ten characters are linked to actual persona/session IDs. Select across roles and outcomes; let viewers replace a featured slot with another persona.

Build characters from box/capsule geometry with joint groups, simple faces, clothing colors, laptop/phone props. Reuse desks, chairs, and rooms. Alternatively use licensed GLB assets and animation clips. No requirement to create custom realistic rigs.

Scene assignment stores persona_id, scenario_id, location_id, scene_id, seat_id, device, session_id, and status. The same scenario drives both the browser task and 3D location.

| Event | Animation/status |
| --- | --- |
| Moving to assigned location | Walk along predefined path |
| Queued | Idle with waiting badge |
| Trial starts | Sit/use laptop or phone |
| Typing/click executed | Brief typing/tapping motion |
| Model response pending | Seated idle |
| Task fails | Neutral failure indicator |
| Feedback submitted | Short feedback bubble |
| Persona stops | Stop device interaction |
| Retest starts | Return to device/task animation |

Use explicit reported emotions only; do not infer happiness/confusion from every success/failure. LLMs decide browser tasks, while deterministic frontend animation controls limbs and movement. Never claim illustrative walking is a measured real-world behavior.

Summarize remaining personas through markers, building counts, filters, and counters. Distinguish configured, queued, running, completed, failed, and replayed. Ten visible characters need not mean ten simultaneously active browser workers.

## 20. Live browser viewing

The selected character's viewer must display the browser the agent is actually controlling. A separately loaded iframe is not equivalent because its state/session can differ.

Architecture: Playwright worker → screenshot/screencast frames → authenticated backend WebSocket → selected character viewer.

MVP: capture screenshots after actions plus approximately 1–2 updates/second while viewed, then tune overhead. Upgrade: Playwright CDP session with Chromium Page.startScreencast, screencastFrame events, and acknowledgments. This is image-frame streaming, not guaranteed high-FPS video. Full remote-desktop streaming is unnecessary initially.

Subscribe by session ID. Changing selection unsubscribes from old live frames without canceling either task. Use timestamps/sequence numbers, a cursor overlay from actual executed coordinates, stale-stream detection, and latest-frame backpressure. Drop obsolete frames instead of accumulating lag. Reconnect using last event sequence and display current session state.

Stream detail only for selected/nearby watched sessions. Keep long image streams out of Neon; persist event metadata and artifact references. Store clips/keyframes externally or locally for reproducible demo replay.

Character panel shows profile, scenario, task, version, latest screen, action timeline, opinions, stop reason, and live/replay status. Advanced polish: display the same image stream on the 3D laptop using Drei Html transform/occlusion or an updated texture. Prioritize readable side-panel viewing first.

## 21. Suggested technologies

| Layer | Default |
| --- | --- |
| Dashboard/product UI | React + TypeScript + Vite |
| Styling | Tailwind CSS |
| 3D | Three.js + React Three Fiber + Drei |
| Regional map | MapLibre GL JS, cached geographic data |
| Backend | Python + FastAPI |
| Schemas | Pydantic; shared JSON contracts |
| Agent execution | Explicit state machine and queued workers |
| Browser | Playwright Python + Chromium |
| Live frames | WebSockets, screenshots/CDP screencast |
| Persistent data | Neon Postgres, psycopg pooled connections |
| Optional TS database access | Neon serverless driver |
| Model serving | vLLM on compatible AMD ROCm environment |
| General open model | Qwen/Qwen3-8B candidate |
| Optional coding model | Qwen/Qwen2.5-Coder-7B-Instruct candidate |
| Isolation | Docker, separate generated-app origin |
| Artifacts | Files/object storage; references in Neon |

These are planning candidates, not verified installed versions. Pin compatible package versions during implementation, including React/React Three Fiber major versions. No Supabase requirement. No fine-tuning requirement. Avoid adding orchestration frameworks, Redis, or custom physics unless the measured workload warrants them.

## 22. AMD and Hugging Face integration phase

This is actual compute integration, not merely generating code with an AMD-branded tool. No specific AMD plugin/API was verified in the discussion. Sponsor hardware reservation/access is an unresolved dependency.

Before implementation, obtain GPU model, VRAM, allocation time window, credentials/access method, installed ROCm/driver versions, container permissions, and reachable inference networking. Use the sponsor-provided environment and a compatible ROCm vLLM image, not a generic CUDA image.

Download model weights from Hugging Face, pin revision/license, serve on AMD, and expose a protected OpenAI-compatible endpoint to backend workers. Start with one Qwen3-8B model for extraction, personas, and review. Non-thinking mode can reduce routine token overhead. Enable structured schema constraints where supported and validate outputs independently.

Load a coding model only if hardware and code-quality needs justify it. Models can be switched between phases rather than held simultaneously. Memory needs include weights, runtime, and KV cache; do not choose context/concurrency from weights alone.

Benchmark representative requests: structured extraction, browser action selection, feedback, and code patch. Measure tokens/second, latency, schema validity, task success, and actual memory use. Store model/server versions and compute provenance for the demo.

If hardware access is delayed, develop UI/contracts against clearly labeled fixtures or use a disclosed hosted-model fallback. That fallback does not substantiate an AMD execution claim. Hugging Face credentials/credits are separate from AMD compute allocation.

## 23. Neon phase and persistent schema

Use Neon as the real database for the core pipeline, not as a decorative integration. Recommended backend uses a pooled Postgres client. Neon also has a Data API; choose it only if it simplifies authenticated access. Never put administrative database credentials in the frontend.

Suggested tables:

- repositories, capability_evidence, issue_evidence, issue_capability_matches, combination_proposals
- novelty_checks, feasibility_checks, integration_runs, validation_cases
- concepts, product_specs, prototype_versions
- data_sources, population_configs, personas, scenarios, tasks
- experiments, sessions, actions, feedback
- feedback_clusters, improvements, retest_results, artifact_refs

Use IDs, foreign keys, timestamps, statuses, and JSONB for structured payloads. Persist source commits, app commit/version, model revision, prompts/configuration, fixtures, seeds where applicable, and explicit assumptions.

Version isolation can use experiment/version IDs and fixtures. Neon branching is optional; it is not necessary to prove sponsor fit. Keep screenshots/videos outside database rows and retain references/checksums.

## 24. Workload and feasibility

Generating 200 or 1,000 persona records is not the same as running that many browser sessions. Personas share model inference infrastructure but retain distinct state.

Illustrative workload: 100 personas × 2 tasks × 8 model calls × 2 versions = 3,200 calls. At 400 output tokens/call this is 1.28 million output tokens. Hypothetical measured aggregate 100 output tokens/second gives approximately 3.6 hours of generation alone. For 1,000 personas it is approximately 35.6 hours. Prompt processing, browser work, retries, code generation, and installation add overhead. These are calculations, not AMD benchmark claims.

Start with five pilot personas. Measure completion time and failures; select a population size from the result. Run 20–50 first, extend toward 100–200 if feasible. Do not claim statistical representativeness or human behavior accuracy from large synthetic counts.

One real integration, one improvement cycle, and ten selectable characters are the core. Thousands of autonomous browsers, generic integration of arbitrary repos, detailed 20-mile interiors, and multiple independent product integrations are stretch/out-of-scope for the initial weekend.

## 25. Three-developer ownership and coding agents

| Developer | Ownership | First milestone |
| --- | --- | --- |
| A: frontend/world | Dashboard, app UI, rooms/characters, live viewer, version comparison | One room, one character, one linked screen |
| B: discovery/integration/compute | GitHub, evidence, novelty/feasibility, adapter, integration validation, AMD endpoint | Both source repos running; narrow adapter pipeline |
| C: simulation/data/improvement | Neon/schema, datasets/personas/scenarios, browser queue, feedback, engineering roles | One persona completes one task with saved evidence |

This assigns actual integration to one owner. B's workload is the critical path; keep discovery modest and let coding agents inspect each repo independently. If integration consumes the schedule, A/C can help with schema or infrastructure after their first milestones.

Freeze shared contracts early: concept/spec, validated capabilities, scenario/persona, task/check, session/action event, improvement, and stream envelope. Use isolated branches/worktrees and small reviewed merges. One owner controls shared frontend merges; engineering implementer agents patch a separate product branch.

Suggested agent subtasks: repo A interface investigator, repo B investigator, schema adapter reviewer, implementation assistant, and test reviewer. Parallelize independent investigation, not conflicting writes. Avoid excessive agents competing on the same GPU.

## 26. Milestones and fallback priorities

Plan against actual remaining event time. Suggested order:

1. Confirm compute and access; freeze contracts; select a feasible pair.
2. Both repos run independently; database/model endpoint and one UI/room exist.
3. One real adapter passes known cases; one browser persona uses its frontend.
4. Ten to twenty personas run contextual trials; feedback links to actions.
5. Two bounded improvements produce v2; integration regressions and matched retest pass.
6. Ten characters, several reusable rooms, live viewer, and clear experiment counters work.
7. Add data enrichment, extra personas, richer map, and screencast only if stable.
8. Freeze features; record demo/replay; finish submission and rehearse.

Preserve a working checkpoint at each milestone. If needed reduce population, room detail, number of proposals, and animation polish before sacrificing real execution evidence.

## 27. Demo acceptance criteria

- Candidate repos and source evidence are visible.
- Existing-solution search is documented with uncertainty.
- Feasibility is explained and one pair selected.
- Actual adapter integration passes documented normal and failure cases.
- App calls the integration; unsupported features are marked.
- Personas receive verified briefing and scenario-specific goals.
- Initially uninterested personas still trial, then may stop honestly.
- At least one complete session has replayable actions, real outputs, and feedback.
- Clicking a featured 3D character shows that exact session live, with status/timestamps.
- Roles/scenarios change tasks and locations coherently.
- Engineering changes trace back to evidence and preserve v1.
- v2 comparison uses executed retests and fixed acceptance criteria.
- HF model and actual AMD ROCm usage are evidenced; Neon stores core state.
- Synthetic locations/opinions and prerecorded replays are labeled.

Strong demo sequence: discover/select combination → show gates → open working app → click student in library and watch trial → inspect stop reason/problem → show prioritized patch → open v2 → watch retest → compare evidence.

## 28. Sponsor alignment

Based on the user-supplied announced challenges:

- Hugging Face: meaningful use of open models in capability extraction, personas, and review.
- AMD: actual ROCm inference on provided AMD graphics/compute.
- Neon: persistent data powering the complete pipeline and inspection UI.
- Figma: thoughtful navigation, usability, accessibility, and clear flows.
- Adobe: cohesive world, characters, typography, and animation.
- General AI: substantive model-driven behavior and evaluation, not merely AI-assisted coding.
- Full Sail: only if it becomes a genuine training simulation with meaningful pathfinding or face detection; decorative walking alone is weak alignment.
- Databricks: optional only if actual Databricks processing powers useful analysis. Neon usage alone is not a Databricks challenge integration.

Other sponsor themes are not requirements. “Most Useful” is the announced funny/goofy category, not a serious utility award.

## 29. Open decisions Codex should surface

- Which real repo pair and problem is selected?
- What is the remaining event time and the integration owner's experience?
- What AMD hardware, software, access, and networking are actually available?
- Which model size/revision fits after benchmarking?
- What external search access powers novelty checks?
- Which UCF/ACS exports can be obtained quickly, and which persona assumptions remain synthetic?
- Is 200 a configured-persona target or an executed-test target?
- Which scenarios, tasks, known fixtures, and acceptance criteria are fixed first?
- Where do the app, worker service, and artifact store run?
- Which map/model assets are available and licensed for use?
- Which screenshots/streaming approach works reliably on the deployment host?
- What versioning and merge contract prevents agent conflicts?

## 30. Technical and data references

References identified during the discussion. Verify exact installation versions, access, and compatibility at implementation time.

- GitHub Trending: https://github.com/trending
- GitHub repository APIs: https://docs.github.com/en/rest/repos/repos
- GitHub rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- Whisper: https://github.com/openai/whisper
- pyannote.audio: https://github.com/pyannote/pyannote-audio
- Existing WhisperX integration: https://github.com/m-bain/whisperX
- Qwen3-8B: https://huggingface.co/Qwen/Qwen3-8B
- Qwen coding model: https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct
- vLLM GPU/ROCm installation: https://docs.vllm.ai/en/latest/getting_started/installation/gpu/
- AMD Radeon ROCm documentation: https://rocm.docs.amd.com/projects/radeon/en/latest/
- Neon serverless driver: https://github.com/neondatabase/serverless
- Neon Data API announcement: https://neon.com/blog/a-postgrest-compatible-data-api-now-on-neon
- Playwright browser contexts: https://playwright.dev/python/docs/api/class-browsercontext
- Playwright CDP sessions: https://playwright.dev/python/docs/api/class-cdpsession
- Playwright accessible snapshots: https://playwright.dev/python/docs/aria-snapshots
- Chromium screencast protocol: https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-startScreencast
- React Three Fiber: https://r3f.docs.pmnd.rs/getting-started/introduction
- Drei animations: https://drei.docs.pmnd.rs/abstractions/use-animations
- Drei HTML in 3D: https://drei.docs.pmnd.rs/misc/html
- MapLibre buildings: https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/
- OpenStreetMap attribution/license: https://www.openstreetmap.org/copyright
- UCF Common Data Set: https://analytics.ucf.edu/institutional-research/common-data-set/
- UCF IPEDS: https://analytics.ucf.edu/institutional-research/ipeds/
- UCF reporting library: https://analytics.ucf.edu/data-literacy/reporting-library/
- ACS API: https://www.census.gov/programs-surveys/acs/data/data-via-api.html

