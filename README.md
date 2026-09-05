# ED-Finder

ED-Finder is an Elite Dangerous exploration, system-finding, colony-planning,
evidence-review, and spatial-analysis project. V3 is rebuilding those journeys
as one spatial platform.

## Current authority

Start here, then follow only the authority needed for the question:

| Authority | Controls |
|---|---|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Current programme, execution order, and open decision gates |
| [`docs/development/v3-application-stack-decision.md`](docs/development/v3-application-stack-decision.md) | V3 application technology and ownership |
| [`docs/colonisation-redesign/spatial-platform-product-contract.md`](docs/colonisation-redesign/spatial-platform-product-contract.md) | Product journey, features, and truth semantics |
| [`docs/colonisation-redesign/spatial-platform-architecture-decision.md`](docs/colonisation-redesign/spatial-platform-architecture-decision.md) | Renderer-neutral spatial ownership and boundaries |
| [`docs/development/v3-browser-validation-lanes.md`](docs/development/v3-browser-validation-lanes.md) | Browser acceptance and Review Lab separation |
| [`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md) | Production, runtime, database, and recovery boundary |
| [`CLAUDE.md`](CLAUDE.md) | Agent and repository-working rules that point into this chain |

[`docs/development/v3-coordination-control-plane.md`](docs/development/v3-coordination-control-plane.md)
supports implementation coordination; it is not product or architecture
authority. Older stage documents, audit reports, receipts, and Git history are
rationale or evidence only. They never override the authorities above. See the
[`docs/archive/` policy](docs/archive/README.md).

## Current V3 baseline

- Production is `ed-finder-prod` at `nb79a3d.mevnode.com` on PostgreSQL 18.
  Hetzner/V2 is gone. Old V2 runtime, cron, database, deployment, recovery, and
  rollback receipts are historical evidence only.
- Three self-hosted Codex runners are hosted on Contabo. They are not
  production and are not an automatic live-checkpoint host. Any checkpoint
  destination requires a later explicit decision.
- [`apps/web/`](apps/web/) is the sole V3 browser target: Svelte 5, SvelteKit 2,
  TypeScript 6, Vite 8, Node 24, and pnpm 11.
- A fresh Babylon.js 9-class renderer is the V3 spatial target. Svelte owns
  routes, application/domain orchestration, panels, text, and accessible DOM;
  Babylon owns spatial presentation, picking, and camera mechanics only.
- [`frontend/`](frontend/) React/R3F/Three code and Stage 26 receipts are
  historical migration/reference and behaviour evidence. R3F won Stage 26; that fact
  does not make it current V3 architecture or production authority.
- PR #601 is the active integration lane. The current known exact head
  `12eebac48ca9286e0fd8c180cc5f552dc922d07e` contains the real
  Explore/Finder → fresh Babylon → canonical Inspect slice and the Review Lab
  rebase to `apps/web` + Babylon. Exact-head validation is still red and
  stabilizing, so this is not a green or complete checkpoint.
- The experimental Ollama/Octopus test residue has been removed from
  production. It is not V3 architecture.

## Product direction

The connected journey is:

`Explore → Inspect → Plan → Review / Export`

The spatial platform spans Galaxy and System views while preserving explicit
truth, bounded-result semantics, accessible equivalents, and selected-system
continuity. Colony Planner remains the detailed plan and persistence owner;
rendering must never silently change a plan, ranking, mechanic, or canonical
fact.

Search/spatial-index/grid/cluster design, PostgreSQL 18 derived-data bootstrap,
and the Ratings v3.4 versus archetype judgement model are active decisions, not
settled architecture. Finder's current local search calculates raw `x/y/z`
distance; it does not establish grid indexing as the V3 accelerator.

## Repository map

```text
apps/api/          FastAPI application and API composition
apps/eddn/         EDDN ingestion service
apps/importer/     Source import, enrichment, and build tooling
apps/web/          Sole V3 Svelte/SvelteKit browser target
frontend/          Historical React/R3F migration and behaviour evidence
docs/              Current authorities plus supporting/historical evidence
scripts/checks/    Repository validation and drift checks
scripts/operator/  Bounded operator helpers and repository tooling
sql/               Schema and migration history
tests/             Application, safety, and governance tests
```

## Local development

For the V3 web application:

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm check
pnpm lint
pnpm format:check
pnpm test
pnpm build
```

Use only local or disposable API/data targets. The generated client under
`apps/web/src/lib/api/generated/` comes from the authoritative FastAPI
`/openapi.json` contract. Same-origin route ownership is fixed:

| Route | Owner |
|---|---|
| `/api/*` | FastAPI |
| exact `/openapi.json` | FastAPI |
| numeric `/s/{id64}` | FastAPI share/metadata stop page |
| application routes, assets, and SPA fallback | SvelteKit |

Backend checks still use the repository-pinned Python 3.12 environment while
the reviewed V3 target is CPython 3.14 with `uv`. Follow [`CLAUDE.md`](CLAUDE.md)
and current CI for focused commands; never use production data or credentials
for ordinary development.

## Validation and operations

Product E2E/Visual Acceptance proves the real V3 user journey. Review Lab is a
separate lane using synthetic data and an isolated environment. Both exercise
`apps/web` + Babylon; one is not a substitute for the other.

Production and recovery work must begin at
[`docs/operations/infrastructure-status.md`](docs/operations/infrastructure-status.md)
and use an explicitly current, target-specific procedure. Root legacy Compose,
old receipts, retained dumps, and historical stage documents are not production
instructions. If no current procedure authorizes an action, stop.

## Project attribution

ED-Finder is an unofficial community project and is not endorsed by Frontier
Developments. Preserve [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
the applicable in-product legal notices.
