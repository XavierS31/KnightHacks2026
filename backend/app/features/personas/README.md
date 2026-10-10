# Developer B offline kickoff

This feature owns an explicit in-memory replacement for **all expected A handoff categories**:
repository references (fixture identities; commits honestly unavailable), product version/URL,
briefing/limitations, concrete capability input/output schemas, initial sample state,
persona-linked tasks, fixed check IDs and expected outputs. The runnable loopback page is a
mock, not A's integration. No integration/evolution code, shared schemas or migrations are changed.

## Offline commands

From the repository root in PowerShell:

```powershell
# Build 500 deterministic fixture records/tasks in memory; all trial counters remain zero.
.venv/Scripts/python -m backend.app.features.personas.kickoff
# Inspect the entire mock A handoff (no secrets).
.venv/Scripts/python -m backend.app.features.personas.kickoff --handoff
# One actual Chromium interaction against a synthetic product; no HF request.
.venv/Scripts/python -m backend.app.features.personas.kickoff --browser
# Deliberate application error / unresponsive mock UI.
.venv/Scripts/python -m backend.app.features.personas.kickoff --browser --failure application
.venv/Scripts/python -m backend.app.features.personas.kickoff --browser --failure timeout
```

If Chromium is absent: `.venv/Scripts/python -m playwright install chromium`.
Each browser run starts a temporary loopback server, creates a fresh context and closes both.
Observed button IDs constrain decisions. Fixed card content determines mock success independently
of the policy. Navigation and the final check count toward the six-action limit. The two-minute
watchdog, per-action timeout and cooperative cancellation bound work. External requests are blocked.
Real screenshots and timestamped mock actions stay in memory and are discarded on exit. These
results do not create production sessions, feedback, stored artifacts or completed experiment counts.
The `timeout` mock intentionally leaves the UI unchanged; the scripted policy reports stopping,
not a fabricated provider timeout. The dashboard now also exposes a selected mock-trial run:
POST `/api/v1/personas/mock-trials/{persona_id}` returns a fresh canonical fixture Session and its
latest actual PNG via the existing stream. Loopback/viewer authorization is required. Retention is
twenty in-memory sessions with one capture each; four simultaneous reservations, one per persona.
Browser interactions are real mock mechanics; outcome remains `not_run` and mandatory counts zero.

## Credential gate (ready for user configuration)

Keep `APP_MODE=fixture` and `EXPERIMENT_BUDGET_LIMIT=0` for offline development. This mock harness
does not need any API keys, a GPU, Neon or HF credit. Do not put secrets in command arguments.

When ready for a **single representative HF configuration check**, put these in the ignored root `.env`:

```dotenv
HF_TOKEN=<fine-grained token with Make calls to Inference Providers>
HF_MODEL_ID=Qwen/Qwen3-32B
HF_PROVIDER=deepinfra
```

Then explicitly run:

```powershell
.venv/Scripts/python -m backend.app.features.personas.live_readiness --run --budget <authorized-small-limit>
```

This can consume credit: one logical request, with at most one transient retry. It tests a supported
target choice from synthetic input, checks the output and prints sanitized configuration/usage
metadata. It does not run browsers, review ingestion, persona generation or a batch. Missing/invalid
configuration fails rather than falling back to fixtures. The diagnostic uses conservative
pre-send dollar reservations and an exclusive ignored spending marker; do not delete/reset it to
reuse an authorization. Changing the model/provider requires a reviewed price/token policy.
This particular command caps small diagnostics at $4; no cap is new spending permission. It
overrides live settings for that call only, so APP_MODE can remain fixture. The legacy unguarded
`kickoff --hf-smoke` live branch is disabled. Full batches require C's durable ledger and measured
pilot forecast. Our already-used $4 authorization and diagnostics are in the runtime report.

