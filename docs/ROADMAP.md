# ED-Finder V3 Roadmap

This is the authority for current programme order and unresolved decisions. It
does not duplicate detailed product, architecture, browser, or infrastructure
contracts.

## Authority and baseline

Start at the [root authority index](../README.md), then use:

- [V3 application stack decision](development/v3-application-stack-decision.md)
- [spatial product contract](colonisation-redesign/spatial-platform-product-contract.md)
- [spatial architecture decision](colonisation-redesign/spatial-platform-architecture-decision.md)
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
- **Active integration lane:** PR #601 is the single active V3 application
  integration lane. At known head
  `190d26446a2487596299cbb6b497ffa5201fee0b`, it already contains the real
  Explore/Finder → fresh Babylon results → canonical Inspect slice. Because
  this documentation branch is based on `main`, that is active-PR state, not a
  claim that the implementation has merged here.
- **Historical renderer decision:** the equal Stage 26 bakeoff selected R3F and
  the subsequent Stage 26 work shipped. That result remains valuable history;
  it does not constrain the post-V2 V3 renderer target.
- **Infrastructure separation:** Contabo is the host for exactly three
  self-hosted Codex runners. It is not production. A live-checkpoint destination
  remains a deployment decision; a prior read-only capacity audit established
  only that a small isolated, bounded checkpoint might be feasible.
- **Inference:** Ollama was an Octopus experiment and has been removed from
  production. It is not part of the architecture.

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

1. **Stabilize the active browser slice.** Complete review of PR #601's
   Explore/Finder → Babylon results → Inspect journey, including typed
   boundaries, accessibility, bounded data, Product E2E/Visual Acceptance, and
   the separate Review Lab lane.
2. **Harden the V3 release.** Continue CPython 3.14/`uv`, immutable release
   provenance, same-origin route, health, migration compatibility, and rollback
   work without treating an application release as database recovery.
3. **Merge, then choose checkpoint policy.** Accept the exact reviewed PR head
   before any checkpoint/promotion decision. The destination and isolation
   limits are deployment choices; Contabo is not a default.
4. **Resolve search and data architecture in order.** Establish Search product
   and performance requirements, then choose the spatial index/grid/cluster
   design, then define the PostgreSQL 18 derived-data bootstrap.
5. **Resolve judgement dependencies.** Reconcile current Ratings v3.4 uses with
   the roadmap's intended archetype judgement layer before a full ratings,
   grid, cluster, or derived-data build is prescribed.
6. **Establish V3 database evidence.** Add reviewed PostgreSQL 18 maintenance,
   backup, restore, and PITR evidence/procedures before claiming operational
   readiness. Historical V2 receipts cannot fill this gap.

## Active decision gates

| Gate | Decision required before implementation |
|---|---|
| Search and spatial data | Search requirements → spatial index/grid/cluster design → PG18 derived-data bootstrap. Current normal Finder uses raw `x/y/z` bounding and distance and does not establish `grid_cell_id` as a first-class accelerator. |
| Scoring and judgement | Decide how Ratings v3.4 code/data dependencies relate to the intended archetype judgement layer. Do not trigger a full ratings/archetype rebuild from this roadmap. |
| Derived-data bootstrap | Define sources, ordering, versioning, bounded resource use, rebuildability, verification, and rollback only after the preceding two gates. |
| Live checkpoint | Choose destination, resource limits, isolation, data posture, lifecycle, and acceptance. Contabo runner hosting is not architectural authorization. |
| V3 DB maintenance/recovery | Supply current PG18 population/invariant evidence and an executable reviewed backup/restore/PITR procedure. Until then, recovery remains fail-closed. |

No final Search/Grid/Cluster authority document exists yet. Active audits feed
that future decision; they do not pre-authorize its conclusion.

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
