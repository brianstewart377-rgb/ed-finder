# Stage 26A Next-Generation Map Foundation Contract

## Status

Stage 26A is the active authorization and contract checkpoint for replacing the
current galaxy-map frontend.

This checkpoint is documentation only. It authorizes an artifact-backed
research run and an isolated renderer bake-off. It does not select a renderer,
change a production route, add a database write lane, or authorize planner-map
fusion.

## Product Decision

ED-Finder needs a useful desktop galaxy map rather than another incremental
repair of the current canvas implementation.

The replacement remains a secondary `Explore` surface. The Colony Cockpit
remains the canonical planning workspace. Map interactions may select, compare,
and hand systems into existing workflows, but they must not mutate a Build Plan,
run Preview, promote evidence, or invent mechanics truth.

The current frontend map implementation is not an architectural baseline for
the replacement. It may remain live until cutover, but its renderer,
orchestration, camera model, and interaction model must not constrain the new
design. Verified backend data, API contracts, query ownership, error handling,
and other independently useful assets may be reused after review.

## Non-Negotiable Requirements

1. Render all 42 named in-game galaxy regions with correct names, recognizable
   boundaries, and correct galactic placement. Region index 0 remains an
   unmapped sentinel and is not a forty-third named region.
2. Use one continuous camera with a top-down default and optional tilt/rotation.
   A mode change must not abruptly replace the scene or lose user context.
3. Accept a typed scene descriptor and return typed interaction events. Feature
   code must not reach into renderer internals.
4. Highlight arbitrary sets of systems, including two-system comparisons and
   three-or-more-system cluster results, even when a highlighted system is
   absent from an aggregated background level of detail.
5. Represent cluster anchors, member IDs, member roles, edges, radius or hull,
   and labels. Selecting an anchor must not discard its member context.
6. Preserve bidirectional selected-system context between Map, Finder, System
   Detail, Compare, saved/evidence views, and explicit planner hand-off.
7. Disambiguate overlapping selectable systems. Never choose an arbitrary
   system silently.
8. Auto-fit a new scene at most once. Manual camera movement must survive later
   data, selection, and layer updates until the scene revision changes.
9. Give every bounded data response explicit `count`, `truncated`, and
   continuation or aggregate-remainder semantics. A bare `LIMIT` is invalid.
10. Provide a bounded contextual keyboard-accessible companion view for the
    selected systems, active overlays, search results, and overlap candidates.
11. Treat GPU timing as unknown unless measured with a GPU timer extension or a
    captured system trace. JavaScript callback duration is not GPU duration.
12. Target desktop browsers only. Required viewports are 1280x720 and 1440x900.
    Mobile, touch gestures, and phone-width map layouts are out of scope.
13. Support independently toggleable, data-driven overlay layers in the
    scene descriptor, including at minimum: live activity pulse (recent
    ingest events), freshness/age heat (colonisation freshness policy),
    cluster constellations (anchors, member edges, radius/hull), and plan
    routes (expansion-plan paths with explicit planner hand-off).
    Per-system animation state must be derivable from descriptor data
    attributes, not hand-placed. Applying a streamed scene update must
    preserve camera and selection (extending requirement 8) and must not
    produce visible frame hitching.

## Scene Boundary

The artifact-backed research run must produce a compilable TypeScript boundary
equivalent in responsibility to:

- `MapSceneDescriptor`: revision, one-time fit intent, camera intent and state,
  origin/return state, systems, clusters, highlights, routes, annotations, and
  layer visibility;
- `MapSystemEntry`: id64, name, coordinates, region, source, score where
  relevant, and primary/secondary/context role;
- `MapClusterDescriptor`: anchor, members, member roles, edges, radius/hull,
  economy context, and labels;
- `MapInteractionResult`: selection, deselection, overlap choice, navigation,
  camera change, and layer change events, and extensible contextual-action
  events carrying a target system or named region (for example, originating a
  Finder search from a map location), so feature stages can add map-initiated
  workflows without renderer changes. Named regions are addressable
  interaction targets, not only rendered geometry.
- `MapRendererAdapter`: renderer-independent mount, update, resize, context-loss
  recovery, measurement, and disposal behavior.

Names may change during the research run, but these responsibilities and their
separation may not disappear.

As recorded owner priority for the first Stage 26D wiring wave (not
authorized by this contract, and binding only on boundary design):
search-from-here contextual actions, a live radius indicator
bidirectionally synced with the Finder radius input including pre-query
scope tinting, hover synchronization between result surfaces and map
systems, and region-scoped search. The Finder retains sole ownership of
query semantics; the map acts as parameter input and result display
through this boundary.

## Required Integration Scenarios

The shared bake-off harness must execute the same scenarios against every
renderer candidate:

1. Three-system cluster with anchor, two members, edges, radius/hull, labels,
   and preserved group context after selection.
2. Two-system comparison fitted together and individually selectable.
3. Finder results with selection reflected both in the map and the originating
   result surface.
4. Highlighted system rendered above the background LOD even when aggregation
   omitted it.
5. Explicit planner navigation followed by exact map return-state restoration,
   without map-side plan mutation.
6. Evidence and saved-system overlays visible simultaneously with distinct,
   text-supported semantics.