Later gates: real permitted review sources/context; checked review extraction; C-coordinated Neon
storage/leases; A's validated real product; representative role evaluation; five pilots and a
20-person soak before 500 v1 trials. Preserve all persona/behavior/corpus/task/check IDs for v2.
Manual review exports or permitted HN sources can avoid an additional review API credential;
Reddit access must be verified before using its adapter. No automatic live review collection exists.

## Checks

```powershell
.venv/Scripts/python -m pytest backend/tests/personas -q
$env:B_BROWSER_TESTS = '1'
.venv/Scripts/python -m pytest backend/tests/personas/test_mock_browser.py -q
Remove-Item Env:B_BROWSER_TESTS
.venv/Scripts/python -m ruff check backend
```

Chromium checks cover success, application failure, unresponsive UI, invented targets, cancellation,
bounded actions, fresh-context isolation and rerunning after a failed attempt. Fixture tests enforce
source/capability honesty, task/check/state lineage, unique deterministic IDs and live fixture rejection.

## Review-corpus slice (library helpers; no mounted routes or storage)

`review_corpus.py` provides:

- `collect_hn_item`: one explicitly selected item from the fixed official HN API. Requests have a
  ten-second timeout and 64 KiB response cap; redirects, missing/deleted/dead records, mismatched IDs
  and invalid source data fail with sanitized codes. Authors/votes are not retained. HTML becomes
  normalized plain text. Callers must supply relevant software/selection context and a documented
  access basis; this does not automatically approve reuse of every retrieved review.
- `CollectedReview`: a bounded import format for manual/permitted exports from other supported
  categories. It preserves source identity, original permalink, dates, context and normalized source
  text in memory. Callers must verify retrieval and permission independently; a valid payload alone
  cannot prove these. Raw imported source text must already be plain text.
- `curate_review`: an explicit manual paraphrase/excerpt/privacy step. The excerpt must occur in the
  normalized original text. The source hash is computed from that text, never from the summary.
  Obvious email/handle/token patterns are rejected from model context; manual review must also remove
  author names and other sensitive information. Paraphrase accuracy requires independent review.
- `freeze_corpus`: up to 100 curated real-source records; reject repeated source IDs, URLs, hashes,
  fixture leakage and context mismatch. Selection limitations are mandatory. Snapshot order is stable;
  its SHA-256 version binds timestamps, source hashes, excerpts, context and curation metadata. All
  returned objects are detached copies of immutable canonical JSON. No durable state is claimed.

`behavior_extraction.py` sends only reviewed excerpts/paraphrases/context through B's shared HF
adapter, caps model input at 20 KiB, and checks returned schema, source IDs, duplicate patterns and
literal excerpt support. It retains corpus version and adapter prompt/model/configuration provenance.
The result is **pending independent support review**, not an approved `SoftwareBehaviorProfile`.
Matching an excerpt does not establish the correctness of a tendency, trigger or trial policy.
It neither generates live personas nor bypasses budgets/review. Source text is untrusted prompt data.

HN documentation: https://github.com/HackerNews/API . No additional HN API key is required by this
public item endpoint. Reddit has no automatic adapter here; verified access or a permitted manual
export remains necessary. C owns eventual storage/migrations; no database change is included.

```powershell
.venv/Scripts/python -m pytest backend/tests/personas/test_review_corpus.py -q
```

Tests use invented source records and fake HTTP/HF clients, never real reviews or paid inference.
The earlier corpus slice used offline tests only. Subsequent actual source/HF diagnostics, runtime,
population/budget foundations, checks and remaining gates are recorded in
[B's runtime report](../../../../docs/tasks/developer-b-runtime-report.md). The first real extraction
was independently rejected; a revised request failed. No approved live population or real trials.

`population.py` freezes supported behavior plus exact deterministic identities and intentional
coverage assumptions; `runtime_policy.py` supplies bounded HF browser/feedback roles to
`session_execution.py`. Live execution requires A validation and C durable evidence. In-memory
budget/approval/store helpers do not establish persistent reviewer authentication or job recovery.

Frontend stream-validation checks:

```powershell
node --test frontend/src/features/personas/streamValidation.test.mjs
```
