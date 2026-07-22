# Stage 26D Typed Feature Hand-off Contract

## Status And Authorization

Stage 26D connects ED-Finder's existing Finder, Compare, saved-system, evidence,
System Detail, Cluster Search, and Planner data shapes to the Stage 26C typed
scene and interaction boundary. The integration remains behind the isolated
map-foundation entry. It does not replace the production map route, mutate a
Build Plan, change backend schemas, or authorize cutover.

## Inbound Boundary

`applyFeatureHandoff` accepts the existing frontend feature types and returns a
new `MapSceneState`, accepted system IDs, and explicitly omitted system IDs.
The adapter preserves camera, origin, and layer state through the retained
`MapReturnWorkflow` reducer.

The supported inputs are:

- Finder `SystemResult` rows with bounded-response metadata and optional
  selected-system context;
- Compare `SystemResult` snapshots and the explicit left/right pair;
- device-local `PinnedEntry` and server-backed `WatchlistEntry` saved-system
  snapshots without conflating their persistence models;
- evidence summaries paired with a coordinate-bearing system snapshot;
- the existing `SystemDetail` response;
- `ClusterResult` plus an explicit coordinate-bearing lookup for slot members;
  and
- read-only Planner highlights, layers, clusters, systems, and opaque workflow
  context.

All coordinate-bearing production shapes normalize to renderer-independent
`SystemRecord` values. Y is retained by the source feature but is intentionally
not part of the current galactic X/Z scene contract.

## Missing Coordinate Rule

Evidence summaries and cluster slot matches identify systems but do not carry
renderable member coordinates. Stage 26D never invents coordinates. Their
callers must provide an existing coordinate-bearing system snapshot. Missing or
invalid coordinates are returned in `omittedSystemIds` and mark the hand-off's
bounded response as truncated.

The Cluster Search anchor may use its existing `anchor_coords`; every other
member requires the explicit lookup. The rendered cluster contains only
resolved members and retains its anchor/member roles, edges, radius, label, and
group context.

## Outbound Boundary

`resolveMapInteraction` translates renderer events into host commands for Map,
Finder, System Detail, Compare, saved systems, evidence, Cluster Search, and
Planner. Selection updates the selected-system context and carries the cluster
anchor ID when present. Camera and layer events update scene state without a
navigation command.

Planner navigation resolves only to `openPlanner(systemId64)` when a system is
already selected. Otherwise it returns `plannerSelectionRequired`. Neither the
renderer nor the adapter creates, loads, or changes a plan.

## Isolated Workbench Evidence

The Stage 26C workbench now identifies itself as Stage 26D and exposes a
keyboard-operable feature-return selector. It exercises all seven inbound
feature families against the real adapter and reports the retained return
workflow, the last outbound host command, and coordinate omissions.

The two required Chromium journeys at 1280x720 and 1440x900 verify that:

- Finder, Compare, saved systems, evidence, System Detail, Cluster Search, and
  Planner each cross the typed return boundary;
- camera bearing, pitch, centre, and zoom survive every feature round trip;
- the fixture has no unreported coordinate omissions; and
- a selected-system Planner request becomes `openPlanner` while producing no
  plan mutation.

Focused unit coverage verifies each production input shape, evidence and
cluster omission behavior, selected-system and cluster-anchor context, every
outbound route command, and the planner selection guard.

## Deferred Gates

The live `#map` route still uses the existing map implementation. Stage 26E
owns deliberate route cutover, production parity, final accessibility,
performance and GPU evidence, browser and visual-regression coverage, legal
closure, and removal of superseded map code.
