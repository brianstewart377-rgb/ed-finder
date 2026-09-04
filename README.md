# ED-Finder

ED-Finder is an Elite Dangerous exploration, system-finding, colony-planning, and spatial-analysis project.

## Current state

`ed-finder.app` is served from the V3 replacement infrastructure. The current production boundary uses PostgreSQL 18, the current backup/PITR design, Frontier identity, and the replacement-host operator workflows.

The complete product interface is being brought onto the current infrastructure in staged work governed by the repository roadmap.

## Canonical sources of truth

Use these in this order when deciding what is current:

1. [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) — current production and recovery boundary.
2. [`docs/ROADMAP.md`](docs/ROADMAP.md) — current programme stage and authorized next work.
3. [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) — locked target stack for new V3 application implementation.
4. [`CLAUDE.md`](CLAUDE.md) — repository engineering/agent constraints and validation expectations.
5. [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) — repo/local/production command boundaries.
6. Current code and tests on reviewed GitHub branches and PRs.

Do not infer authorization from old Git history, archived artifacts, installed dependencies, or removed operational procedures.

## Programme direction

The repository's current programme authority is [`docs/ROADMAP.md`](docs/ROADMAP.md).

- **Stage 27 — One Spatial Platform** is current.
- The roadmap controls when renderer implementation and production cutover are authorized.
- The intended spatial direction is a modern **Babylon 9-class** workbench.
- Colony Planner remains the detailed planning workspace and persistence owner; renderer work must not silently mutate plans.

Read the roadmap before starting implementation work.

The locked technology target for new V3 application implementation is defined by the [`V3 application stack decision`](docs/development/v3-application-stack-decision.md). That technology lock does not authorize Stage 27B, Babylon runtime work, or a production cutover.

## Infrastructure boundary

The current environment is intentionally built as a clean V3 platform.

Current rules:

- Production uses **PostgreSQL 18**.
- Do not attach or copy an older PostgreSQL physical data directory into PostgreSQL 18.
- Public/reconstructable galaxy data should be reimported or rebuilt through the current data path.
- Redis/cache state is disposable and rebuildable.
- NATS/JetStream transport state is not canonical domain truth.
- Production/recovery commands must come from current V3 runbooks that explicitly identify their target and safety boundary.
- GitHub is the application and infrastructure source authority.

### Legacy migration vault

A validated custom-format PostgreSQL dump is retained offsite solely as a selective migration source for genuinely irreplaceable/private/manual/history data.

| Field | Value |
|---|---|
| Filename | `edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Recorded offsite sync | `2026-08-23T05:32:41Z` |

The dump is not the operating database. Extract only explicitly justified data through reviewed migration tooling.

## Repository layout

```text
ed-finder/
├── apps/
│   ├── api/                 # FastAPI service and API composition
│   ├── eddn/                # EDDN ingestion
│   └── importer/            # Source import/enrichment/build tooling
├── frontend/                # React + TypeScript + Vite application
├── docs/                    # Product, architecture, research and operations docs
├── scripts/                 # Development, validation, migration and operator tooling
├── sql/                     # Schema/migration history
├── tests/                   # Backend, contract and integration tests
├── .github/workflows/       # CI, review and current operator automation
├── CLAUDE.md                # Engineering/agent contract
├── CHANGES.md               # Current development change log
└── README.md                # This entrypoint
```

Prefer the checked-out tree and current roadmap over old setup diagrams or Git history.

## Frontend

The checked-in frontend under [`frontend/`](frontend/) is still a React/TypeScript application built with Vite and remains the migration/reference and current-validation reality. The locked target for new V3 application implementation is Svelte 5/SvelteKit 2/TypeScript 6 on Node 24 with pnpm 11; the reviewed migration slices have not landed yet.

The package declares Yarn 1.22.22. Common validation commands are:

```bash
cd frontend
yarn install --frozen-lockfile
yarn typecheck
yarn test
yarn build
```

Additional focused map, planner, operator, Playwright, Storybook, and accessibility scripts are defined in [`frontend/package.json`](frontend/package.json).

## Backend and data work

Backend/service code lives primarily under [`apps/`](apps/) with SQL/migration history under [`sql/`](sql/).

The repository uses real PostgreSQL/Redis integration paths for relevant tests and deliberately separates disposable/local environments from production. Follow current preflight helpers and CI rather than pointing local tools at production.

For broad backend validation, use the repo-local Python environment and the current test/CI instructions in [`CLAUDE.md`](CLAUDE.md).

The checked-in backend validation path remains on Python 3.12. New V3 backend implementation targets CPython 3.14 with uv under the stack decision as reviewed migration slices land.

## Development workflow

`main` is protected. Normal changes go through a branch and PR with the required backend, integration, frontend, E2E, Review Lab, parity, and security checks.

Before changing code:

1. read [`docs/ROADMAP.md`](docs/ROADMAP.md);
2. verify the requested work is authorized by the current stage;
3. follow the [`V3 application stack decision`](docs/development/v3-application-stack-decision.md) for new V3 application implementation;
4. check [`CLAUDE.md`](CLAUDE.md) for repository-specific constraints;
5. keep local/test data isolated from production;
6. run the focused checks for the touched surface plus the required protected checks.

For UI/renderer work, preserve the repository's visual, accessibility, browser, bounded-data, and performance evidence requirements.

## Production and operator work

Read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
- [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md)
- [`scripts/operator/README.md`](scripts/operator/README.md)

Production actions must use current V3 procedures. Do not adapt commands from old Git history or archived artifacts to the current host.

## Project attribution

ED-Finder is an unofficial community project. Retain the repository's existing Frontier/community attribution and third-party notices when redistributing or changing relevant assets/data. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the current product/legal notices in the application.
