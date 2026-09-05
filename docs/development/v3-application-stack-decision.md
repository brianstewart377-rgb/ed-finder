# ED-Finder V3 Application Stack Decision

**Decision date:** 2026-09-04  
**Status:** stack lock for the V3 application rebuild  
**Tracking:** issue #574  
**Base:** `main` after PR #568 (`da35e1872c96376d78137d56a07a9bf5ff27662a`)

## Purpose

ED-Finder is using the V3 infrastructure cutover as the point to make one deliberate application-stack reset rather than migrating React, the spatial renderer, package management, browser testing, Python packaging, runtime services and deployment mechanics independently.

This document is the technology authority for the new application baseline. It does not itself authorize production deployment, database mutation, a Babylon production cutover, or any later Stage 27 slice. Those actions still require their normal reviewed stage/operator boundaries.

`apps/web/` is the sole destination for browser application implementation. The current React/R3F tree is temporary source evidence for behaviour and parity while the hard replacement is completed; it is not a runnable parallel lane. The replacement branch must remain unmerged until equivalent accepted coverage and behaviour exist.

## Post-cutover runtime evidence

Read-only V3 application status run `33817618652`, executed after PR #568 merged, established the starting point:

- `ed-finder-prod` and the expected V3 listeners are reachable;
- all required V3 containers were running and PostgreSQL was healthy;
- origin `/api/health` returned HTTP 200 with `database=connected`;
- the running API was the stale `edfinder-v3-api:phase4c-r5` image and reported `build_sha=unknown`;
- the running origin exposed neither `/openapi.json` nor the current `/api/auth/*` Frontier OAuth routes;
- no built frontend index existed inside the API image or at `/opt/ed-finder/frontend/dist`;
- the host checkout was clean but remained on historical branch `infra/multi-target-operator-mcp`, not current `main`;
- the public edge was partial/inconsistent: public root and anonymous session responded, while public health returned 503.

Therefore the next engineering problem is **immutable application release/deployment**, not PostgreSQL resurrection and not manual patching of the Phase4C container.

## Locked stack

### Frontend and browser application

| Layer | Locked decision |
|---|---|
| Language | **TypeScript** |
| Initial compiler | **TypeScript 6**; move to TypeScript 7 when Svelte tooling supports it cleanly without a dual-compiler path |
| UI framework | **Svelte 5** |
| Application framework | **SvelteKit 2** |
| Production delivery | **Static SvelteKit output** via `adapter-static`; no Node application server in production |
| Build system | **Vite 8 / Rolldown** |
| Tooling runtime | **Node.js 24 LTS** |
| Package manager | **pnpm 11**; Yarn 1 is retired from the new stack |
| CSS | **Tailwind CSS 4** plus native CSS variables/design tokens |
| Accessible primitives | **Bits UI v2** |
| Starter components | **shadcn-svelte selectively**, as copied source only; it is not ED-Finder's visual authority |
| Icons | **Lucide Svelte** |
| Local/application state | **Svelte 5 runes/context**; no Zustand replacement library by default |
| Server/API state | **TanStack Svelte Query** |
| OpenAPI client | **Hey API + Fetch**, generating typed SDK/query helpers from FastAPI OpenAPI |
| Tables | **TanStack Svelte Table** |
| Large lists | **TanStack Svelte Virtual** |
| Charts | **LayerChart 2** |
| Component/unit tests | **Vitest 4.1 + Testing Library Svelte** initially |
| Browser/E2E authority | **Cypress** |
| Accessibility automation | **Cypress + axe** |
| Visual/browser regression | **Cypress screenshots/assertions** |
| Component workshop | **Storybook 10.5** |
| Lint | **ESLint 10 + official Svelte plugin** |
| Formatting | **Prettier 3** |
| Initial PWA posture | **No PWA/service worker** until a concrete product requirement justifies the cache/deployment complexity |

### Spatial platform

