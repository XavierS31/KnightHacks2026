# RepoFusion

An evidence-backed repository integration and synthetic usability experiment workspace.
Three developers each own a full-stack phase: **A integration**, **B personas**, **C evolution**.
Runtime AI uses **Hugging Face Inference Providers only**; **Neon** stores persistent state.
Playwright executes browser tasks; React Three Fiber visualizes ten selected personas.

## Current state

This is a runnable, fixture-first shared scaffold with developer starter implementations.
Sample repository combinations, personas and improvement suggestions are explicitly synthetic.
No real source pair has been selected, no 500-persona experiment has run, and no v2 has been approved.
The required experiment is **500 personas on each version**, not 500 generated records.
Each persona requires a [software-behavior profile](docs/software-behavior.md) grounded in real software
reviews for production use. The schema supports Reddit, Hacker News and other review sources; current
profiles are labeled fixtures, and real review ingestion/extraction remains unfinished.
Live Hugging Face/Neon credentials are not bundled. Fixture operation makes no paid inference calls.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock
npm --prefix frontend ci
# Optional: copy local settings; defaults already start in fixture mode.
Copy-Item .env.example .env
.venv/Scripts/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173. API documentation is at http://127.0.0.1:8000/docs.
The Vite proxy connects `/api` requests and WebSockets to FastAPI.

For Linux/macOS, use `.venv/bin/python` instead of `.venv/Scripts/python`.
Keep both services on localhost during development; a public deployment needs authenticated controls,
restricted origins, and isolated generated-product execution.

## Verify the scaffold

```powershell
.venv/Scripts/python -m pytest backend/tests
.venv/Scripts/python -m ruff check backend
.venv/Scripts/python -m backend.scripts.export_openapi --check
npm --prefix frontend run check:contracts
npm --prefix frontend run typecheck
npm --prefix frontend run build
.venv/Scripts/python -m backend.scripts.doctor
```

After approved schema/route changes:

```powershell
.venv/Scripts/python -m backend.scripts.export_openapi
npm --prefix frontend run generate:api
```

`shared/openapi.json` and `frontend/src/shared/api-types.ts` are generated artifacts, not separately
maintained contract definitions. Python's `backend/app/shared/contracts.py` is authoritative.

## Developer kickoff

Read [AGENTS.md](AGENTS.md), [ownership](docs/ownership.md), the [product backlog](docs/product-backlog.md), and [roadmap](docs/roadmap.md).
Developer agents live in `.codex/agents/`. Reusable repo-local skills live in `.agents/skills/`.
The roadmap and task documents distinguish completed foundation work from future product gates.

- **A:** [integration starter tasks](docs/tasks/developer-a.md).
- **B:** [personas starter tasks](docs/tasks/developer-b.md).
- **C:** [evolution starter tasks](docs/tasks/developer-c.md).

Each starter specifies allowed files, contracts, validation and acceptance. Parallel agents must use
disjoint files or worktrees. No one should run an unrestricted “improve the entire repo” task.

## Credentials and dependencies

Set server-side settings using `.env.example`. Hugging Face requires `HF_TOKEN`, a served `HF_MODEL_ID`,
and a tested provider; a positive experiment budget is required before paid execution. `DATABASE_URL`
is the pooled Neon Postgres URL. `VIEWER_TOKEN` protects authenticated viewing when configured.
Provider/model availability and quotas must be verified before promising 1,000 completed sessions.

Docker is required for isolated selected-source execution; install/check it before the real integration
gate. Playwright's browser is installed separately with:

```powershell
.venv/Scripts/python -m playwright install chromium
```

Screenshots, replay captures and generated outputs go under ignored `artifacts/`, with database references.
Tokens, database URLs and screenshots containing secrets must not enter version control.

Optional Docker development: `docker compose up --build`. Both ports bind to localhost;
enter `local-fixture-only` in the persona viewer to authorize the container-to-container stream.
The compose setup deliberately runs fixture mode and does not import live credentials.
Container builds require Docker and have not been exercised on this machine if `doctor` reports it absent.

## Documentation

See [documentation index](docs/README.md) for architecture, contracts, dataset provenance, runtime-agent
rules, integration, decisions and phased roadmap. The two original planning briefs are preserved as
historical inputs; the current plan excludes AMD, ROCm, Figma and Adobe.
