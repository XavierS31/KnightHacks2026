# Issue #13 — evidence-linked improvement handoff

The E2 implementer, isolated QA and release composition exist. Closing #13 still requires
two or three improvements supported by executed E1 evidence, review of A's boundary,
QA on the frozen runtime and human approval of the resulting v2. A passing scaffold test
does not establish any of those live approvals.

## Implemented follow-up

The live analysis API now saves its checked report in C's existing `analysis_records` tables
before returning it. The record includes all role provenance, normalized session/action
references and SHA-256 fingerprints of the analyzed sessions. Retrying the same report is
idempotent. No new migration or API payload is required. Fixture reports stay in memory.

A live `POST /api/v1/improvements/{id}/patch-runs` now requires that `id` resolve to a supported
proposal in a stored E1 report. The proposal must belong to a fully evidenced product cluster.
Its cited actions must belong to its own finished sessions, on A's frozen v1 version, with
product feedback rather than infrastructure failures, irrelevant outcomes or unexecuted tasks.
The current evidence must match the saved fingerprints. Changing an acceptance check,
priority estimate, title or supporting-session list requires a new reviewed E1 proposal;
the caller cannot replace them in the improvement body.

The proposed scope is `product/ui` or a subset of its three exact files. It remains a proposal
until the existing human scope review. Backend code, the adapter, evaluator, fixed checks and
manifest are outside that boundary. The initial lifecycle event records the E1 report and
proposal IDs. Patch runs and v2 candidates still live in memory; durable run/version storage
remains unfinished.

E1 also now reads the worker's authoritative `sessions.stream_mode` and `sessions.stop_reason`
columns. Legacy provenance fields are no longer mistaken for those values.

## Operator sequence once executed evidence is available

1. B persists a checked v1 session, its actual actions and synthetic feedback using the existing
   session repositories. Register the validated v1 version through A's version repository.
2. Run live analysis for its experiment with server-side HF configuration and an authorized
   budget. The API persists the report; submitted live sessions remain forbidden.
3. Pick a supported proposal and a bounded scope. In Python,
   `improvement_intake.improvement_from_report(report, proposal_id, allowed_paths, sessions,
   frozen_v1_base().version_id)` constructs the exact `Improvement` body. Both report and sessions
   must come from the repositories, not illustrative UI suggestions or manually invented evidence.
4. Create a patch run. A human reviews the proposed scope; a separate implementer proposes
   bounded edits through the HF role or the deterministic edit submission.
5. Run QA against the configured frozen image. Each run must pass all fixed checks. A failed run
   cannot enter a release, and v1 remains unchanged.
6. Compose two or three distinct passed runs. Run QA again on the combined release, then present
   its diff, E1 citations, individual and combined results to the human reviewer. Only explicit
   approval may promote v2. No automated approval is authorized by starting this task.

The missing-proposal response is `409 E1_PROPOSAL_REQUIRED`; an altered proposal or changed
evidence returns `422 E1_EVIDENCE_MISMATCH`; unavailable storage returns `503 DATABASE_UNAVAILABLE`.

## Observed execution gates, 2026-10-10

Read-only native Python queries to the configured Neon database succeeded. The local Neon context
selects project `delicate-lab-50091983`, branch `dev`. The queried database held zero non-fixture
sessions, feedback records and product versions, and zero analysis records. No database write or
migration was performed. These counts do not contradict the separately persisted configured
500-person population: configured personas are not executed trials.

The local SourceTable image is
`sha256:9defc8bf9def9500fec38892bc8ed973468f692ffa04fa5593c0cd19c6d7814d`.
A's frozen image is
`sha256:998df8c083e6094f9aac9a347b2fe61670dcc4ea9407e17b57accba128193d5e`,
which is absent locally. The configured artifact directory has no trial snapshots or runtime
image record, and HF is unconfigured in this checkout. The frozen-image gate is not relaxed.

Validation uses invented test evidence in disposable local PostgreSQL schemas. Docker/Chromium
QA uses the available image rebuild and keeps that distinction in its evidence. A no-op Extract
handler must fail every fixed browser check. No real E1 proposal, new persona trial or human v2
approval is established by these checks; issue #13 remains open.

## Validation of this follow-up

- Full backend suite with disposable local TLS PostgreSQL and opt-in QA on the existing image
  rebuild, after rebasing onto master with B's single-pilot evidence path: **676 passed,
  22 skipped**. Real Docker/Chromium checks include the no-op Extract
  regression, individual patches, combined release, rejection and rollback. New deterministic
  intake/persistence tests use invented records, with no mocks or paid inference.
- Backend lint, OpenAPI drift, generated frontend contract drift, typecheck and production build
  pass. Existing test-client deprecation and frontend bundle-size warnings remain.
- The updated live endpoint was exercised against Neon with an explicitly synthetic unbacked
  improvement: `409 E1_PROPOSAL_REQUIRED`. Subsequent read-only counts stayed zero. No patch run,
  database write, HF call or trial was created by that probe. Sanitized local gate evidence is
  `artifacts/issue-13/readiness.json`.