| Layer | Locked decision |
|---|---|
| Renderer target | **Babylon.js 9-class** |
| Package form | Modular **`@babylonjs/*`** packages; start with `@babylonjs/core` |
| Renderer ownership | Babylon owns spatial/GPU presentation only; it does not own application state, domain truth, persistence, ranking or planning |
| Backend preference | WebGPU where supported/proved, with WebGL2 fallback according to the existing Stage 27 renderer contract |
| Heavy client transforms | Native **Web Workers + transferable ArrayBuffers/typed arrays** only when profiling demonstrates a main-thread problem |
| Large-data transport | Normal JSON/OpenAPI by default; bounded binary/streaming endpoints only for measured bottlenecks |

The existing Stage 27 renderer-neutral `SpatialSceneContract`, contribution, command and event boundaries remain authoritative. The frontend-framework change does not permit Babylon types to leak into domain contracts.

### Backend and data

| Layer | Locked decision |
|---|---|
| Language/runtime | **CPython 3.14**, normal GIL build initially |
| Dependency/project manager | **uv + `pyproject.toml` + `uv.lock`** |
| API framework | **FastAPI** |
| Validation/contracts | **Pydantic 2** + FastAPI OpenAPI |
| API PostgreSQL driver | **asyncpg** |
| Importer/synchronous PostgreSQL driver | **Psycopg 3**; retire `psycopg2-binary` as importer code is ported |
| Database | Existing **PostgreSQL 18** V3 database; do not recreate or restore V2 wholesale |
| Schema migrations | Existing reviewed SQL manifest/checksum `schema_migrations` ledger |
| ORM | **None by default**; do not add SQLAlchemy merely as part of the reset |
| API server | **Uvicorn** behind the internal web/proxy boundary |
| OAuth | Existing FastAPI Frontier Authorization Code + PKCE/session/owner model; no auth-framework rewrite |

The application must expose exact build provenance (`build_sha`/version) from its immutable release. `unknown` is not an acceptable production release identity.

### Cache, pub/sub and background processing

| Layer | Locked decision |
|---|---|
| Cache/pub-sub service | **Valkey** for the new baseline |
| Valkey state | Non-authoritative, disposable/rebuildable cache/pub-sub/rate-limit state; canonical truth remains PostgreSQL |
| NATS | **Not in the baseline**; reintroduce only if a future requirement demonstrates a job/stream responsibility Valkey should not own |
| EDDN | **One dedicated EDDN worker service** |
| Generic job queue | None initially; introduce one only for a demonstrated multi-worker durable-queue requirement |

The current runtime still uses Redis until a reviewed migration. The existing full-spectrum `apps/eddn` listener and the simulation-only FastAPI lifespan EDDN consumer must not survive as two independent relay consumers in the target architecture. Fold the simulation/body-scan handling into one dedicated EDDN worker and remove long-lived ingest ownership from FastAPI request-service lifespan.

Valkey persistence is not required to recover canonical product data. Restart may discard caches, pub/sub state and rate-limit counters. Any future feature that would make cache data authoritative requires a new decision rather than silently enabling persistence.

### Web serving, containers and production orchestration

| Layer | Locked decision |
|---|---|
| Static web server | **nginx** |
| Public/application routing | Same-origin web + API; `/api/*`, exact `/openapi.json` and numeric `/s/{id64}` route to FastAPI, while all other application/static routes route to the SvelteKit build; no backend catch-all may steal SvelteKit routes |
| Container runtime | **Docker Engine** |
| Host orchestration | **Docker Compose v2**, through a new explicitly V3 production authority file; root legacy/local Compose is not production authority |
| Alternative orchestrators | No Kubernetes/Swarm/Traefik/Caddy migration as part of this rebuild |
| Production build behaviour | **No builds, dependency resolution or `git pull` on production** |
| Release artifacts | Immutable OCI web/backend images plus a release manifest containing exact Git SHA, image digests, migration-set/schema identity, schema-compatibility evidence and rollback eligibility |
| API/worker image | Prefer one versioned backend image with different commands/entrypoints for API and worker responsibilities where practical |
| Rollback | A previously accepted immutable application release manifest is eligible only when backward compatibility with the current database schema has been proved; otherwise fail closed pending an explicitly reviewed and rehearsed database rollback/recovery path |

Target request shape:

```text
Internet
   |
existing V3 public/TLS edge
   |
V3 web nginx
   |-------------------- static SvelteKit assets/routes
   |
   +---- /api/* ---- FastAPI
   +---- /openapi.json ---- FastAPI
   +---- /s/{id64} -------- FastAPI
                         |
                  PostgreSQL 18
                         |
                      Valkey

EDDN relay ---- dedicated EDDN worker ---- PostgreSQL 18 / Valkey pub-sub
```

