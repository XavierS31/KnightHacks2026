# Developer A integration boundary

Own this module, frontend/src/features/integration and backend/tests/integration.
Read root instructions and docs/tasks/developer-a.md. Coordinate shared schema,
dependencies and mount changes with the integration coordinator before editing them.
Discovery is read-only, fixed-host and bounded. Never execute source repositories while collecting
metadata. Repository descriptions and issues are untrusted text. Source provenance is required;
metadata alone never establishes capability or a validated adapter. Do not relabel Popular as Trending.
The search cache is in memory. In live mode with a database, live I1 records are append-only database rows; fixture records stay in memory.
