# ED-Finder

ED-Finder is an Elite Dangerous system-finding, inspection, colony-planning,
evidence, and spatial-analysis project.

## Current V3 baseline

ED-Finder production is `ed-finder-prod` at `nb79a3d.mevnode.com`, on the V3
replacement infrastructure with PostgreSQL 18. Hetzner/V2 is decommissioned;
its host, runtime, cron, database, backup, and rollback records are history.

The target browser application is [`apps/web/`](apps/web/): Svelte 5,
SvelteKit 2, TypeScript, and a fresh Babylon renderer behind renderer-neutral
contracts. The React/R3F/Three application under [`frontend/`](frontend/) is
retained migration and behavioural evidence, not the V3 target or an authority
for current production. Stage 26's R3F selection remains an accurate historical
decision.

PR #601's Explore/Finder → fresh Babylon results → canonical Inspect product
slice and Review Lab rebase onto `apps/web` + Babylon merged to `main` at exact
merge commit `6d574a2908ebda146a2c271f8fb46a9e272ad12e`.

The separate Contabo/live checkpoint remains a rehearsal boundary outside
production.
The V3 production application promotion authority is defined independently and is
now `authorized`: its inventory, schema, network, secret-file, receipt-store,
Docker-context, and unchanged-edge cutover facts have been reviewed and pinned,
and it has accepted the first governed `bootstrap` promotion (2026-09-10);
ROADMAP's programme status additionally records the 2026-09-16 identity release
deployed via the governed path. Being authorized is not blanket permission to
promote — deploys run only through the governed application-promotion workflow.

## Current authority

Read this small set in order. Archived and stage-labelled documents preserve
evidence but never override it.

1. [`README.md`](README.md) — entry point and current baseline.
2. [`docs/ROADMAP.md`](docs/ROADMAP.md) — current programme, order, and open
   decisions.
3. [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md)
   — technology choices and application ownership.
4. [`docs/colonisation-redesign/spatial-platform-product-contract.md`](docs/colonisation-redesign/spatial-platform-product-contract.md)
   — product journey, spatial behaviour, and truth rules.
5. [`docs/colonisation-redesign/spatial-platform-architecture-decision.md`](docs/colonisation-redesign/spatial-platform-architecture-decision.md)
   — renderer-neutral boundaries and ownership.
6. [`docs/development/v3-browser-validation-lanes.md`](docs/development/v3-browser-validation-lanes.md)
   — Product E2E/Visual Acceptance and Review Lab authority.
7. [`docs/development/v3-search-spatial-derived-data-decision.md`](docs/development/v3-search-spatial-derived-data-decision.md)
   — merged search/spatial and derived-generation architecture.
8. [`docs/development/ratings-v4-freeze/README.md`](docs/development/ratings-v4-freeze/README.md)
   — frozen Ratings V4.0 mechanics, scores and validation evidence.
9. [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
   — production, runtime, checkpoint, and recovery boundary.

[`CLAUDE.md`](CLAUDE.md) is the repository and agent contract that points to
this chain. It is not a competing product roadmap. [`CHANGES.md`](CHANGES.md)
is a historical changelog. [`docs/archive/README.md`](docs/archive/README.md)
explains how historical records must be interpreted.

## Product and ownership summary

The current journey is **Explore/Finder → Inspect → Plan → Review/Export**.
The spatial north star is one continuous Galaxy context at true Elite
light-year coordinates, with deliberate transitions to System Map and later
Digital Twin contributions.

- Svelte/SvelteKit owns routes, application/domain orchestration, panels, and
  the accessible parallel DOM.
- Babylon owns spatial/GPU presentation, picking, projection, and camera
  implementation only. Babylon types do not cross domain contracts.
- Finder owns queries and ranking, including Finder/search-from-here.
- Domain owners contribute clusters; the renderer does not invent them.
- Colony Planner/CPE owns planning mechanics and persistence. A map never
  silently mutates a plan.
- CRE owns mechanics, research interpretation, and Digital Twin truth.
- Commander History/Journal, Routes, Powerplay, Colonisation, and planned CPE
  overlays contribute through explicit renderer-neutral boundaries.

PR #645 establishes the V3 search/spatial and derived-generation architecture;
PR #646 freezes Ratings V4.0. Production integration now follows canonical
source recovery, bounded derived builds, validation and atomic publication.
Archetype judgement and Finder ranking remain separate later layers.

## Repository layout

```text
apps/api/                     FastAPI application
apps/eddn/                    EDDN ingestion code
apps/importer/                Import and derived-data tooling
apps/web/                     V3 Svelte/SvelteKit + Babylon application lane
frontend/                     Historical React/R3F migration evidence
docs/                         Current authority, support, and archives
sql/                          Schema and migration history
tests/                        Application and repository-governance tests
```

## Safe local validation

Use local or disposable services only. Never point ordinary development or
test commands at production.

For the V3 web application, use Node.js 24 LTS and pnpm 11.25.0. The root
`.nvmrc` and `.node-version` select the locked Node major for local version
managers; `apps/web/package.json` requires `>=24 <25`. Verify `node --version`
and `pnpm --version` before running the checks. See the
[Node runtime upgrade plan](docs/development/node-runtime-upgrade-plan.md)
for the pin inventory and the separate owner-gated production procedure.

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm check
pnpm lint
pnpm format:check
pnpm test
pnpm build
```

The retained React tree is historical migration evidence only. It is not built,
tested, or required as a validation gate.

Before a repository change, run the strict state resolver and the focused tests
for the touched surface:

```bash
make state-check
```

## Operations boundary

The root `docker-compose.yml` and retired V2 procedures do not describe V3
production. Production or recovery work requires an explicitly current V3
runbook and target. Contabo hosts exactly three self-hosted Codex runners; it is
not production. Its selected first live-checkpoint path remains isolated and
fail-closed on the recorded missing runtime, data and route authorities.

The repository currently has no executable PostgreSQL 18 recovery runbook.
Stop rather than adapting V2 instructions or inventing host paths, credentials,
backup targets, or restore commands.

The separate V3 production application promotion authority is documented in
[`docs/operations/v3-production-application-release.md`](docs/operations/v3-production-application-release.md).
Its committed target is `authorized` (inventory and schema/edge facts reviewed
and pinned) and has accepted the first governed `bootstrap` promotion (the later
2026-09-16 identity release is recorded in ROADMAP's programme status), but
promotions still run only through the governed workflow; the root Compose and
Contabo checkpoint do not
become production authority.