These are the retained backend-owned non-application routes, not a broad FastAPI catch-all: exact `/openapi.json` serves FastAPI OpenAPI for CI and client generation, and numeric `/s/{id64}` serves the OpenGraph share stop page. SvelteKit retains every other application/static route. The exact host ports/network names are deployment details and must come from reviewed V3 topology evidence, not from V2 configuration guesses.

Application rollback must prefer expand/contract and backward-compatible migration discipline. Selecting an old application manifest is safe only when evidence proves that release remains compatible with the database's current migration set and schema. If compatibility is absent or unknown, promotion of the old application fails closed until an explicitly reviewed and rehearsed database rollback/recovery path exists. Incompatible or destructive migrations must never advertise one-click application-only rollback. This decision defines that gate; it does not invent the currently absent executable V3 database recovery procedure.

### Secrets and configuration

- Production Compose contains **no inline secret values**.
- Sensitive configuration is supplied through mounted secret files/Compose secrets with application `*_FILE` support where appropriate.
- Non-secret configuration may use environment variables.
- Frontier client secret, owner bootstrap/admin credential, database credentials, telemetry credentials and similar values are never frontend build inputs.
- Secrets are never printed in receipts, CI logs, PRs or source-controlled examples.
- A production deployment must identify its exact secret source and target services before OAuth or migration activation.

### Observability

Initial baseline:

- structured logs to stdout/stderr;
- existing Prometheus-style service/infrastructure metrics where applicable;
- GlitchTip/Sentry-compatible exception telemetry for backend and frontend;
- release/build identity attached to telemetry;
- no OpenTelemetry tracing in the initial baseline.

OpenTelemetry may be added later only when a real multi-service latency/debugging problem justifies it.

## Browser and test authority

ED-Finder has already paid the cost of discovering that Playwright was flaky for this repository. Generic ecosystem preference does not override repository evidence.

New baseline:

- **Cypress is the protected browser/E2E authority**;
- Chrome/Chromium-family and Firefox are the initial protected browser classes;
- Microsoft Edge may be exercised as the production Chromium-family browser;
- Safari/WebKit is best-effort/compatibility-target initially and is not a hidden Playwright requirement;
- Vitest/Testing Library owns fast component/unit tests;
- Cypress Svelte component testing may be reconsidered when its Svelte integration has proved stable for this repository.

Playwright is not active tooling. Its unique Review Lab, accessibility, visual, browser, and renderer-ordering responsibilities are replaced by Cypress in the issue #577 hard cut. Stage 26 artifacts and receipts may retain clearly historical Playwright wording as provenance, but no Playwright configuration, dependency, invocation, or runnable harness remains. Cypress is only the browser driver for Review Lab; the Python evaluator remains the acceptance brain and schema owner.

## Frontend/renderer ownership amendment

Where Stage 27A documents currently say **React owns app/domain orchestration**, the target-stack interpretation is now:

> **Svelte/SvelteKit owns app/domain orchestration, routing, panels, accessible DOM UI, keyboard and text. Babylon owns only the long-lived spatial renderer runtime.**

This is a frontend-framework authority amendment, not a change to the renderer-neutral scene contract and not authorization to implement Babylon in Stage 27A.

The same replacement applies to references that say React/DOM owns accessible UI: the durable contract is **Svelte/DOM** accessibility ownership. Renderer-neutral domain handlers, rather than React-specific handlers, decide whether runtime events are permitted to mutate application/domain state.

### Current executable foundation

The later governed PR #601 packet establishes the minimum executable baseline selected here: an isolated Svelte canvas host and Babylon 9 adapter using modular `@babylonjs/core` imports, WebGPU preference, explicit WebGL2 fallback, bounded renderer status, and deterministic diagnostic geometry. It is explicitly **non-product**. It introduces no application `worldScale`, Finder/Inspect behaviour, fresh map visual design, production wiring, or renderer cutover; those remain later reviewed work.

## Explicit retirements / negative decisions

Do not carry these into the new baseline by inertia:

