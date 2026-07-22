# Stage 26C Region-First Foundation Contract

## Status And Authorization

Stage 26C implements the selected Three.js/React Three Fiber foundation behind
an isolated development entry. It does not change the production route, wire a
feature hand-off, mutate planner state, or authorize map cutover.

The production-candidate renderer may live under `frontend/src/`, but the live
application entry must not import it during this stage. A separate Vite entry
is the only executable surface.

## Required Slice

The Stage 26C foundation must:

1. render the 42 named regions from ED-Finder's existing authoritative source,
   with the sentinel excluded and runtime-derived boundaries and interior label
   positions;
2. accept `MapSceneState` and emit typed `MapInteractionEvent` values without
   exposing Three.js objects to feature code;
3. use one orthographic camera whose state is expressed in light-years per
   pixel, with continuous pan, zoom, bearing, and pitch updates;
4. cap background-system rendering through a deterministic visibility/LOD
   selector while always retaining selected, highlighted, and cluster systems;
5. render arbitrary simultaneous comparison and cluster highlights, including
   cluster edges, radius or hull, labels, and preserved group context;
6. require an explicit choice when selectable systems overlap;
7. expose a bounded keyboard-accessible companion for selection, highlights,
   cluster members, overlap candidates, and visible layer state;
8. preserve one-time scene auto-fit semantics through the retained scene
   reducer rather than renderer-owned feature state; and
9. report context loss and restoration without claiming recovery until a
   renderer-backed interaction succeeds after restoration.

## Bounded Visibility Contract

The browser renderer must not receive an unbounded background draw list. The
selector returns:

- total in-view background count;
- returned background count;
- deterministic aggregate remainder count;
- truncation state; and
- all guaranteed system IDs, even when the background sample omitted them.

The isolated workbench may generate 100,000- and 500,000-system deterministic
fixtures, but it must keep the rendered background at or below 25,000 points.
This is frontend LOD evidence, not authorization for an unbounded backend
response.

## Interaction Boundary

Stage 26C completes the retained interaction union with selection, deselection,
overlap-choice, camera-change, layer-change, and context-state events. Navigation
events remain hand-off requests only. Stage 26D owns actual Finder, Compare,
Cluster Search, saved/evidence, System Detail, and planner wiring.

Selecting a cluster anchor or member must include its cluster anchor ID so the
host can preserve group context. Planner navigation must remain a typed event;
the renderer and workbench must not create or mutate a Build Plan.

## Verification

Required local evidence is:

- strict TypeScript and ESLint checks for the isolated entry and reusable
  foundation modules;
- unit tests for deterministic visibility caps, guaranteed-system retention,
  highlight/cluster extraction, and overlap grouping;
- Playwright at 1280x720 and 1440x900 covering 42 regions, bounded 500k LOD,
  camera updates, explicit overlap choice, arbitrary highlights/clusters,
  keyboard operation, and context restoration followed by a successful pick;
- a separate production build proving the live application still compiles; and
- repository-required checks and an exact-head review.

## Deferred Gates

Stage 26C does not close production performance, GPU timing, accessibility,
visual-regression, browser-matrix, or region-redistribution gates. Stage 26D
owns feature integration. Stage 26E owns parity, final performance and visual
evidence, deliberate cutover, and removal of superseded map code.

## Implemented Evidence

The isolated implementation is retained under `frontend/map-foundation/`, with
the reusable renderer and deterministic visibility logic under
`frontend/src/features/map-foundation/`. The live frontend entry and route do
not import either path.

Local verification on 2026-07-22 established:

- 42 named region labels and runtime-derived boundary segments from
  `apps/importer/src/data/region_map.json`;
- a 500,000-system fixture reduced to 25,000 background points plus five
  guaranteed systems, with 474,995 represented by aggregate-remainder metadata
  at the reviewed default camera;
- six focused visibility/cluster/overlap unit tests;
- passing Playwright journeys at 1280x720 and 1440x900, including a successful
  renderer-backed interaction after WebGL context restoration; and
- a [1440x900 visual review](../../artifacts/map-foundation/stage-26c/region-first-1440x900.png)
  retained in the Stage 26C evidence directory.

The isolated minified build measured approximately 309 kB gzip on this local
toolchain. This is not a production bundle budget or cutover result. GPU timing,
the broader browser matrix, final accessibility evidence, and the legal gate
remain unresolved.
