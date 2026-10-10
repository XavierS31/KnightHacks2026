# Developer B runtime progress — 2026-10-10

This follows the mock handoff and corpus work in merged PRs #3 and #4. Available runtime
foundations are implemented; P1/P2/P4 remain partial and P3 remains unexecuted. No real product
trial, Neon write, 500-person live population, full experiment or v2 promotion is claimed.

## Changes delivered

- `population.py`: independent support decisions separate from extraction; context/citation and
  immutable-lineage validation; bounded HF fictional details with deterministic persona/scenario/task
  identity; intentional coverage quotas, pilot versus exact-500 configuration, and frozen versions.
  Complete-size tests use fake HF. Approval attestations are not authenticated reviewer identities.
- `inference_budget.py`: atomic single-process reservations before sending, retry/output/input
  allowances, conservative failed/unknown charges, bound-violation blocking, protected mandatory
  capacity, and an assumption-only 1,025-session forecast with 30% time contingency. C still needs
  durable accounting/leases; this is not restart-safe experiment storage.
- `session_execution.py`: A-validated live handoff and C-durable evidence gates, scoped state reset,
  fresh contexts, same-origin requests, observed click/type/select targets, deterministic checks,
  six-action maximum including navigation/check, timeouts/cancellation, actual PNG captures and
  same-session feedback references. Mock mechanics remain fixture/not_run.
- `runtime_policy.py`: budgeted HF browser/feedback roles receive bounded behavior/preferences,
  fictional assumptions, observed targets and own-session actions. Low initial relevance cannot
  skip participation. Upstream reviews cannot establish generated-product defects.
- `fixture_operations.py` and B router: authorized loopback POST
  `/api/v1/personas/mock-trials/{persona_id}` returns canonical Session. New ID per run; summary
  exposes latest per persona; old IDs remain within retention. Four concurrent reservations,
  per-persona busy guard, twenty retained sessions and latest-only captures bounded to 2 MiB PNG.
  State is in memory and lost on restart; no production queue is claimed.
- World/viewer: run selected mock trial, preserve pending work across selection changes, display
  exact-session PNG/actions/feedback, reject foreign/malformed/reordered events, and track capture
  staleness independently of heartbeat. Only bounded inline PNGs are accepted. A coordinated the
  additive route; canonical schemas unchanged, OpenAPI/TypeScript regenerated.
- `live_readiness.py`: opted-in small smoke with price/token bounds and exclusive crash/restart
  spending marker. Legacy `kickoff --hf-smoke` cannot bypass dollar reservations.

## Actual external evidence

The human authorized **$4 total** for smoke/small pilots, not the 1,000-session experiment.
`Qwen/Qwen3-32B` / `deepinfra` through HF Providers returned supported `click` / `load-sample`,
84 reported tokens, 4,203 ms latency, zero retries. Request ID:
`4767d8de-8d82-4e6d-b199-bed56319234c`.

Two real public HN comments were collected with six bounded API reads including candidate inspection
and adapter re-reads. No authors or full review text retained. The purposive one-thread sample
concerns mock-product category preferences only: [notes-to-card workflow](https://news.ycombinator.com/item?id=39166209)
and [interest in deeper learning](https://news.ycombinator.com/item?id=39165803).
It establishes neither representative demographics nor real product defects. An inspected comment
involving a child was excluded. Corpus version:
`8b66821e8078afa81c8a3cfe69b26dcfd19d876cb1cb329aa8ddea6188a07547`.
Public endpoint reference: [official HN API](https://github.com/HackerNews/API).

First HF extraction passed structured/literal-citation validation; an independent agent **rejected**
its sole pattern for unsupported collaboration classification and feature advice outside actual
capabilities. Zero patterns approved. Draft/rejection are retained unchanged in ignored artifacts.
After tightening bounded-policy instructions, a fresh extraction ended `INFERENCE_REQUEST_FAILED`.
No approved draft and no live generated personas. Collection-stage corpus limitations describe
collection only; later real inference is separately recorded here.

Conservative aggregate accounting: **$0.01836714**, against $4 authorization. Failed/unreported
attempts keep full worst-case charges. Estimates use [published model pricing](https://deepinfra.com/Qwen/Qwen3-32B),
verified 2026-10-10, at priority ceiling $0.12 input/$0.42 output per million tokens (normal
$0.08/$0.28); **not a provider invoice**. No further paid calls after the second failure. Never
reset existing markers or treat another invocation as fresh authorization. Local app mode remains
fixture with budget setting zero. Token configuration already worked; no additional token needed now.

Local ignored evidence: `artifacts/devb-live-readiness-20261010.json`,
`devb-review-pilot-candidates.json`, `devb-review-extraction-20261010.json`,
`devb-independent-support-review.json`, `devb-review-extraction-retry-20261010.json`, and
`artifacts/b-ui-smoke/`. Credentials, raw prompts, full source text and captures are not committed.

## Verification

387 combined backend tests pass after reconciling C PR #21 (362 after A #7/#8, 343 after #5, 317 originally),
with one opt-in real-Docker check skipped on this Windows host. Actual local Chromium checks, six standalone stream-validation tests,
Ruff, frontend typecheck/build and generated-contract checks pass. Final test counts are recorded
in [status](../status.md). Build retains the existing large persona/3D chunk warning; test client
emits its dependency deprecation warning. Dependencies unchanged.

Actual desktop/mobile UI smoke verified rendered PNG decoding, four exact-session actions,
switching without foreign frames/actions, switching during a pending rerun without cancelling,
and returning to its new session. At 390 px, document width equals viewport width. Only owned
smoke servers were started/stopped. Mandatory experiment counts remain zero throughout.

## Remaining work, in dependency order

1. **B source/model gate:** reviews relevant to A's real product, reliable extraction, independent
   support approval and representative generation/browser/feedback role evaluation. Two category
   reviews and a configuration smoke do not finish P1/model acceptance.
2. **A handoff now available:** upstream PRs #7/#8 provide SourceTable v1's frozen manifest, local
   product URL, task/check templates and reset semantics. See [A handoff](../handoffs/developer-a-v1.md).
   B still needs a feature-owned consumer that verifies compatibility and binds templates to exact
   persona scenarios; the existing mock operation is not that consumer. Portable runtime validation
   remains required on other computers.
3. **C blocker:** coordinated immutable corpus/approval/population storage, authenticated reviewer
   identity, durable actions/feedback/frame artifacts, atomic spending, queue leases and recovery.
   Live execution rejects an in-memory sink. C needs intended server-side DATABASE_URL for Neon;
   the mock UI needs no additional key.
4. **B population/first trial:** generate/persist exactly 500 review-informed fictional personas,
   then one real checked trial/viewer. Freeze identities/versions for v2.
5. **B capacity:** five product-backed pilots, twenty-person soak, measured tokens/rate limits,
   CPU/memory/throughput with four workers; measured forecast and separate full-batch authorization
   before 500 v1 trials. Current forecast is assumptions, not measured throughput.
6. **B/C:** all 500 matched v2 trials after human approval; honest matched denominators.

Keep tokens server-side in ignored settings, never chat/viewer. Reconsider credit/configuration
after source/model reliability, A/C gates and measured pilot forecast. Current approval does not
authorize the full experiment, purchases, deployment or v2 promotion.