7. One-time auto-fit followed by manual camera movement that survives
   selection, loading, and layer changes.
8. Live-update stream: a deterministic fixture applies successive scene
   update batches while the activity-pulse layer animates; camera,
   selection, and layer toggles survive every batch, and frame cost
   during the stream is measured and recorded.

## Region Data And Legal Gate

The V5 research report identifies `klightspeed/EliteDangerousRegionMap` commit
`6c1191a58e1e593966f44f16235ab39d1ad24d84` as a useful implementation and
verification reference. Its MIT license covers its code, not Frontier's region
names or galaxy geography.

No new third-party region data may be committed by this checkpoint. Before
shipping region geometry, the implementation stage must:

- inventory the region data already present in ED-Finder;
- verify all 42 names, IDs, lookup orientation, scale, origin, and boundaries;
- record provenance and redistribution reasoning;
- derive label points from region interiors, using stored centroids only as an
  explicit fallback; and
- prove region alignment with automated fixtures plus desktop visual review.

Raven Colonial screenshots are usability warnings only. No layout, styling,
assets, or interaction design may be copied or closely imitated.

## Research-Control Run

Stage 26B begins with a paid, artifact-backed Research Control run against the
exact merged ED-Finder commit containing this contract. It must use DeepSeek Pro
with a broad specialist fan-out and retain complete, validated artifacts rather
than prose appendices.

Required retained artifacts are:

1. `map-scene-contract.ts`, validated by the strict in-memory TypeScript gate;
2. `map-renderer-adapter.ts`, validated by the same gate;
3. `map-bakeoff-scenarios.ts`, containing deterministic fixtures for all eight
   integration scenarios and validated by the same gate;
4. `map-region-verification.json`, validated as JSON and covering the 42 named
   regions plus the unmapped sentinel; and
5. `map-research-closure.md`, linking each requirement to primary evidence,
   retained artifacts, disagreements, and unresolved legal or measurement work.

The run must use repository search/read evidence pinned to the registered
commit. Generated code remains non-executable during generic research.

## Renderer Bake-Off

No renderer is selected by Stage 26A. Stage 26B must compare these three
candidates through one shared Vite/React desktop harness:

- deck.gl `OrbitView` with its orthographic top-down posture and continuous
  tilt path;
- deck.gl `OrthographicView` as the deliberately top-down control candidate;
- Three.js with React Three Fiber and an explicit camera-transition design.

Every candidate receives the same deterministic 100,000- and 500,000-system
datasets, region layer, controls, scenarios, instrumentation, and Playwright
journey. A candidate cannot be skipped because another looks promising.

The recorded decision must cover frame-time percentiles, initial load,
click-selection latency, memory, compressed bundle contribution, context-loss
recovery, region correctness, overlap handling, keyboard workflow, and all seven
integration scenarios. Unknown measurements remain unknown; they are not
converted into passes.

The dimensions above are correctness and performance gates: a candidate
failing them is eliminated regardless of appearance. Candidates passing
the gates then receive an owner-judged visual quality review, conducted
side-by-side on the required viewports against the same scenes, scoring
glow/bloom rendering, softness of region boundaries, motion design of
the animated layers, and overall depth and atmosphere. The review notes
and comparison screenshots are retained in the recorded decision, and
the final selection among gate-passing candidates weighs this review as
a first-class criterion. As informational context only, the recorded
decision also notes each candidate's WebXR support path; this selects
nothing and authorizes nothing.

## Delivery Sequence

- **Stage 26A:** authorize and pin this contract. Documentation only.
- **Stage 26B:** run artifact-backed research and the isolated three-renderer
  bake-off; select a renderer only from recorded evidence.
- **Stage 26C:** implement the region-first replacement foundation behind an
  isolated development entry, with no production route cutover.
- **Stage 26D:** wire Finder, Cluster Search, Compare, saved/evidence overlays,
  selected-system context, and explicit planner hand-off through the typed scene
  boundary.
- **Stage 26E:** complete parity, accessibility, performance, context-loss,
  visual, and browser gates; cut over deliberately and then remove superseded
  frontend map code.

## Stage 26A Exit Criteria

Stage 26A is complete when this contract, the canonical roadmap, `CLAUDE.md`,
the documentation index, and the change log are merged with all protected checks
green.

Completion of Stage 26A authorizes Stage 26B only. It does not authorize a
production renderer, production map cutover, backend schema change, canonical
write path, or planner-map fusion.

## Stage 26B Artifact Acceptance

The repaired five-file research bundle is retained at
`artifacts/map-foundation/stage-26b/`. Local acceptance covered strict joint
TypeScript compilation, JSON parsing, exact sentinel-plus-42-region comparison
against the pinned ED-Finder source, targeted semantics for the repaired
auto-fit and R3F state-machine behavior, and presence of 17 unique named
fixtures. This acceptance does not claim renderer benchmarks, select a
renderer, or authorize runtime integration; the equal three-renderer bake-off
remains the next Stage 26B gate.

That gate subsequently completed. The retained measurement receipt and
selection rationale are documented in
[`stage-26b-renderer-bakeoff-decision.md`](./stage-26b-renderer-bakeoff-decision.md):
Three.js/R3F is selected for the isolated Stage 26C foundation, with production
cutover and unresolved performance work explicitly deferred.
