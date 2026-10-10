# Developer A kickoff — project scraping and integration

Use `developer_a_integration` and `$repofusion-integration`. Read root AGENTS.md, ownership, architecture, API/data contracts and roadmap. Inspect current implementation before treating a starter as unfinished.

## Boundaries and inputs

Own `backend/app/features/integration/**`, `frontend/src/features/integration/**` and `backend/tests/integration/**`. Shared shell/contracts are coordinated, not unrestricted ownership. Do not edit B/C modules, inference, database or migrations. Inputs are original briefs, approved HF-only plan, canonical contracts and fixture summaries. Outputs are evidence/proposals/checks/version briefing plus readable discovery/validation/product UI.

## First three tasks

1. **Discovery vertical slice:** implement a source adapter with replaceable GitHub client and bounded source extraction. Test against explicit API fixtures and show cited candidate capability/proposal state. Keep Trending separate from star-sorted Popular; rate limits produce visible partial/failure state. Done: deterministic test fixtures map to canonical records and the view handles loading/empty/error/source state.
2. **Selection gate:** retain roughly five complementary proposals, record exact-pair and equivalent-purpose searches, inspect documented input/output meaning and select a feasible pair. No claim of novelty from missing search results. Done: selected pair has source commits/licenses/interface evidence and fixed independent execution fixtures; blocked assumptions are visible.
3. **Integration proof:** run each source independently, implement a narrow adapter, validate normal/invalid/incompatible/timeout cases, and expose it through the generated product. Done: actual product operation passes known checks and B receives the validated briefing/task catalog/version manifest. Fixtures alone do not close this task.

## Dependencies, checks and stop rules

GitHub/search/Docker access is a live gate, not a reason to stall fixture-backed coding. All extraction uses B's shared HF adapter; missing credentials remain explicit. A decides adapter language only after inspecting actual selected repositories. Simplify/switch the pair after the six-hour independent-execution gate.

Run relevant Python tests and frontend typecheck/build; export/regenerate/check contracts after approved schema edits. Preserve source/version evidence and obtain coordinated review before touching generated-product paths for v2.

## Progress log

2026-10-10 starter complete: scoped discovery adapter/store and frontend controls implement synchronous in-memory discovery with fixture default and bounded opt-in live GitHub reads, explicit source modes and failures. Known fixture candidates remain unvalidated. Offline discovery checks and combined schema/type/build checks passed; desktop/mobile browser smoke verified fixture discovery controls. Live repository selection, independent tool execution, research and integration remain gated. Next: inspect a real candidate pair and establish independent fixtures.


2026-10-10 source collection slice: added live-run-gated, commit-pinned README/license/requested documentation collection, bounded issue snapshots, byte/text limits, hash checks and visible partial failures. The UI exposes source inspection for live candidates. A real read of psf/requests pinned commit 611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60 and returned README, LICENSE and three issue records. This is a collector smoke test, not a selected integration pair. All 121 backend tests, lint, generated-contract checks, frontend typecheck and build passed. HF extraction/proposals, Trending, durable storage, selection and execution remain unfinished. Docker CLI exists but its daemon is unavailable on this machine.

Source inspection desktop/mobile browser check passed, including expanded source excerpts and no horizontal overflow at 390px. Local captures are under ignored artifacts/.
