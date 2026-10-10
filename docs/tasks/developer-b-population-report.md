# Developer B — SourceTable review-informed population

2026-10-10. The requested collection → HF extraction → independent support review →
500-person generation is complete **with durable local files**. Neon write/readback
is blocked by missing server-side `DATABASE_URL`. No browser trial was executed.

## Actual evidence

Five real public upstream issue bodies were fetched through bounded official GitHub
API reads. Only privacy-curated excerpts (at most 25 words per source), paraphrases,
IDs, dates, canonical URLs and normalized-content hashes were retained. Full bodies,
authors and attachments were not retained. These are related-tool reports, not
SourceTable reviews or evidence of its defects:

- [pdfplumber #311](https://github.com/jsvine/pdfplumber/issues/311): investigation of unexpected detected table boundaries.
- [pdfplumber #140](https://github.com/jsvine/pdfplumber/issues/140): inspection of extraction with blank outer columns.
- [Frictionless #809](https://github.com/frictionlessdata/frictionless-py/issues/809): request for a concise schema-validation example.
- [Frictionless #766](https://github.com/frictionlessdata/frictionless-py/issues/766): expectation of visible typed-validation errors.
- [Frictionless #1633](https://github.com/frictionlessdata/frictionless-py/issues/1633): expectation of an actionable field-level report.

Selection is purposeful troubleshooting coverage from two upstream projects. It
establishes no demographics, demand, prevalence, consensus or representative sample.
Access/reuse limitations and [official API documentation](https://docs.github.com/en/rest/issues/issues#get-an-issue)
are recorded in the collector and corpus. Public accessibility is not a blanket content license.

HF `Qwen/Qwen3-32B` through `deepinfra` produced an initial syntactically valid
draft. A separate agent rejected cropping and deliberate-error policies because
they did not transfer to SourceTable's eligible mandatory task. A second call
failed; the third, with exact product context, yielded one independently supported
tentative source-inspection pattern from #311. The reviewer re-fetched the original
source and checked its full normalized hash and exact excerpt, then checked the
actual cell-inspection control and six-action task. The preference is conditional;
no discrepancy in the fixed sample is asserted. The reviewer is an independent
model, with local operator attestation, **not an authenticated human review**.

500 fictional personas, scenarios and tasks were then generated with 100 successful
five-record HF requests. All 500 persona/scenario/task IDs are distinct. There are
332 distinct display names; names are fictional labels and may repeat. Names,
skills and constraints came from HF; cohort/role/device/location are explicit
scenario assumptions. Each cohort has 100 records. All profiles carry the same
approved tentative pattern, not 500 independently learned human behavior profiles.
Only cited evidence enters each profile; all five collected reports remain in the corpus.

An interrupted provider request after 89 batches was charged conservatively. Resume
reused those 445 records and generated the remaining 55, without replacing failures
with fixtures. The final 3,335,544-byte population snapshot was validated and fsynced;
100 immutable local chunks and a reservation-before-send journal remain available.
Local data is ignored by Git and is **not bundled into the PR**.

| Frozen artifact | SHA-256 version |
| --- | --- |
| Corpus | `6bc830815942894c67ff9994c8ad6211d0986b1eb83b459b5a53f8843f121d26` |
| Approved behavior | `91e5d0dca2ead64cceff4225a100a183cfb633af1e0a6a6106746c881df23460` |
| Population | `9b54b97f703dc637d3bf56bba3e5a1891fce1bfd16638a75988b8aaf4821e535` |
| A manifest | `e31ef6db10645fef008a8ae5279434f7f0bce48ab80d3acfa8f59bffa0cbe4b1` |

Local files: `artifacts/sourcetable-review-corpus.json` and
`artifacts/sourcetable-generation/{population.json,population.sha256,approved-behavior.json,handoff-binding.json,extraction.json,support-review.json,support-review-audit-v3.json,support-review-rejected-v1.json,budget.json,report.json,chunks/}`.

The generation preflight reserved a worst-case $0.78980640 for 100 calls/200
possible attempts. Conservative aggregate accounting including earlier B smoke,
extraction failures and generation is **$0.05753544 / $4**, leaving **$3.94246456**.
The current run charged $0.03916830; earlier charges were $0.01836714. This uses the
documented [priority price ceiling](https://deepinfra.com/Qwen/Qwen3-32B), not a
provider invoice. Unknown/failed requests retain their full bound. No credit purchase
or 1,000-session experiment was authorized or performed.

## Changes and checks

B added bounded GitHub issue intake, exact frozen A-manifest consumption, contextual
extraction, checkpointed five-record generation, exclusive local spend accounting,
whole-run forecast and a generation/persistence CLI. C implemented migration 003
and an atomic immutable corpus/approval/population repository with readback checks,
bounded SQL batches and separately versioned evidence per corpus. B reviewed the
consumer schema; repeated source IDs can appear in new corpora without rewriting old evidence.

Latest merged C work was integrated before PR preparation. C's migration 002 is
preserved; the population migration is 003, with no independent transaction wrappers.
The runner lists all three checksums without contacting a database. A documentation
merge retained both owners' progress. Windows checkout CRLF was reconciled locally
by restoring three UI files from Git blobs proven to match A's frozen fingerprints,
without changing their tracked content. Coordinated C QA writes now use UTF-8/LF,
and comparison tests explicitly read UTF-8. No fixed check or fingerprint was weakened.

523 backend tests passed with real local Chromium checks enabled; 18 unavailable
Docker/database checks skipped. Ruff, OpenAPI drift, generated TypeScript drift,
frontend typecheck and build passed. TypeScript was regenerated to normalize checkout
line endings; no schema/API change was introduced. Existing test-client deprecation
and large frontend chunk warnings remain. No UI behavior changed in this slice.

## Remaining work, sequentially

1. **Neon gate (#3 partial):** set intended server-side `DATABASE_URL` in ignored
   `.env`; apply C's reviewed ordered migrations 001, 002 and 003 with recorded checksums;
   save the frozen bundle and prove readback/rollback. Repository tests currently use
   fake connections; no live Neon success is claimed. Hosted authenticated reviewer
   identity, atomic multiworker spend, leases and durable action/frame/feedback sinks
   remain separate work.
2. **Runtime gate (#2 partial):** the frozen SourceTable catalog is consumed and
   its normal check is bound to all 500 exact scenarios. Local image/hash/process
   verification is still missing on this Windows host. Error/recovery checks require
   seven/nine actions; A must supply independently validated alternatives fitting the
   six-action mandatory limit before those can enter coverage. No hash gate or budget
   was weakened.
3. Connect the verified runtime and durable evidence sink; execute one checked
   product-backed trial, then five pilots and a twenty-person soak. Evaluate HF
   action/feedback behavior and measure costs, provider limits and throughput.
4. Obtain separate full-experiment budget authorization and execute all 500 v1
   trials; show ten exact real sessions. Human-reviewed v2 promotion and all 500
   matched v2 trials follow. **Completed mandatory trials remain zero.**

P1/P2/P4 remain partial; P3 is unexecuted. Population generation is complete locally,
not completion of all production persistence or trial acceptance criteria.

To validate/reuse the existing local snapshot and attempt Neon persistence after
configuration/migrations, use the same directory and original authorization boundary:

```powershell
.venv/Scripts/python -m backend.app.features.personas.source_population_run --run --remaining-budget 3.98163286 --corpus artifacts/sourcetable-review-corpus.json --directory artifacts/sourcetable-generation --persist-neon
```

The journal subtracts this run's charges from that original boundary. Reusing the
finished snapshot makes no HF request. Never delete a paid lock/journal or change
directories to reset accounting. A crash lock requires reconciliation; local journals
do not provide a distributed experiment ledger. Keep secrets out of chat and artifacts.
