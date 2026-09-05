# ED-Finder Agent Contract

This file defines current repository rules for automated coding and review
agents. It does not independently authorize product, architecture, or
production changes.

## Authority chain

Read [`README.md`](README.md), then use the current authority for the surface:

1. [`docs/ROADMAP.md`](docs/ROADMAP.md) — programme, order, and decision gates.
2. [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) — V3 technology and application ownership.
3. [`docs/colonisation-redesign/spatial-platform-product-contract.md`](docs/colonisation-redesign/spatial-platform-product-contract.md) — product/features/truth.
4. [`docs/colonisation-redesign/spatial-platform-architecture-decision.md`](docs/colonisation-redesign/spatial-platform-architecture-decision.md) — renderer-neutral spatial ownership.
5. [`docs/development/v3-browser-validation-lanes.md`](docs/development/v3-browser-validation-lanes.md) — browser acceptance authority.
6. [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) — production/runtime boundary.

[`docs/development/v3-coordination-control-plane.md`](docs/development/v3-coordination-control-plane.md)
supports implementation coordination only. Older stages, audit documents,
receipts, installed dependencies, Git history, and retained code are evidence;
they never override this chain. See [`docs/archive/README.md`](docs/archive/README.md).

## Current programme and application

- Stage 27 — One Spatial Platform is current. The roadmap controls execution
  order and open gates.
- [`apps/web/`](apps/web/) Svelte/SvelteKit is the sole V3 browser target. A
  fresh Babylon renderer is the V3 spatial target.
- Svelte owns routes, application/domain orchestration, panels, text, keyboard,
  and accessible DOM. Babylon owns spatial presentation, picking, and camera
  mechanics, never mechanics, ranking, persistence, or planning.
- Colony Planner remains the detailed planning and persistence owner. Renderer
  interaction must not silently change plans or canonical evidence.
- [`frontend/`](frontend/) React/R3F/Three and Stage 26 are historical migration
  and behaviour evidence only. R3F won Stage 26; it is not V3 architecture or
  current production authority.
- PR #601 is the active integration lane. Current known head
  `12eebac48ca9286e0fd8c180cc5f552dc922d07e` contains the real
  Explore/Finder → Babylon → Inspect slice and Review Lab rebase, but exact-head
  validation remains red/stabilizing. Do not describe it as green or complete.

Search/index/grid/cluster architecture, PostgreSQL 18 derived-data bootstrap,
and Ratings v3.4 versus archetype judgement remain explicit roadmap decisions.
Do not settle them by implementation inference.

## Repository state and change scope

- `main` is protected; use the exact selected branch/base and a pull request.
- Run the strict repository state resolver/preflight when required.
- Preserve unrelated work. Do not reset, rewrite, force-push, or broaden task
  scope to clean up adjacent history.
- Treat code and tests on the selected branch as implementation evidence under
  the authority chain, not as permission to revive an old architecture.
- If a requested operation has no current procedure or requires new authority,
  stop instead of reconstructing one from history.

## Infrastructure and operations

Production is `ed-finder-prod` at `nb79a3d.mevnode.com`, using PostgreSQL 18.
Hetzner/V2 is gone. Old runtime, cron, database, deployment, backup, recovery,
and rollback receipts are historical only.

Contabo hosts three self-hosted Codex runners. It is not production and is not
automatically the live-checkpoint host. Checkpoint destination, trust,
retention, and recovery purpose require a later explicit decision.

Production commands must come from current V3 authority that explicitly names
the target and safety boundary. Do not infer them from root Compose, server-side
paths, old runbooks, retained dumps, or operator helper names. Do not access or
mutate production during ordinary coding tasks.

The current GitHub-hosted replacement-host operator workflow is
`.github/workflows/chatgpt-ed-new-ops.yml`. It uses the `ED_NEW_OPERATOR_*`
credential boundary and pinned host trust. Never weaken host verification, use
runtime `ssh-keyscan`, expose credentials, or broaden allowlisted operations by
inference.

The experimental Ollama/Octopus test residue has been removed from production.
Do not treat it as architecture or restore it through old evidence.

## Application and route ownership

The V3 target is Svelte 5/SvelteKit 2/TypeScript 6, Vite 8, Node 24, and pnpm
11 under `apps/web/`. The package and lockfile there control exact dependencies.

Same-origin ownership is fixed:

- FastAPI owns `/api/*`, exact `/openapi.json`, and numeric `/s/{id64}`.
- SvelteKit owns all other application/static routes and the SPA fallback.
- Do not add a frontend route or backend catch-all that blurs this boundary.
- Preserve typed API contracts and regenerate/check clients when FastAPI
  request or response shapes change.

The checked-in backend validation environment still uses repository-pinned
Python 3.12. New V3 backend implementation targets CPython 3.14 with `uv` as
reviewed slices land; do not claim that migration early.

## Data and services

- Use disposable/test databases, parameterized SQL, bounded inputs, and
  fail-closed validation.
- Bulk writes must follow
  [`docs/development/bulk-database-write-safety.md`](docs/development/bulk-database-write-safety.md).
- Never attach or wholesale-restore a V2 PostgreSQL physical directory into
  PostgreSQL 18.
- Public/source data and derived indexes are rebuildable. Redis/Valkey cache
  state is disposable; NATS/JetStream transport state is not canonical truth.
- Do not create a production database read/write lane without explicit current
  production authority.

### Named exception: EDDN simulation ingest

`apps/api/src/ingest/eddn_client.py`, controlled by
`EDDN_SIMULATION_INGEST_ENABLED` and defaulting on, is a deliberate background
task consuming the public EDDN feed. It is not authority for a general journal
import scheduler, service, timer, or journal-import canonical promotion.

## Validation and acceptance

Run focused checks proportional to the touched surface, then every applicable
protected check. Do not weaken a test to make a PR green; when a governance
contract intentionally changes, update the test to protect the new durable
invariant.

Product E2E/Visual Acceptance and Review Lab are distinct V3 browser lanes.
Both use `apps/web` + Babylon. Product acceptance proves the real user journey;
Review Lab varies only synthetic data and its isolated environment. Neither
substitutes for the other.

Every PR must satisfy
the [Pull Request Acceptance Policy](docs/development/pull-request-acceptance-policy.md)
for the exact latest PR head SHA. Both Codex Review
(`chatgpt-codex-connector`) and Octopus Review must satisfy that exact-head
policy. Green CI alone is insufficient: required reviews and substantive
finding dispositions must also be complete. User-visible changes require
appropriate visual and accessibility evidence.

## Trust and secrets

Codex review is a reviewer path. Repository writes must preserve the separation
between unprivileged execution, sealed result, and trusted compare-and-swap
writer; task text must never control branch routing or expected remote SHAs.

Never commit or print passwords, credential-bearing DSNs/URLs, tokens, OAuth
secrets, SSH/private keys, recovery codes, or private production environment
files. Use scoped secret paths and keep sensitive values out of arguments,
logs, artifacts, and frontend builds.

When instructions conflict, current infrastructure status governs production,
the roadmap governs programme order, and the product/architecture/stack/browser
authorities govern their named surfaces. Fail closed on missing authority.
