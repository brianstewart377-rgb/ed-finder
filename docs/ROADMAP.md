# ED-Finder V3 Roadmap

This is the authority for current programme order and unresolved decisions. It
does not duplicate detailed product, architecture, browser, or infrastructure
contracts.

## Authority and baseline

Start at the [root authority index](../README.md), then use:

- [V3 application stack decision](development/v3-application-stack-decision.md)
- [spatial product contract](colonisation-redesign/spatial-platform-product-contract.md)
- [spatial architecture decision](colonisation-redesign/spatial-platform-architecture-decision.md)
- [V3 search, spatial and derived-data decision](development/v3-search-spatial-derived-data-decision.md)
- [Ratings V4.0 freeze](development/ratings-v4-freeze/README.md)
- [browser validation lanes](development/v3-browser-validation-lanes.md)
- [infrastructure status](operations/infrastructure-status.md)

Archived documents, completed Stage 17–26 contracts, Stage 27A audits, Git
history, and old Superpowers plans are evidence only. They cannot authorize work
or override this set.

## Current V3 state

- **Production:** `ed-finder-prod` / `nb79a3d.mevnode.com` is the production
  environment and PostgreSQL 18 is the database generation. Hetzner/V2 is gone.
  Old host, runtime, cron, database, backup, and rollback receipts are history.
- **Browser target:** [`apps/web/`](../apps/web/) is the sole destination for
  new browser application work: Svelte/SvelteKit with a fresh Babylon renderer.
  React/R3F/Three is historical migration, behaviour, and parity evidence only;
  it is not the V3 target or current production authority.
- **Merged application baseline:** PR #601's Explore/Finder → fresh Babylon
  results → canonical Inspect slice and Review Lab rebase to `apps/web` +
  Babylon merged at exact `main` commit
  `6d574a2908ebda146a2c271f8fb46a9e272ad12e`.
- **Historical renderer decision:** the equal Stage 26 bakeoff selected R3F and
  the subsequent Stage 26 work shipped. That result remains valuable history;
  it does not constrain the post-V2 V3 renderer target.
- **Infrastructure separation:** Contabo is the host for exactly three
  self-hosted Codex runners and the selected first live-checkpoint target. It
  is not production. The checkpoint is limited to a persistent, isolated and
  bounded two-service application namespace; current missing runtime, data and
  route authority keeps mutation stopped.
- **Inference:** Ollama was an Octopus experiment and has been removed from
  production. It is not part of the architecture.
- **Production application authority:** the separate app-only V3 production
  promotion path is defined and its committed target is still stopped, but the
  reviewed read-only inventory of 2026-09-10 proved the application network,
  the local Docker context, exact loopback ownership of ports 58080/58081, host
  capacity and the live schema/ledger identity. Five blockers remain: the api
  secret file, the receipt store, the reviewed schema identity file, the
  unchanged-edge cutover topology and an exact CPython 3.14 mutation runtime.
  The reviewed unchanged-edge cutover authority is now published as
  `edge_route_authority`, and the committed edge configuration forwards the
  public application surface to the single active origin rather than the staging
  port, so the topology blocker is host state only: the deployed edge still
  targets `127.0.0.1:58081` and the web slot is still staged there pending the
  governed bootstrap cutover.
  Production already serves the 2026-09-09 in-place release; that promotion is
  recorded as a description of what runs, not as governed acceptance. The root
  Compose and Contabo checkpoint remain non-authoritative for production.
- **Designated production secret and receipt paths (not yet provisioned):** the
  api env snapshot is to live at `/etc/ed-finder/v3-production/api.env` (owner
  uid `0`, mode `0600`) and the durable promotion receipt store at
  `/var/lib/ed-finder/v3-production/receipts` (owner uid `0`, mode `0700`).
  Neither path exists on the host yet, and no deployment root can be derived
  from the running containers: they carry no Compose project directory, and the
  only labels present belong to unrelated stacks. Both are free parameters that
  the target authority must pin, and
  [`scripts/operator/v3_production_deploy.py`](../scripts/operator/v3_production_deploy.py)
  verifies them with `secure_path` rather than supplying a default.
  The read-only inventory records stat-only existence/kind/owner-uid/mode
  evidence for both designated paths without reading their contents, so the next
  reviewed run supplies the facts those two authority fields need.

## Product journey and spatial north star

The connected journey is **Explore/Finder → Inspect → Plan → Review/Export**.
The spatial platform keeps one continuous Galaxy context using true Elite
light-year coordinates and supports wide, regional, local, and deliberate
System semantic scales. The detailed requirements—including all 42 named
regions, bounded/truncated results, selection and camera continuity, accessible
parallel DOM, overlap disambiguation, Finder hand-offs, System truth, and
representation classes—live in the
[spatial product contract](colonisation-redesign/spatial-platform-product-contract.md).

