# ED-Finder

ED-Finder is an Elite Dangerous exploration, system-finding, colony-planning, evidence-review, and spatial-analysis project.

> **V3 status — 4 September 2026**
>
> The infrastructure cutover is complete and the application rebuild has begun. The V3 implementation lane lives under [`apps/web/`](apps/web/) and starts with a static SvelteKit foundation. It is **not** a production cutover and it does not yet reproduce the complete React product. The existing application under [`frontend/`](frontend/) remains the behavioural, accessibility, browser, and parity reference until equivalent accepted coverage exists.

## Read this first

The repository deliberately separates **what exists**, **what is authorised next**, and **what may be operated in production**. Use these sources in order:

| Question | Authority |
|---|---|
| What is the current production, database, backup, and recovery boundary? | [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) |
| Which programme stage and implementation slice is authorised? | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| Which technologies and ownership boundaries are locked for the V3 application? | [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) |
| What rules apply to engineering agents and repository changes? | [`CLAUDE.md`](CLAUDE.md) |
| Which commands belong in the repo, a local environment, or production? | [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) |
| What must be true before a pull request may merge? | [`docs/development/pull-request-acceptance-policy.md`](docs/development/pull-request-acceptance-policy.md) |
| What are the current API ownership and generated-client contracts? | [`docs/api-contracts.md`](docs/api-contracts.md) |

Old Git history, archived stage evidence, retired runbooks, installed dependencies, and deleted workflows are evidence only. They do not authorise implementation or production actions.

## What ED-Finder is for

The complete product reference currently covers a connected workflow:

1. **Explore and find** systems using system, body, economy, distance, topology, and regional criteria.
2. **Inspect** a selected system, its bodies, evidence, infrastructure, and buildability context.
3. **Plan** colony projects and whole-system layouts without allowing visualisation code to become the owner of planning truth.
4. **Review and compare** saved systems, observations, provenance, simulations, and exportable planning evidence.
5. **Operate and diagnose** bounded owner/operator surfaces without exposing production credentials or turning a browser client into an operations console.
6. **Visualise spatial context** through the Stage 27 renderer-neutral scene and interaction contracts.

That product scope is the migration/parity target. The presence of a route, component, dependency, or historical test does not prove that a capability has already moved to the V3 application.

## Current V3 baseline

### Infrastructure

- The replacement V3 environment is the current production infrastructure boundary.
- PostgreSQL **18** is the production database generation.
- GitHub is the application and infrastructure source authority.
- Production and recovery actions must come from current V3 procedures that identify their target and safety boundary explicitly.
- Retired Hetzner/V2 deployment, hosted-review, and database procedures must not be reconstructed from history.
- The current repository operator surface is intentionally narrow; a status, source-contract recovery, or bounded repair helper is not implicit authority to deploy, migrate, or restore a database.

### Application

- [`apps/web/`](apps/web/) is the new V3 browser-application lane.
- It uses the locked Svelte 5 / SvelteKit 2 / TypeScript 6 / Vite 8 / Node 24 / pnpm 11 baseline.
- Its initial foundation proves a static application shell, route ownership, typed FastAPI client generation, query-state wiring, unit checks, and Cypress smoke coverage.
- It does not yet port Finder, Inspect, Colony Planner, Review, Admin/Ops, or the spatial renderer.
- [`frontend/`](frontend/) remains the React 19 / Vite 8 migration reference and continues to carry protected validation until deliberate retirement criteria are met.

The locked target for new V3 application implementation is Svelte 5/SvelteKit 2/TypeScript 6. The checked-in frontend under [`frontend/`](frontend/) remains a React/TypeScript migration/reference and current-validation lane until equivalent accepted coverage exists.

### Programme

- **Stage 27 — One Spatial Platform** is current.
- The V3 stack lock does not itself authorise a Babylon runtime, renderer cutover, production deployment, database mutation, or a later Stage 27 slice.
- Svelte/SvelteKit owns application routing, panels, accessible DOM UI, and app/domain orchestration in the target architecture.
- Babylon is the intended Stage 27 spatial/GPU renderer and owns spatial presentation only.
- Colony Planner remains the detailed planning and persistence owner; renderer events must not silently mutate plans or canonical evidence.

