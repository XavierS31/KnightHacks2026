# Developer B backend

Read root AGENTS.md, docs/tasks/developer-b.md and the repo-local repofusion-personas skill.
Own this feature and its tests; shared inference is B's coordinated boundary.
Current endpoints are fixture-only. APP_MODE=live must never expose fixture trials as observations.
Viewer credentials go in HTTP authorization or the first WebSocket message, never URLs.
Unauthenticated fixtures require loopback connections and permitted browser origins.
Never create frames or action evidence from 3D props. Browser execution requires an isolated
context, observed targets, approved product origin, scoped backend state and deterministic checks.
Coordinate storage with C and contracts with A before adding real persisted sessions.