Finder owns queries and ranking. Domain owners contribute clusters and other
overlays. The renderer owns no mechanics, scoring, persistence, or planning.
Colony Planner/CPE remains the detailed plan owner; CRE remains the mechanics,
evidence-interpretation, and Digital Twin owner.

## Execution order

1. **Keep checkpoint and production authorities separate.** The Contabo
   checkpoint remains non-production. Use only the production authority's
   read-only inventory to resolve its explicit blockers; do not deploy while
   its target is stopped.
2. **Harden the V3 release.** Continue CPython 3.14/`uv`, immutable release
   provenance, same-origin route, health, migration compatibility, and rollback
   work without treating an application release as database recovery.
3. **Promote only after reviewed production preflight.** A candidate must be an
   authenticated immutable release compatible with the freshly verified live
   ledger. Preserve PostgreSQL 18, Redis, NATS, the public-auth/TLS edge,
   Octopus and unrelated containers; schema deltas stop for a separate
   production migration authority.
4. **Preserve the checkpoint boundary.** Keep Contabo non-production and its
   persistent app-only namespace isolated from the three runner services.
5. **Integrate the merged V4 contract.** PR #645 establishes search/spatial and
   derived-generation architecture; PR #646 freezes Ratings V4.0. Recover the
   verified canonical importer, preserve source provenance and unknowns, then
   implement the production derived-generation schema and bounded builder.
6. **Validate and publish V4.** Prove complete generation coverage, scores,
   explanations, resource use and rollback before exposing a stable API through
   the reviewed production release controls. Archetypes and Finder ranking
   follow this raw-economy layer and do not alter its frozen coefficients.
7. **Establish V3 database evidence.** Add reviewed PostgreSQL 18 maintenance,
   backup, restore, and PITR evidence/procedures before claiming operational
   readiness. Historical V2 receipts cannot fill this gap.

## Active decision gates

| Gate | Decision required before implementation |
|---|---|
| Search and spatial data | Decided by merged PR #645: exact coordinates, cube/GiST, versioned search/map projections and independent cluster publication. |
| Scoring and judgement | Ratings V4.0 is frozen by PR #646. Seven independent raw scores; archetype judgement and Finder ranking remain later layers. |
| Derived-data bootstrap | Implement recovered canonical inputs, bounded generation builds, complete validation and atomic publication/rollback through reviewed production controls. |
| Live checkpoint | Supply the still-missing non-production database/config, container runtime, origin/edge and receipt authorities before first mutation. |
| Production app promotion authority | Provision the two designated non-secret paths (`/etc/ed-finder/v3-production/api.env`, `/var/lib/ed-finder/v3-production/receipts`) at the recorded owner uid and mode, author the api env snapshot, and capture stat-only existence/owner/mode evidence before the target can be authorized. An exact CPython 3.14 mutation runtime is still absent from the host, and the live loopback bindings must match the reviewed single-active-origin cutover model, whose authority and edge configuration are now published but not yet applied to the host. |
| V3 DB maintenance/recovery | Supply current PG18 population/invariant evidence and an executable reviewed backup/restore/PITR procedure. Until then, recovery remains fail-closed. |

The merged V3 search/spatial decision and Ratings V4.0 freeze are architecture
and scoring authority. Their merge does not establish production build or
publication evidence; the integration must produce those receipts.

## Deferred and later capabilities

These remain part of the product direction, sequenced after the current browser
and decision-gate work:

- Commander History and its non-map Journal, spatial queries, expeditions, and
  historical playback;
- first-class System Map with `BodyRef` identity and honest schematic orbits;
- Powerplay, Routes, and deeper Colonisation overlays;
- planned CPE contributions and CRE Digital Twin contributions;
- broader account sync, collaboration, and other product expansion.

Their truth, ownership, accessibility, and hand-off requirements are defined in
the [spatial product contract](colonisation-redesign/spatial-platform-product-contract.md),
not duplicated here.

## Historical evidence

- [Archive policy and index](archive/README.md)
- [Colonisation/spatial current index](colonisation-redesign/README.md)
- Stage 27A capability, readiness, and inheritance files remain audit/evidence
  inputs, not roadmap or authorization gates.
- Stage 25 and Stage 26 documents preserve the completed product/map chronology.
  The archived bakeoff record says R3F won Stage 26. The V3 technology
  authority selects a fresh Babylon target without rewriting that fact.
- [`CHANGES.md`](../CHANGES.md) preserves dated change history and cannot be
  used as current production or programme authority.

## Roadmap rule

If a supporting, historical, or archived document disagrees with this roadmap
about programme order, this roadmap wins. Infrastructure operations still
require the separate current
[infrastructure authority](operations/infrastructure-status.md).
