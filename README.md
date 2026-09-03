# ED Finder

ED Finder is the player-facing Elite Dangerous exploration and colonisation-planning application in the ED Finder three-repository architecture.

The repository is now on the **V3** product line. The retired Hetzner/V2 server build is not a supported deployment target and this README intentionally does not preserve its machine-specific setup instructions.

## Current programme

The authoritative programme state lives in [`docs/ROADMAP.md`](docs/ROADMAP.md).

At the current baseline:

- **Stage 27 — One Spatial Platform** is the active programme.
- **Stage 27A** is contract/audit work only; later runtime slices require their own authorization.
- The shipped Galaxy map baseline remains the Stage 26E **React Three Fiber / Three.js** implementation until a later renderer bakeoff earns a cutover.
- **Colony Planner** remains the canonical detailed planning workspace and persistence owner.
- Player-facing scoring uses **Development Score** / archetype language; the current database implementation remains on **Ratings v3.4** while the architecture continues to move away from legacy universal-score concepts.

Do not infer authorization for a later roadmap slice from code or historical design documents. `docs/ROADMAP.md` is the source of truth for "what next?".

## Architecture

### Frontend

- React 19 + TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- Zustand
- React Three Fiber / Three.js for the current production Galaxy map
- Generated API wire types from FastAPI OpenAPI

The shipping frontend is [`frontend/`](frontend/). Historical vanilla-JS frontend code is not part of the current product.

### Backend and data

- Python 3.12
- FastAPI
- PostgreSQL
- Redis
- EDDN ingestion
- Spansh/import and post-import data builders

Primary service code lives under [`apps/`](apps/):

- `apps/api/` — HTTP API
- `apps/eddn/` — live EDDN ingestion
- `apps/importer/` — import, grid, ratings and derived-data builders

Database schema and migrations live under [`sql/`](sql/).

### Three-repository boundary

The standing architecture is:

- **ED Finder** — player-facing product and integration surface
- **CRE (`colonisation-research-engine`)** — research truth producer
- **CPE (`colony-planning-engine`)** — plan-construction owner

CRE/CPE integration is staged and governed by the roadmap. Do not silently duplicate ownership across repositories just because a capability is convenient to add here.

## Local development

Windows is the primary local development target. Use the checked-in PowerShell wrappers rather than translating old Unix/production examples by hand.

### Fresh setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/bootstrap-windows.ps1 -StartServices -RunDoctor
```

### Check the environment

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight -Strict
```

### Start the app

Frontend plus local API/services:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices
```

API only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices
```

The canonical Windows setup guide is [`docs/development/windows-dev-environment.md`](docs/development/windows-dev-environment.md).

## Verification

The repository deliberately keeps local and CI verification close together. Useful entry points include:

```powershell
make state-check
make test-unit
```

and the stricter Windows preflight:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight -Strict
```

For browser/review-environment work, follow the dedicated development docs rather than inventing one-off service layouts.

## Repository map

```text
apps/                 FastAPI, EDDN and importer services
frontend/             React/TypeScript player-facing application
sql/                  schema and migration history
scripts/dev/          canonical local-development entry points
scripts/operator/     bounded operator/admin tooling; read its contracts before use
docs/                 roadmap, architecture, product, development and operations docs
tests/                unit, integration, contract and repository-hygiene tests
.github/               CI, review and repository automation
```

## Documentation hierarchy

Start here:

1. [`docs/ROADMAP.md`](docs/ROADMAP.md) — authoritative current programme and authorization boundary.
2. [`CLAUDE.md`](CLAUDE.md) — repository operating context, engineering rules and canonical commands.
3. [`docs/development/windows-dev-environment.md`](docs/development/windows-dev-environment.md) — Windows local setup.
4. [`docs/development/pull-request-acceptance-policy.md`](docs/development/pull-request-acceptance-policy.md) — exact-head CI/review/merge policy.
5. [`CHANGES.md`](CHANGES.md) — development change history.

Historical stage documents and archived operational material are evidence, not automatically current instructions. Check their status against the roadmap and current contracts before acting on them.

## Production and retired V2 material

The old Hetzner-hosted V2 environment has been decommissioned. References to its host layout, IP/DNS arrangement, `/opt/ed-finder` checkout, or Hetzner-specific operator procedures are legacy material and must not be treated as the current production contract.

Production changes must follow the repository's current deployment, operator, migration and acceptance contracts on the exact code being shipped. Do not resurrect old V2 instructions as a shortcut.

## Change history

The previous root README had grown into a machine-specific Hetzner setup/import manual mixed with bug history and implementation changelogs. That information is no longer the root project contract. Relevant historical reasoning belongs in [`CHANGES.md`](CHANGES.md), stage/operation documents, commit history and archived evidence.
