# ED-Finder V3 Roadmap

This is the operational programme authority: it says what is current, what
happens next, and which decisions remain open. It is not a changelog.

## Authority and current baseline

Normal work should need only this chain:

1. [`../README.md`](../README.md) — entry point and current baseline.
2. this roadmap — programme, order, and decision gates.
3. [`development/v3-application-stack-decision.md`](development/v3-application-stack-decision.md) — technology and application ownership.
4. [`colonisation-redesign/spatial-platform-product-contract.md`](colonisation-redesign/spatial-platform-product-contract.md) — product/features/truth.
5. [`colonisation-redesign/spatial-platform-architecture-decision.md`](colonisation-redesign/spatial-platform-architecture-decision.md) — renderer-neutral spatial ownership.
6. [`development/v3-browser-validation-lanes.md`](development/v3-browser-validation-lanes.md) — browser authority.
7. [`operations/infrastructure-status.md`](operations/infrastructure-status.md) — production/runtime boundary.

[`../CLAUDE.md`](../CLAUDE.md) applies repository and agent rules through this
chain. [`development/v3-coordination-control-plane.md`](development/v3-coordination-control-plane.md)
is supporting process guidance, not product authority.

### V3 infrastructure cutover boundary — 2026-09-02

Production is `ed-finder-prod` at `nb79a3d.mevnode.com`, using PostgreSQL 18.
Hetzner/V2 is decommissioned. All V2 runtime, cron, database, deployment, recovery, and
rollback receipts are historical V2 evidence unless a current V3 authority
explicitly revalidates a fact. The retired Windows/V2 release wrappers remain
non-authoritative. Contabo hosts three self-hosted Codex runners;
it is not production and is not an automatic checkpoint destination.

## Current V3 state

- [`apps/web/`](../apps/web/) is the sole V3 browser target, using
  Svelte/SvelteKit. Fresh Babylon is the V3 spatial renderer target.
- React/R3F/Three and the Stage 26 material remain historical migration,
  behaviour, accessibility, and bake-off evidence. R3F won Stage 26; it is not
  current V3 architecture or production authority.
- PR #601 is the active integration lane. Current known exact head
  `12eebac48ca9286e0fd8c180cc5f552dc922d07e` contains a real
  Explore/Finder → fresh Babylon → canonical Inspect product slice and the
  Review Lab rebase to `apps/web` + Babylon.
- Exact-head validation at that head is red and stabilizing. Do not call the
  integration checkpoint green, accepted, or complete until every required
  exact-head lane proves it.
- Product E2E/Visual Acceptance and Review Lab are separate. Both V3 map lanes
  exercise `apps/web` + Babylon; Review Lab varies synthetic data and its
  isolated environment, not the application architecture.
- The experimental Ollama/Octopus test residue has been removed from
  production and has no architectural standing.

## Product journey and spatial north star

The product journey is:

`Explore → Inspect → Plan → Review / Export`

The north star is an Elite-familiar Galaxy and System spatial workbench with
ED-Finder's own visual identity and explicit evidence discipline. It must work
from true Elite light-year coordinates across all 42 named regions, preserve a
continuous camera from wide through regional, local, and system semantic
scales, and keep highlighted/selected targets stable across level-of-detail
changes.

Spatial views must expose exact versus bounded/truncated counts, accessible DOM
equivalents, overlap disambiguation, search, fly-to, picking, and honest unknown
states. Finder supports Search From Here, Systems Within, and explicit
viewport/reference/region/radius inputs. Clusters are domain-derived
contributions, not renderer inference.

The same platform grows to Commander History/Journal, Routes, Powerplay,
Colonisation, planned CPE integration, and CRE Digital Twin views. System Map
uses stable `BodyRef` identity, distinguishes truth from schematic orbit
presentation, and preserves infrastructure uncertainty. Representation classes
are explicit. Babylon never owns mechanics, ranking, persistence, or planning;
Colony Planner remains the detailed plan/persistence owner.

## Current execution order

1. Stabilize PR #601 at its exact latest head without weakening either browser
   lane or turning an intermediate red head into a checkpoint claim.
2. Accept the Explore/Finder → Babylon → Inspect slice and Review Lab rebase
   only when Product E2E/Visual Acceptance and Review Lab independently pass.
3. Decide search/spatial-index/grid/cluster architecture and the PostgreSQL 18
   derived-data bootstrap contract before building the full derived-data path.
4. Decide the scoring/data model before that build: code still uses Ratings
   v3.4 in places while prior roadmap intent moved judgement toward archetypes.
   Record one explicit decision; do not resolve the conflict by documentation
   fiat or silent schema work.
5. Continue the renderer-neutral product journey in bounded slices, preserving
   truth/provenance, accessibility, selection continuity, and planning ownership.
6. Choose any live-checkpoint destination explicitly. Do not infer one from the
   location of build/review runners.

## Active decision gates

| Gate | Current truth | Decision required before expansion |
|---|---|---|
| PR #601 acceptance | Real product slice is present; exact-head validation is red/stabilizing | Required exact-head checks and reviews pass without collapsing the two browser lanes |
| Search acceleration | Finder local search currently uses raw `x/y/z` distance | Choose grid/spatial-index/query architecture, bounded semantics, and ownership |
| Clustering | Clusters are domain-derived; renderer clustering is not canonical | Define contribution, aggregation, invalidation, and explanation contracts |
| PG18 derived data | PostgreSQL 18 is production; derived-data bootstrap is not settled | Define rebuild sources, migrations, ordering, observability, and rollback/abort boundaries |
| Scoring/data | Ratings v3.4 remains in code; archetypes are prior judgement intent | Make and record the canonical scoring/data decision before full PG18 derived-data build |
| Checkpoint location | Contabo is runner infrastructure only | Select an explicit destination, trust boundary, retention, and recovery purpose |

Unknowns remain unknown. No old database receipt, runtime observation,
dependency, or stage label can close one of these gates.

## Deferred and later capabilities

- Commander History/Journal ingestion, analytics, timeline, expedition playback,
  and privacy-aware Galaxy/System contributions.
- Routes and Powerplay spatial workflows.
- Broader Colonisation surfaces, planned CPE integration, and CRE Digital Twin.
- Rich System Map infrastructure and body-level views after `BodyRef`, source,
  truth/schematic, and uncertainty contracts are ready.
- Cross-device plan sync, collaboration, and broad account expansion.
- Mission intelligence, ring/mining expansion, and automatic canonical apply.

Each remains subject to the product and architecture contracts and requires a
bounded reviewed slice. Deferred does not mean rejected, and a historical
prototype does not authorize implementation.

## Historical pointer

Stage 25 established the connected product-shell/planner journey. Stage 26
selected and cut over R3F/Three and produced useful browser, accessibility,
visual, performance, region, and rollback evidence. Stage 27A audits document
inheritance and data-readiness findings. All are supporting or historical
evidence only; they do not override this roadmap or restore V2 production
authority.

The historical minimum V2 restore-readiness baseline came from V2
backup/restore automation and rehearsal. Those V2 records do **not** constitute a V3 PostgreSQL 18 recovery runbook. The infrastructure authority remains
fail-closed where a current executable procedure is absent.

Use [`colonisation-redesign/README.md`](colonisation-redesign/README.md) for the
small current spatial index and [`archive/README.md`](archive/README.md) for the
historical-document policy. No files are physically retired by this authority
cleanup; a separate archive pass owns that work.

If any older roadmap, stage document, audit, receipt, or Git history disagrees
with this file about current order or authorization, this file wins.
