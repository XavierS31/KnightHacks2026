# Discovery starter

`POST /api/v1/discovery-runs` accepts `mode` (`fixture` by default, or `live`),
`discovery_mode` (`popular` only), a single-line GitHub `query` (up to 200 characters),
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
