# Stage 19X — deep Grok product and architecture intake

## Purpose

Stage 19X records the deeper review of Grok suggestions as product, UI/UX, map, package, and architecture input.

Grok is useful as a brainstorming and adversarial review source. It is not an execution authority.

Nothing from the Grok bundle should be run directly, deployed directly, or merged as a broad patch bundle.

## Corrected interpretation

The strongest product direction from the deeper review is:

`ED-Finder should become a provenance-backed colonisation planning cockpit.`

That means the product should connect:

`source data -> source_runs/artifacts -> warehouse freshness -> map/planner -> exports/operator provenance`

## Accepted product lanes

| Lane | Verdict | Reason | Timing |
|---|---|---|---|
| Admin/operator cockpit | Accept | Source-runs, artifacts, freshness, failed imports, and bounded writes need visibility. | Near-term |
| Map as planning surface | Accept | The galaxy/system map should become the main visual planning surface. | Near/mid-term |
| Planner cockpit | Accept | CP curve, build sequencing, body slots, materials, economy impact, and exports are core product value. | Mid-term |
| Facility browser and recommender | Accept | Turns raw facility data into build decisions. | Mid-term |
| Ring/mining planning | Accept | Useful for resource and economy strategy. | Mid-term |
| Mission intelligence | Accept | Mission density can become a differentiator, but must be freshness-bound. | Mid-term |
| Exports/operator packs | Accept | The user needs shareable, auditable build packs. | Mid-term |
| Accessibility/mobile polish | Accept | Needed once cockpit workflows are usable. | Later but planned |

## Map architecture verdict

The current map is a custom React canvas map. That is still the correct short-term foundation.

Do not jump directly to PixiJS.

Map order of operations:

1. Refactor the current canvas map into projection, viewport, render layers, hit-test helpers, and overlays.
2. Add canvas LOD and batching.
3. Add performance profiling and E2E coverage.
4. Evaluate PixiJS only if canvas complexity or performance demands it.

## Package verdict

| Package or approach | Verdict | Why | Timing |
|---|---|---|---|
| Current Canvas | Keep | Already present and good enough for the next refactor. | Now |
| PixiJS | Evaluate later | Strong candidate if overlays and point counts outgrow canvas. | Later |
| deck.gl | Defer | Powerful, but too geo/WebGL oriented for ED galaxy coordinates right now. | Probably later or never |
| MapLibre or Leaflet | Avoid for map | Not a good fit for ED galactic coordinates. | Not planned |
| d3 | Utility only | Useful for scales/layout helpers, not main renderer. | Optional later |
| Recharts | Use | Already installed and good for CP curves/timelines. | Near-term |
| Zod | Add soon | Runtime validation at API/UI boundaries will reduce bad-data bugs. | Near-term |
| dnd-kit | Add later | Excellent for planner drag/drop, not map rendering. | Planner phase |
| TanStack Table | Consider | Useful for source-run/artifact/admin tables if current tables become painful. | Later |
| XState or reducer state machines | Consider | Useful if planner workflow state gets complex. | Later |

## dnd-kit lane

dnd-kit is accepted for planner/workflow UX, not for the galaxy map.

Good dnd-kit targets:

- build sequence planner;
- planetary slot assignment;
- facility priority queue;
- material or cargo delivery phases;
- export pack section ordering;
- alternative build plan comparison.

Rule: drag/drop should only be added after the planner has a real data model underneath it.

The goal is not movable cards. The goal is actions like:

`Drag a refinery hub earlier and immediately see CP, material, unlock, and economy impact.`

## UI/UX cockpit ideas accepted

- Admin dashboard for source-runs, artifacts, warehouse freshness, failed/running imports, review packets, approval allowlists, bounded writes, and canonical apply state.
- Planner cockpit with build sequence, CP curve, materials, unlocks, economy/security impact, and export status.
- Map overlays for source freshness, economy potential, mission density, ring/mining opportunities, facility coverage, and confidence/provenance.
- Facility browser with comparison and recommendation views.
- Mission intelligence dashboard with freshness-bound evidence and stale-data warnings.
- Export/operator pack builder for Markdown, JSON, CSV, and shareable snapshots.

## Testing implications

Accepted testing lanes:

- source-run/import/artifact integrity tests;
- FK compatibility tests and rollback rehearsals;
- map projection and hit-test unit tests;
- map E2E flows with selection, overlay toggles, and planner handoff;
- drag/drop planner tests once dnd-kit is introduced;
- export snapshot tests;
- visual/performance regression tests later.

## Rejected or deferred direct-use ideas

Do not directly use:

- broad Grok patch bundles;
- ready-to-deploy scripts;
- fake API endpoint examples;
- direct prototype TSX components;
- Discord OAuth/RBAC during Stage 19;
- renderer rewrites before map refactor;
- production DB or operator commands from Grok output.

## Roadmap impact

Stage 19 remains focused on safe warehouse/import foundations.

The deeper Grok intake shapes Stage 20 onward:

| Stage | Theme | Boundary |
|---|---|---|
| Stage 20A | Source-run/artifact/warehouse status API design | Docs or repo-only |
| Stage 20B | Admin/operator cockpit UI | Repo-only |
| Stage 20C | Map architecture refactor | Repo-only |
| Stage 20D | Canvas LOD and batching | Repo-only |
| Stage 20E | Planner data model | Repo-only |
| Stage 20F | CP curve and build sequence UI | Repo-only |
| Stage 20G | dnd-kit drag/drop build planner | Repo-only |
| Stage 20H | Export/operator pack builder | Repo-only |

## Safety rules

- Grok output is input, not implementation.
- Ideas must become scoped roadmap items or Codex PRs.
- New packages require a package justification and scoped PR.
- UI should not be built on fake data unless clearly marked as prototype-only.
- Production DB changes remain controlled, audited, and separately approved.
- Canonical apply remains separately approved only.

## Verdict

Stage 19X accepts the deeper Grok review as roadmap input for product, UI/UX, map architecture, package selection, planner UX, and testing strategy.

No DB writes, imports, migrations, scheduler/timer enablement, canonical writes, or canonical apply are approved by this document.