- React / ReactDOM;
- `@react-three/fiber`;
- Three.js as the ED-Finder application renderer;
- Zustand;
- React Radix packages;
- Recharts;
- legacy monolithic `babylonjs` package;
- Yarn 1;
- Tailwind 3 configuration/plumbing;
- Playwright (equivalent Cypress coverage is required before this hard-cut branch merges);
- NATS without a new justified responsibility;
- duplicated EDDN consumers;
- API-served frontend bundle as the target deployment model;
- production source checkout as the application release artifact;
- PWA/service-worker caching without a product requirement;
- Biome while Svelte support remains experimental for our needs;
- SQLAlchemy/Alembic solely for fashion or migration-framework uniformity;
- Kubernetes or another orchestrator without a scale/availability problem that Compose cannot meet.

Deck.gl/Luma.gl are not automatically retained. Current use is renderer-bakeoff/reference material. A future Stage 27 requirement must establish a non-Babylon responsibility before either library enters the new application dependency graph.

## Migration and implementation order

The reset is deliberately serialized to avoid half a dozen simultaneous production cutovers.

1. **Accept this stack decision.** No feature implementation before the target is internally consistent.
2. **Establish immutable V3 release foundation.** Build/publish current FastAPI plus a minimal SvelteKit shell as immutable images; define exact release manifest, secrets, V3 production Compose/network/rollback, health and provenance.
3. **Prove backend runtime before feature porting.** Origin and public `/api/health` must be healthy; `/openapi.json` and current `/api/auth/*` routes must be present; exact build SHA must be reported.
4. **Prove migration/OAuth state through reviewed V3 paths.** Inspect migration state before applying anything; then configure Frontier secrets/callback, complete a real login and owner claim.
5. **Port Svelte application surfaces in bounded slices:** shell/auth/shared API context -> Finder -> Inspect/System Detail -> Planner -> evidence/review -> Admin/Ops.
6. **Introduce Babylon only through the existing Stage 27 authorization/bakeoff sequence.** The Svelte rebuild does not silently accelerate the renderer production cutover.
7. **Run V3 data-coverage audit** and repair only data/functions actually shown missing.
8. **Complete the React/R3F and Playwright hard replacement before merging its branch.** Preserve useful source/history as non-runnable evidence; do not preserve a parallel Playwright lane for gradual retirement. Redis/NATS retirement remains separately staged.

## Initial release-foundation acceptance

Before the new application can replace the stale Phase4C runtime, require at minimum:

- immutable web and backend image digests tied to one Git SHA;
- reproducible CI build from frozen pnpm/uv locks;
- dedicated reviewed V3 production Compose/runtime authority;
- no production build or source pull;
- exact host/target guard and release manifest recording migration-set/schema identity, compatibility evidence and rollback eligibility;
- PostgreSQL 18 retained in place, with no V2 wholesale restore;
- API reports exact `build_sha` and version;
- origin and public health both valid;
- same-origin routing sends `/api/*`, exact `/openapi.json` and numeric `/s/{id64}` to FastAPI while leaving every other application/static route with SvelteKit;
- valid FastAPI OpenAPI document at the backend-owned `/openapi.json` route;
- backend-owned numeric `/s/{id64}` OpenGraph stop page remains reachable without capturing other SvelteKit routes;
- anonymous session endpoint valid;
- all current Frontier OAuth routes present before attempting login;
- frontend static shell served through the same-origin application path;
- Cypress smoke for root, health, anonymous session and representative navigation;
- secret values absent from source, image metadata, Compose literals and logs;
- service restart/recreate limited to explicitly selected V3 application services;
- receipt records images/digests, routes, health, migration-set/schema identity, schema compatibility and only an eligible rollback target without exposing secrets;
- application-only rollback fails closed when backward schema compatibility is absent or unproved, and incompatible destructive migrations do not advertise one-click rollback.

## Revisit triggers

A locked technology may be reconsidered when one of these occurs:

- the selected project is abandoned, materially incompatible or security-blocked;
- measured production requirements exceed its documented capability;
- a required platform/browser cannot be supported;
- a simpler replacement removes substantial operational complexity with evidence;
- Stage 27 measurements invalidate a renderer/runtime assumption.

Do not reopen choices merely because another framework/library has a newer release.