## Architecture at a glance

| Concern | Current repository baseline | Locked direction / boundary |
|---|---|---|
| V3 web application | `apps/web/` static SvelteKit foundation | Svelte 5, SvelteKit 2, TypeScript 6, Tailwind 4, Bits UI, Lucide Svelte |
| Product/parity reference | `frontend/` React 19 + Vite application | Retain until equivalent V3 behaviour and evidence are accepted; do not build new architecture into it by inertia |
| API | FastAPI under `apps/api/` | FastAPI + Pydantic 2 + OpenAPI; exact release provenance required |
| Generated clients | Existing React OpenAPI types plus the V3 Hey API client | Both generated from the same authoritative FastAPI `/openapi.json` while both lanes exist |
| Database | PostgreSQL 18 | Retain the V3 database; never attach or wholesale-restore a V2 physical data directory |
| Cache/pub-sub | Current runtime still contains Redis-era state | Valkey is the locked new baseline; cache state remains non-canonical and disposable |
| Messaging | Existing runtime/history may contain NATS | NATS is not part of the new baseline without a newly justified durable-stream responsibility |
| EDDN | Existing ingestion surfaces | Converge on one dedicated EDDN worker rather than duplicate long-lived consumers |
| Spatial renderer | React/R3F/Three.js remains parity and rollback evidence | Babylon.js 9-class, introduced only through the Stage 27 contract and bake-off sequence |
| Browser tests | Cypress is the protected authority for Chromium-family and Firefox coverage | Historical Stage 26 receipts remain immutable evidence; WebKit is explicitly retired from the runnable harness |
| Delivery | V3 release foundation is being established | Immutable OCI images and an exact release manifest; no production build, dependency resolution, or `git pull` |
| Production orchestration | Current V3 authority is documented outside the root legacy Compose file | A reviewed, explicitly V3 Compose/runtime authority; root legacy Compose is not production authority |

## Request and route ownership

The target application is same-origin, but ownership is intentionally split:

| Route | Owner |
|---|---|
| `/api/*` | FastAPI |
| exact `/openapi.json` | FastAPI |
| numeric `/s/{id64}` | FastAPI OpenGraph/share stop page |
| application pages, static assets, and SPA fallback | Static SvelteKit application |

Do not add a broad backend catch-all that steals SvelteKit routes. Do not add a frontend route that captures the backend-owned paths above.

## Repository layout

```text
ed-finder/
├── apps/
│   ├── api/                 # FastAPI service and API composition
│   ├── eddn/                # EDDN ingestion service code
│   ├── importer/            # Source import, enrichment, and build tooling
│   ├── maintenance/         # Legacy/self-host Compose maintenance sidecar; not V3 backup authority
│   └── web/                 # New V3 SvelteKit application lane
├── frontend/                # Retained React migration/parity reference application
├── docs/
│   ├── colonisation-redesign/ # Stage contracts, spatial authority, and historical evidence
│   ├── development/         # Architecture, engineering, testing, and acceptance docs
│   └── operations/          # Current and explicitly retired operational material
├── scripts/
│   ├── checks/              # Repository validation and drift checks
│   └── operator/            # Narrow current operator helpers plus repository tooling
├── sql/                     # Schema and migration history
├── tests/                   # Backend, integration, safety, and repository contract tests
├── artifacts/               # Retained design/performance/evidence artifacts
├── .github/workflows/       # CI, Review Lab, security, and current operator automation
├── docker-compose.yml       # Retained legacy/self-host stack; not V3 production authority
├── CLAUDE.md                # Engineering and agent contract
├── CHANGES.md               # V3-era development change log
└── README.md                # Current repository entrypoint
```

The tree contains both current implementation and deliberate historical/reference material. Read the governing document before deciding that an old-looking file should be executed, ported, or deleted.

