# ED-Finder

ED-Finder is an Elite Dangerous exploration, system-finding, colony-planning, and spatial-analysis project.

> **Current infrastructure status — 2 September 2026**
>
> The former Hetzner V2 production host has been decommissioned and is no longer an ED-Finder operator target. `ed-finder.app` is now served from the V3 replacement infrastructure. The replacement backend, PostgreSQL 18 data plane, backup path, and Frontier identity foundation are online while the full V3 product interface is brought into service.
>
> Do not use retained Hetzner deployment/operator instructions as current production procedures. Start with [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md).

## Current product state

ED-Finder is in the V2 -> V3 transition.

The public domain currently presents the V3 transition/status surface while the full application experience is migrated onto the replacement infrastructure. The previous full application and its Stage 26 map remain valuable source, migration, regression, and rollback references; they are not authority to recreate the retired Hetzner deployment.

The repository's current programme authority is [`docs/ROADMAP.md`](docs/ROADMAP.md):

- **Stage 27 — One Spatial Platform** is current.
- The current authorized Stage 27 slice is the contract/audit sequence described by the roadmap.
- Stage 26's R3F/Three.js work is the last completed full-map baseline and remains historical/rollback evidence.
- The intended next-generation direction is a modern **Babylon 9-class** spatial workbench, but the roadmap controls when runtime implementation or cutover is authorized.
- Colony Planner remains the detailed planning workspace/persistence owner; renderer work must not silently mutate plans.

Do not infer authorization from old branches, archived runbooks, installed dependencies, or historical production state. Read the roadmap first.

## Canonical sources of truth

Use these in this order when deciding what is current:

1. [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) — current production/recovery boundary.
2. [`docs/ROADMAP.md`](docs/ROADMAP.md) — current programme stage and authorized next work.
3. [`CLAUDE.md`](CLAUDE.md) — repository engineering/agent constraints and validation expectations.
4. [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md) — repo/local/V3-production/retired-V2 command boundaries.
5. Current code and tests on reviewed GitHub branches/PRs.

Historical Stage 17/18/19/25/26 documents remain evidence of what actually happened. A historical document can be factually correct without being a current runbook.

## V3 infrastructure boundary

The replacement environment is intentionally not a lift-and-shift of the old server.

Current rules:

- V3 uses a **fresh PostgreSQL 18** environment.
- Do **not** attach or copy the former PostgreSQL 16 physical data directory to PostgreSQL 18.
- Public/reconstructable galaxy data should be reimported or rebuilt through the V3 data path.
- Redis/cache state is disposable and rebuildable.
- NATS/JetStream transport state is not canonical domain truth.
- Production/recovery commands must come from current V3 runbooks that explicitly identify their target and safety boundary.
- GitHub is the application/infrastructure source authority; a retired server checkout is not.

### Legacy V2 migration vault

The validated V2 PostgreSQL custom-format dump was synchronized offsite before the Hetzner host was retired and is retained only as a selective legacy migration/recovery source.

| Field | Value |
|---|---|
| Former on-host path | `/data/backups/postgres/edfinder_20260823T021001Z.dump` |
| Size | `75,931,356,521` bytes |
| SHA-256 | `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1` |
| Recorded offsite sync | `2026-08-23T05:32:41Z` |

The dump is a **legacy migration vault**, not the V3 operating database. Extract only explicitly justified irreplaceable/private/manual/history data through reviewed migration tooling.

## Repository layout

The repository still contains the mature V2 application, migration-era tooling, current product work, and historical evidence needed to build V3 safely.

```text
ed-finder/
├── apps/
│   ├── api/                 # FastAPI service and API composition
│   ├── eddn/                # EDDN ingestion
│   └── importer/            # Source import/enrichment/build tooling
├── frontend/                # React + TypeScript + Vite application
├── docs/
│   ├── operations/          # Current/retired operator and infrastructure docs
│   └── ...                  # Product, architecture, research and historical evidence
├── scripts/                 # Development, validation, migration and operator tooling
├── sql/                     # Schema/migration history
├── tests/                   # Backend, contract and integration tests
├── .github/workflows/       # CI, review and guarded operator automation
├── CLAUDE.md                # Engineering/agent contract
├── CHANGES.md               # V3-era development change log
└── README.md                # This current entrypoint
```

The detailed structure changes over time. Prefer the checked-out tree and current roadmap over old setup diagrams.

## Frontend

The checked-in frontend is under [`frontend/`](frontend/). It is a React/TypeScript application built with Vite and uses the repository's typed API contract.

The package declares Yarn 1.22.22. Common validation commands are:

```bash
cd frontend
yarn install --frozen-lockfile
yarn typecheck
yarn test
yarn build
```

Additional focused map, planner, operator, Playwright, Storybook, and accessibility scripts are defined in [`frontend/package.json`](frontend/package.json).

The public V3 transition page should not be confused with the complete checked-in product UI: full interface migration onto the replacement infrastructure is still in progress.

## Backend and data work

Backend/service code lives primarily under [`apps/`](apps/) with SQL/migration history under [`sql/`](sql/).

The repository uses real PostgreSQL/Redis integration paths for relevant tests and deliberately separates disposable/local environments from production. Follow current preflight helpers and CI rather than pointing local tools at production.

For broad backend validation, use the repo-local Python environment and the current test/CI instructions in [`CLAUDE.md`](CLAUDE.md). Do not resurrect legacy production credentials or old Hetzner containers to make a test pass.

## Development workflow

`main` is protected. Normal changes should go through a branch and PR with the required backend, integration, frontend, E2E, Review Lab, parity, and security checks.

Before changing code:

1. read [`docs/ROADMAP.md`](docs/ROADMAP.md);
2. verify the requested work is authorized by the current stage;
3. check [`CLAUDE.md`](CLAUDE.md) for repository-specific constraints;
4. keep local/test data isolated from production;
5. run the focused checks for the touched surface plus the required protected checks.

For UI/renderer work, preserve the repository's visual, accessibility, browser, bounded-data, and performance evidence requirements.

## Production and operator work

Do not begin production work from a generic script name or an old command block.

Read:

- [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
- [`docs/operations/operator-command-contexts.md`](docs/operations/operator-command-contexts.md)
- [`scripts/operator/README.md`](scripts/operator/README.md)

A command that says **Hetzner**, expects hostname `ed-finder`, targets the retired V2 IP, or assumes the former host's `/opt/ed-finder`/`/var/lib/ed-finder` surfaces is historical unless an explicit current V3 document says otherwise.

Do not repoint old Hetzner scripts at the replacement host by changing a hostname, IP, or environment variable. V3 operations need their own reviewed contract.

## Historical V2 documentation

The old root README was a detailed Hetzner/PostgreSQL-16 setup and import guide. It is intentionally no longer the repository entrypoint because it described infrastructure that has been retired.

For forensic/history purposes, the pre-decommission version remains available immutably in Git history:

- [V2-era root README at the final pre-decommission `main` commit](https://github.com/brianstewart377-rgb/ed-finder/blob/1dcc6531f61c2ac6ac6f1cc774f53cdee760b1fd/README.md)
- [V2-era development changelog through 31 August 2026](https://github.com/brianstewart377-rgb/ed-finder/blob/1dcc6531f61c2ac6ac6f1cc774f53cdee760b1fd/CHANGES.md)

Do not rewrite historical Stage receipts merely to remove the word Hetzner; where an operation really happened there, that remains part of the record.

## Project attribution

ED-Finder is an unofficial community project. Retain the repository's existing Frontier/community attribution and third-party notices when redistributing or changing relevant assets/data. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the current product/legal notices in the application.
