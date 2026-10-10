# Automatic repository research

The main dashboard uses the automatic research-study pipeline described in [the current design](../../../../docs/opportunity-discovery.md). Discovery starts source research, repo briefs, substantial repurposing proposals, GitHub equivalent-product searches and scope/novelty critique without manual repo selection. Public reads and paid HF calls are bounded and failures remain visible.

Legacy discovery/source routes below remain compatible; their old manual UI is no longer the default.

# Discovery starter

`POST /api/v1/discovery-runs` accepts `mode` (`fixture` by default, or `live`),
`discovery_mode` (`popular`, `trending` or `emerging`), a single-line GitHub `query` (up to 200 characters),
and `limit` (1–30). It is a synchronous read, returning 201 with the completed metadata
result or synthetic fixture result; it is not a durable queue job. GET by UUID returns
that same record while retained in the current process.

Fixture requests never call GitHub or a model. Live requests require server `APP_MODE=live`.
`GITHUB_TOKEN` is optional for public reads, but unauthenticated GitHub quotas are lower.
The adapter makes one fixed-host repository search, sorted by stars, excluding forks and
archived repositories. It does not clone or execute source code, generate proposals,
inspect interfaces, or establish Trending popularity, novelty or integration correctness.

Cache: five minutes, at most 20 searches per process. Source timestamps are retained on
cache hits. Run retention: at most 100 records per process, lost on restart, no Neon writes.
Multiple API workers have separate caches and records, so run reads are not reliable across
workers. Use a single API process for this starter; durable persistence is a next milestone.

The source URL is the exact GitHub metadata request without authentication credentials.
Repository URLs are constructed from checked owner/name identities. Description text is
untrusted and rendered as text. Errors are sanitized, including upstream authentication,
rate limiting, timeout, incomplete search and malformed-response failures.

Next: pin commits/licenses; collect bounded documentation/issues; consume B's HF inference
adapter for cited extraction; retain proposals and research; independently execute a pair
with fixed acceptance fixtures before creating an adapter. Coordinate Neon persistence with C.

## Commit-pinned source inspection

After a real discovery run, `POST /api/v1/discovery-runs/{id}/repositories/{repository_id}/sources`
accepts `documentation_paths` (up to three unique relative `.md`, `.rst` or `.txt` paths)
and `issue_limit` (0–10; default 5). Collection requires server `APP_MODE=live` and a repository
belonging to a live discovery run. Fixture runs never trigger source reads.

The collector resolves the latest default-branch commit, then reads README, license and requested
files using that exact SHA. File evidence includes commit-specific URLs, verified Git blob IDs,
full-content SHA-256 and collection timestamps. SPDX metadata is a collection-time hint; it does
not approve licensing. Issues are mutable, timestamped snapshots, not commit-pinned evidence.
GitHub returns pull requests in the issues endpoint; these are excluded without requesting extra pages.

Only `api.github.com` is contacted, redirects are disabled, requests have a 15-second timeout,
responses are capped at 2 MB, decoded files at 1 MB and selected text at 20,000 characters across useful sections.
No code, Markdown HTML, links from repository content or model instructions are executed.
Missing/invalid/oversized files and issue failures yield a visible partial snapshot; failure to
resolve a commit prevents collection. Rate limiting stops remaining optional requests.

`GET /api/v1/source-snapshots/{id}` reads one of at most 100 process-local snapshots. In live mode
with `DATABASE_URL`, live runs, snapshots, extractions and proposal previews are also stored in the
database (`discovery_repository.py`, migration 004). Their `storage` field is then `database`, and a
read falls back to the database after a restart. Otherwise records stay in memory. The UI offers inspection
for real candidates and shows source excerpts, provenance, missing files and collection limitations.

Next gates: coordinate persistence with C, use B's verified HF adapter for cited capability/proposal
extraction, then perform pair research, independent execution and adapter validation.
