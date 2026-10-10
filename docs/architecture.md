# Architecture

Use one React dashboard, one FastAPI application, feature-owned modules and a durable Postgres queue. Browser execution and integration work remain deterministic application code; hosted models propose structured decisions.

```text
React dashboard + React Three Fiber world
                    |
                 FastAPI
       +------------+--------------+
       |            |              |
integration      personas       evolution
GitHub/research  Playwright      analysis/patch review
repo adapters   sessions/frames  regression/comparison
       |            |              |
       +-------- shared -----------+
       Pydantic contracts / HF client / Neon / artifacts
```

## Runtime locations

| Location | Work |
| --- | --- |
| Viewer browser | React/TypeScript/Vite/Tailwind dashboard; Three.js/R3F/Drei world |
| Demo computer | Python/FastAPI, Chromium/Playwright workers, source-repository execution, generated product and artifacts |
| Hugging Face Inference Providers | All application model inference through the server-side adapter |
| Neon Postgres | Durable records, worker job state and artifact metadata |

Hugging Face does not host the browser workers or repository containers. The configured model must be currently served and verified with representative structured decisions. Choose an optional coding model only after evaluation demonstrates a need. The developer's Codex coding assistant is separate from the application's inference provider.

## Feature boundaries

`backend/app/features/{integration,personas,evolution}` and `frontend/src/features/{integration,personas,evolution}` contain vertical slices. Backend routers compose once in the app shell. Canonical Pydantic models generate OpenAPI and frontend types; do not hand-maintain duplicate TypeScript contracts.

Shared code holds configuration, Hugging Face inference, database access, job state and artifact references. A coordinates contract changes, B owns inference and browser/stream infrastructure, C owns database migrations and CI. Detailed ownership is in [ownership](ownership.md).

## Execution and isolation

B's review-source adapters feed an immutable corpus of real software-review evidence into HF behavior extraction and persona generation. Required `Persona.software_behavior` carries patterns plus resolvable source records into the planner/browser/viewer. C persists corpora/review identity and frozen persona profiles through coordinated migrations. This input path is planned beyond the implemented schema/fixture/viewer; see [software behavior](software-behavior.md). Freeze the corpus and behavior alongside tasks/configuration for v1/v2. Review evidence informs simulated preferences; session actions substantiate feedback about the generated product.

Repository tools run separately with a narrow HTTP/CLI/function/file adapter chosen after their interfaces are inspected. Docker is the target for unfamiliar repository execution; availability is a gate, not a claim that it is already installed. Preserve source commits, licenses, fixtures and generated-product version IDs.

Use a separate product process/origin. Playwright contexts isolate cookies and local storage; server-side product records also require session scoping. Reset fixture state before each version's mandatory trial. Allow navigation only to the configured product origin and explicit required origins.

Start with four browser contexts. Claim jobs through Postgres locks and leases; retain attempts and terminal evidence. Recovery restarts expired work in fresh scoped state and never replaces a completed session silently. Cooperatively cancel between actions.

Store screenshot bytes and generated artifacts in `ARTIFACT_ROOT`, outside database rows. Neon stores checksums, paths, sequence/time and ownership metadata. Stream only the selected session's frames; drop obsolete frames and detect staleness.

## Hugging Face boundary

One asynchronous inference adapter receives role, messages, output schema, inference profile and request context; it returns validated output and metadata. Authenticate only server-side, enforce concurrency and experiment budget, and validate every output with Pydantic. A budget or availability failure pauses/resumes durable work; it must not become synthetic successful results.

Record model/provider, prompt version, parameters, request duration, reported token use, retries and schema failures. Freeze configuration for matched v1/v2 experiments. If the provider does not expose immutable weight revisions, retain available metadata and disclose the limitation. See [official Hugging Face inference documentation](https://huggingface.co/docs/inference-providers/index) and [structured outputs](https://huggingface.co/docs/inference-providers/guides/structured-output).