## Working on the V3 web application

### Requirements

- Node.js **24**
- pnpm **11.25.0**
- a local/disposable API and data environment for integration and generated-client work

The package and lockfile under `apps/web/` are authoritative for exact JavaScript dependencies.

### Install and validate

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm check
pnpm lint
pnpm format:check
pnpm test
pnpm build
```

Run the Cypress foundation suite only with the expected local API and preview environment available:

```bash
cd apps/web
pnpm test:e2e
```

### Generated API client

`apps/web/src/lib/api/generated/` is generated by Hey API from the authoritative FastAPI OpenAPI document. Generation deliberately requires an explicit input:

```bash
cd apps/web
OPENAPI_INPUT=http://127.0.0.1:8000/openapi.json pnpm generate:api
```

Use only a local/disposable or otherwise explicitly authorised OpenAPI source. The repository-wide drift helper regenerates both frontend clients from the same local API and fails closed if either checked-in result changes:

```bash
bash scripts/checks/openapi-drift.sh
```

That helper refuses production-looking database targets; do not bypass the guard.

## Working on the retained React reference

The React application remains live migration evidence, so changes that affect parity or shared contracts may still require its checks.

```bash
cd frontend
yarn install --frozen-lockfile
yarn typecheck
yarn test
yarn build
```

The package declares Yarn 1.22.22. Focused map, planner, operator, Cypress, Storybook, accessibility, and evidence scripts are defined in [`frontend/package.json`](frontend/package.json).

Do not remove the React application, R3F baseline, or preserved Stage 26 receipts merely because the V3 foundation exists. The runnable Playwright toolchain has been retired after its current coverage moved to Cypress; historical evidence remains unchanged.

## Backend, database, and importer work

Backend and worker code lives primarily under [`apps/`](apps/); SQL and migration history lives under [`sql/`](sql/).

The checked-in backend validation path remains on Python 3.12. New V3 backend implementation targets CPython 3.14 with uv as reviewed migration slices land. Do not claim that migration has completed before the repository proves it.

Rules for backend/data work:

- use disposable local/test PostgreSQL and Redis-compatible services;
- use parameterised SQL and bounded inputs;
- follow [`docs/development/bulk-database-write-safety.md`](docs/development/bulk-database-write-safety.md) for bulk writes;
- preserve the reviewed SQL manifest/checksum migration ledger;
- do not read or mutate production data from an ordinary coding task;
- regenerate both checked-in API clients when an OpenAPI response/request contract changes;
- keep API, importer, EDDN, and maintenance responsibilities explicit rather than allowing one process to become an accidental scheduler.

Use the focused test instructions in [`CLAUDE.md`](CLAUDE.md) and the current CI workflows for the surface being changed.

## Local and review environments

[`docker-compose.review.yml`](docker-compose.review.yml) is the disposable Review Lab service/data contract. It is not production and must remain isolated from production credentials, URLs, and data.

The root [`docker-compose.yml`](docker-compose.yml) is retained because legacy/self-host, importer, CI, monitoring, and rehearsal paths still depend on it. It does **not** describe the V3 production topology or the V3 PostgreSQL 18 backup/PITR design. Do not use it to infer current production containers, database generation, frontend serving, or recovery commands.

When a local command needs secrets or database access, verify the target first. A local helper being executable is not evidence that it is authorised for V3 production.

## Testing and acceptance

`main` is protected. Normal changes use a branch and pull request and must satisfy the exact latest-head acceptance policy.

The protected system includes backend unit/integration tests, script and migration contracts, canonical safety tests, OpenAPI drift, frontend builds, browser E2E, built-image parity, Review Lab, security scanning, and reviewer disposition requirements. The exact required checks are defined by branch protection and current workflows rather than by a copied list in an old document.

Key principles:

- **Cypress is the V3 browser/E2E authority.**
- Cypress supplies Review Lab, accessibility, visual, Chromium-family, and Firefox browser coverage. WebKit is explicitly outside the protected runnable harness.
- Do not remove a test before its behaviour is reproduced or explicitly retired by the governing contract.
- Pure domain tests are valuable parity anchors and should move with framework-neutral code.
- User-visible changes require appropriate visual and accessibility evidence.
- Green CI is necessary but not sufficient; substantive reviewer findings must be resolved or explicitly dispositioned for the exact latest PR head.

## Data classification and migration

Treat data according to whether it can be rebuilt:

| Data class | V3 posture |
|---|---|
| Public galaxy/source data | Reimport or rebuild through current importer/data paths |
| Derived search indexes, caches, Redis/Valkey state | Rebuild; not canonical truth |
| NATS/JetStream transport state | Do not treat as canonical domain truth |
| Private/manual/history data that cannot be reconstructed | Selectively extract through reviewed migration tooling from the retained dump |
| PostgreSQL physical directories or wholesale V2 database state | Never attach/copy into PostgreSQL 18 |

### Retained legacy migration vault

A validated PostgreSQL custom-format dump is retained offsite solely as a selective source for genuinely irreplaceable/private/manual/history data:

| Field | Value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Recorded offsite sync | `2026-08-23T05:32:41Z` |

The dump is not the operating database and is not a general disaster-recovery shortcut. Any extraction requires an explicit inventory, reviewed migration path, target verification, and validation of the selected records.

## Production and recovery boundary

Before any production or recovery action, read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
- [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md)
- [`scripts/operator/README.md`](scripts/operator/README.md)

Fail closed when the current repository does not provide an authorised procedure. Never adapt a V2/Hetzner command, local Compose restore helper, archived incident note, or deleted release wrapper to the V3 host.

The following are not interchangeable:

- source recovery versus database recovery;
- status inspection versus deployment;
- a bounded container repair versus broad host mutation;
- a retained migration dump versus a production backup/PITR procedure;
- a clean Git checkout versus an accepted immutable release.

## Hetzner/V2 decommission boundary

The current tree intentionally preserves a small amount of historical evidence and inert tombstones while removing the old execution path.

- Deleted V2 release/SSH wrappers, hosted-review deployment files, and the Hetzner operator workflow must remain absent.
- `scripts/deploy_main.sh` is an inert retirement tombstone and must not regain a bypass.
- Retired operations documents may retain historical identifiers only when clearly marked non-executable.
- Root legacy Compose and local restore/rehearsal helpers are separate from the V3 runtime and must never be promoted by inference.
- Historical Stage 18/19/26 artifacts remain evidence; “old wording exists” is not by itself a reason to destroy provenance.

The goal is not “zero mentions of Hetzner”. The goal is **zero ambiguous authority and zero live V2 path into V3 production**.

## Change workflow

Before implementation:

1. fetch the current target branch and confirm the exact base SHA;
2. read the current roadmap and the authority document for the touched surface;
3. keep unrelated local changes out of the branch;
4. write or update the regression/contract test that protects the intended behaviour;
5. run focused checks, then the applicable full validation;
6. open or update a pull request and let all required checks/reviewers evaluate the exact latest head;
7. do not weaken a safety boundary, route owner, secret boundary, or test merely to obtain a green result.

For a change to an existing PR, use compare-and-swap/lease semantics and ensure the new head receives fresh CI and review.

## Security and secrets

Never commit or print passwords, credential-bearing DSNs, API tokens, OAuth client secrets, SSH/private keys, recovery codes, production environment files, or secret-bearing URLs.

Production secrets are not frontend build inputs. Keep secret values out of source, generated artifacts, image metadata, Compose literals, receipts, CI logs, and PR discussion. Preserve pinned host verification and do not replace it with runtime `ssh-keyscan` convenience.

Report suspected vulnerabilities privately rather than opening a public issue containing exploit or credential detail.

## Project attribution

ED-Finder is an unofficial community project and is not endorsed by Frontier Developments.

Retain the repository's Frontier/community attribution and third-party notices when redistributing or changing relevant assets or data. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the current legal/product notices in the application.
