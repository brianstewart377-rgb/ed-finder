# V2 Map review for the V3 Babylon delivery

**Status:** historical implementation review and migration evidence, not V3
product or architecture authority
**Review date:** 2026-09-13
**Reviewed implementation:** the Stage 26E React/React Three Fiber production
map and its retained 2-D canvas fallback under `frontend/`
**Target informed by this review:** the Svelte/Babylon implementation in
`apps/web/`

The current delivery authority remains the
[V3 Babylon Galaxy and System Map delivery plan](v3-babylon-map-delivery-plan.md)
and the authority chain it names. This document answers a narrower question:
what the V2 map actually did, what evidence supports it, what is safe to learn
from it, and what must not cross the migration boundary.

## Executive verdict

V2 is a valuable interaction prototype and evidence archive, but it is not a
safe renderer or data contract to port. Its strongest work is the deterministic
42-region build pipeline, camera and view-preset behaviour, bounded rendering,
context-loss handling, overlap chooser, and the discipline of retaining browser,
GPU and memory receipts.

Its largest defect is fundamental to the new product requirement: the active
R3F scene fetches and reports a real heatmap but does not render that geometry.
It hard-disables `DensitySwirl` and always displays `VolumetricGalaxy`, whose
shader constructs a fixed four-arm logarithmic spiral, disk, bulge and dust
field. The visible Galaxy density is therefore procedural even while the UI,
tests and telemetry can describe the heatmap as active. This is a truth failure,
not a styling preference.

V2 also represents 64-bit system addresses as JavaScript `number`, selects
viewport records in coordinate order before applying its promised notable-first
ordering, silently bridges missing route waypoints, and lacks a complete
keyboard/screen-reader equivalent for visible targets. It has no interactive
System Map or colonisation Architect surface.

The V3 decision is consequently:

- preserve behaviours and evidence patterns only where independently verified;
- rebuild data, identity, scene ownership, rendering and accessibility contracts
  in the renderer-neutral V3 platform;
- use the canonical 42-region source, not the V2 emitted asset as authority;
- render catalogue density only from generation-pinned real coordinates; and
- retire every factual-looking procedural Galaxy path.

## Review scope and method

The review covered both V2 implementations:

1. The Stage 26E default production path rooted at
   [`ProductionMapTab.tsx`](../../frontend/src/features/map-foundation/ProductionMapTab.tsx)
   and [`R3FMapFoundation.tsx`](../../frontend/src/features/map-foundation/R3FMapFoundation.tsx).
2. The retained canvas fallback in
   [`GalacticMap.tsx`](../../frontend/src/features/map/GalacticMap.tsx).

The audit traced:

- API query semantics and response contracts;
- renderer adapters, scene composition, LOD and fade behaviour;
- camera, pointer, keyboard and selection flows;
- region generation, validation and attribution;
- routes and domain overlays;
- accessibility and failure behaviour;
- unit, component and browser-test coverage; and
- retained Stage 26 visual, performance, GPU and memory evidence.

The following focused suites were rerun from the current checkout:

| Suite                     |                     Result |
| ------------------------- | -------------------------: |
| `frontend` map foundation |  20 files, 90 tests passed |
| `frontend` map suite      | 29 files, 171 tests passed |
| Python heatmap unit suite |             7 tests passed |

Passing tests establish that the preserved contracts still behave as their
tests describe. They do not overrule findings where those tests mock the
renderer, duplicate an expression instead of exercising production code, or
assert metadata rather than visible pixels.

The review also inspected the retained screenshots under
[`docs/development/evidence/`](evidence/) and Stage 26E receipts under
[`artifacts/map-foundation/stage-26e/`](../../artifacts/map-foundation/stage-26e/).
Those are historical observations, not proof of the present V3 runtime or a new
hardware baseline.

## Implementation map

```text
Finder results / reference / selection
                  |
          ProductionMapTab
        /         |          \
 map endpoints  V2 scene    layer controls / summaries
        |         |
        |     R3FMapFoundation
        |         |
        |      SceneContents
        |      /    |     \
 regions/lines  stars   VolumetricGalaxy (always)
 heatmap cells --------> DensitySwirl (hard-disabled)

Explicit rollback path: GalacticMap 2-D canvas
```

This shape explains several audit results. The React shell owns most data and
controls; a renderer-neutral-looking scene contract feeds the R3F runtime; but
production-only overlays also enter through a parallel prop path. The split
weakens the claim that one contract describes the full visible scene and lets
metadata say one thing while the renderer shows another.

## Scorecard

| Dimension              | V2 assessment                                             | V3 disposition                                                         |
| ---------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------- |
| Visible Galaxy density | **Blocker:** procedural field replaces fetched heatmap    | Rebuild from reconciled real-coordinate cells; ambient art isolated    |
| In-game regions        | Strong deterministic source work; presentation incomplete | Preserve source/provenance, rebuild derived assets and interactions    |
| System identity        | Unsafe `number` representation for uint64 SystemAddress   | Canonical branded decimal-string `Id64` end to end                     |
| Galaxy camera          | Good presets, pan/zoom, top-down and hysteresis           | Preserve behaviour through a tested camera state machine               |
| Semantic LOD           | Useful real-star lane; unreliable aggregate transition    | Rebuild around generation-pinned pyramid packets and explicit states   |
| Picking                | Usable system selection and exact-coordinate chooser      | Central picking service plus screen-space overlap and DOM parity       |
| Accessibility          | Canvas instructions and some keyboard camera control      | Rebuild target traversal, focus, announcements and semantic list       |
| Regions UX             | Lines, labels and current-camera region only              | Fill/hover/select/query with lookup/render agreement and label budgets |
| Routes                 | Typed overlay, progress and direction cues                | Preserve intent; reject gaps instead of silently bridging them         |
| Domain overlays        | Valuable early exploration and Powerplay concepts         | Re-enter through versioned domain-owned contributions                  |
| Timeline               | Summary data, not a rendered spatial/time layer           | Rename as summary or implement a genuine scrubbed map contribution     |
| System Map             | Not present                                               | New Babylon `SystemScene` and semantic orrery                          |
| Colonisation Architect | Not present                                               | New explicit planning surface and intent-only hand-off                 |
| Resilience             | Strong resize/DPR/context-loss/error-boundary intent      | Preserve and expand across WebGPU and WebGL2                           |
| Performance evidence   | Useful historical receipts; weak modern baseline          | New multi-device CPU/GPU/resource/pick evidence                        |
| Automated coverage     | Broad but contains important visibility blind spots       | Test rendered products, truth metadata and ambient-off visuals         |

## Findings register

### Blockers

| ID     | Finding                                                                                                             | Evidence                                                                                                                                                                                                                                                                                                         | Required V3 response                                                                                                                                         |
| ------ | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| V2-B01 | The visible whole-Galaxy density is procedural while the fetched heatmap is not rendered.                           | [`SceneContents.tsx`](../../frontend/src/features/map-foundation/SceneContents.tsx) always mounts `VolumetricGalaxy` and wraps `DensitySwirl` in `false && heatmap`; [`VolumetricGalaxy.tsx`](../../frontend/src/features/map-foundation/VolumetricGalaxy.tsx) implements fixed spiral-arm/disk/bulge equations. | Delete this factual path. Only `catalogue-density` may communicate occupied space; ambient artwork must be separate, subordinate and independently disabled. |
| V2-B02 | The “Heatmap” switch and telemetry can claim that a heatmap is active without changing the procedural visual field. | [`ProductionMapTab.test.tsx`](../../frontend/src/features/map-foundation/ProductionMapTab.test.tsx) asserts an adapted cell count through a mocked renderer, not visible geometry.                                                                                                                               | Layer state must be derived from the accepted rendered revision. Add rendered-pixel/product inspection and ambient-off acceptance.                           |
| V2-B03 | SystemAddress identity is lossy above `Number.MAX_SAFE_INTEGER`.                                                    | V2 map/API/scene contracts type `id64` as `number`, including Map/Set keys.                                                                                                                                                                                                                                      | Use V3 branded decimal-string `Id64` through JSON parsing, stores, URLs, contracts, picking and persistence.                                                 |
| V2-B04 | V2 has no interactive System Map or colonisation Architect workspace.                                               | The reviewed implementation ends at Galaxy system selection/detail hand-off.                                                                                                                                                                                                                                     | Deliver a separate semantic `SystemScene`, body/facility identity, truth ladder and explicit planner intents.                                                |

### High-severity findings

| ID     | Finding                                                                                                                   | Consequence                                                                                                                                          | Required V3 response                                                                                                               |
| ------ | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| V2-H01 | The heatmap is a rated-system/score aggregate, not a base catalogue-density source.                                       | Unrated catalogued systems are omitted; average development score drives colour and indirectly point size, so “density” mixes count and suitability. | Build density from all eligible generation records. Keep ratings as a separately named overlay with its own legend and provenance. |
| V2-H02 | Requested `voxel_size` is used for geometry even when the API serves a different `voxel_bucket`.                          | Non-default resolutions can place/size cells using the wrong grid contract.                                                                          | Return and consume exact cell origin, level and size from the published pyramid packet.                                            |
| V2-H03 | The viewport SQL limits coordinate-ordered candidates before notable-first sorting.                                       | Populated or high-priority stars outside the first coordinate slice can be omitted despite the endpoint promise.                                     | Apply deterministic priority before the bound, or use a documented spatial/priority sampling contract with guaranteed targets.     |
| V2-H04 | Wide-box rejection is indistinguishable from a valid empty result.                                                        | The client cannot explain whether no stars exist or the detail request was refused.                                                                  | Make `complete`, `truncated`, `too_wide`, `stale`, `generation` and bounds explicit and mutually testable.                         |
| V2-H05 | Keyboard control moves the camera but does not provide complete target traversal or a semantic mirror of visible targets. | A keyboard or screen-reader user cannot perform the same inspect/select journey as a pointer user.                                                   | Maintain a virtualized DOM target list, stable focus, spatial navigation, overlap parity and announcements.                        |
| V2-H06 | Missing route waypoints are filtered out before segments are constructed.                                                 | Remaining points are joined across the gap and `currentWaypointIndex` can identify the wrong system.                                                 | Preserve waypoint slots; show unresolved/broken segments and resolve progress against canonical waypoint identity.                 |
| V2-H07 | The broad typed feature-handoff command returned by the reducer is discarded by the live production wrapper.              | Tests imply a richer interaction matrix than the app actually exposes; most cross-workspace journeys are not integrated.                             | Route all map intents through the application command boundary and test the composed app journey.                                  |
| V2-H08 | No response generation, source count, coverage, freshness or reconciliation receipt travels with the map aggregates.      | A rendered density or overlay cannot prove which source publication it represents.                                                                   | Require immutable generation/provenance metadata and reconciliation at builder, API, client and evidence layers.                   |

### Medium-severity findings

| ID     | Finding                                                                                                                                                          | V3 response                                                                                                    |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| V2-M01 | Whole-Galaxy region lines and orange glow dominate the data hierarchy.                                                                                           | Give regions distinct fill/boundary/selected states; budget contrast by semantic importance.                   |
| V2-M02 | Region and Finder labels visibly collide in retained whole-Galaxy and local frames.                                                                              | Use priority, occlusion, clustering, safe-area and guaranteed-target label policies with deterministic tests.  |
| V2-M03 | Regions are not filled, hovered, selected or queried; “current region” follows only the camera centre.                                                           | Make region geometry and lookup first-class scene targets, while keeping unknown space explicit.               |
| V2-M04 | Exact-coordinate equality is the only overlap condition.                                                                                                         | Resolve hits in screen space and expose the same candidate set in the DOM chooser.                             |
| V2-M05 | Shift-drag changes pitch but bearing remains fixed at zero.                                                                                                      | Implement a deliberate top-down/tilt/orbit camera model with bounded pitch and tested restore semantics.       |
| V2-M06 | Real-star monitoring uses a permanent animation-frame loop to observe React prop changes.                                                                        | Drive streaming from explicit camera-store revisions with debounce, cancellation and stale-response guards.    |
| V2-M07 | The intended density-to-star fade mutates a ref attached to the disabled density group; the volumetric opacity prop is not guaranteed to rerender with that ref. | Put semantic LOD state in one reducer and apply it to live Babylon material/visibility state atomically.       |
| V2-M08 | Timeline is offered as a map layer but only renders a summary.                                                                                                   | Either implement spatial/time filtering and a scrubber or call it a non-map summary.                           |
| V2-M09 | Cluster `system_count` sums economy counts and can double-count systems; hull radius is a fixed approximation.                                                   | Keep clusters domain-owned, versioned and explicit about membership, radius method, overlaps and uncertainty.  |
| V2-M10 | Exploration may show prior viewport data during a pan without a corresponding current-box guard or stale indicator.                                              | Bind every contribution to bounds and revision; never present retained data as current without visible status. |
| V2-M11 | Region runtime validation checks counts and finiteness but not the exact 1–42 ID/name set, pinned hash, exact raster dimensions or geometry/lookup agreement.    | Enforce all of these at build and release gates against the canonical source.                                  |
| V2-M12 | Production code imports a scene contract from a historical artifact directory.                                                                                   | Move durable contracts into maintained V3 packages; artifacts remain immutable evidence only.                  |
| V2-M13 | A reducer that appears pure can mutate arrays shared with the input state.                                                                                       | Use immutable contribution/state transitions and referential-purity tests.                                     |
| V2-M14 | Synthetic negative IDs stand in for route waypoints without a SystemAddress.                                                                                     | Give non-system targets their own discriminated identity; never overload `Id64`.                               |
| V2-M15 | Production debug logging remains in viewport/fade paths.                                                                                                         | Use structured opt-in diagnostics and exclude debug noise from normal sessions.                                |

## Data truth review

### Catalogue density

The V2 `/api/map/heatmap` endpoint bins systems that join a ratings row and have
a non-null selected score. It requires a minimum of five such systems per voxel,
sorts by rated count and caps the response at 50,000 cells. The response contains
`n`, average score and maximum score.

That dataset is useful for a **rated-system analytical overlay**. It is not a
truthful base representation of catalogued star density because:

- unrated but catalogued systems are excluded;
- low-count occupied cells are deliberately omitted;
- truncation removes cells after a density sort;
- position coverage is not reconciled to the catalogue generation;
- colour represents mean development score rather than count; and
- [`DensitySwirl.tsx`](../../frontend/src/features/map-foundation/DensitySwirl.tsx)
  derives display size from colour brightness, further mixing score and density.

The live fallback query is visible in
[`apps/api/src/routers/map.py`](../../apps/api/src/routers/map.py); the R3F adapter
in [`production-parity.ts`](../../frontend/src/features/map-foundation/production-parity.ts)
ignores cell `n` and maps `avg_score` to colour. Even if `DensitySwirl` were
re-enabled, it would still not satisfy the new base-density requirement.

V3 must have two distinct contributions:

- **Known systems density:** generated from every eligible real system
  coordinate in a published generation, with exact level/count reconciliation.
- **Ratings/suitability:** an optional domain overlay that may encode score but
  never masquerades as occupancy or density.

An empty or unavailable catalogue-density packet must produce an explicit empty
or unavailable state. Procedural stars, texture brightness, noise and spiral
equations must never fill the factual gap.

### Region truth

V2's region work is its best reusable data lesson. The build reads the audited
[`region_map.json`](../../apps/importer/src/data/region_map.json), decodes the
2048×2048 run-length grid, extracts deterministic boundaries and label anchors,
and emits a bounded static resource. Retained evidence records:

- 42 labels and 42 unique non-zero region IDs;
- 22,595 continuous boundary segments;
- a 2,312,898-byte emitted resource under a 4 MiB limit;
- deterministic lookup fixtures and whole-grid reach checks; and
- retained upstream, attribution and licensing review.

This should inform the V3 builder, but V3 must regenerate from the pinned
canonical source and close the gaps V2 leaves:

- verify the exact ID/name set rather than count alone;
- verify canonical LF-normalized SHA-256 and reviewed upstream revision;
- require exactly 2048 rows of decoded width 2048;
- prove lookup, fill, boundary and label-anchor agreement;
- define simplification error at every LOD;
- expose unknown/outside-source space rather than nearest-region invention;
- make regions hoverable, selectable and queryable; and
- solve labels as a deterministic priority/layout problem.

The source and derived resource retain the reviewed Frontier/community
attribution and non-commercial constraints. A future commercial deployment
requires its own explicit rights decision.

### Individual systems and semantic LOD

The V2 real-star lane has good product behaviour worth retaining:

- a 250 ms settle before requesting a new spatial box;
- grid snapping and stable query keys;
- enter/exit hysteresis around local detail;
- explicit bounds and a hard result cap;
- cancellation and stale-response rejection in the primary lane;
- spectral colouring; and
- real-star suppression when the response is truncated.

The implementation contract still needs replacement. When the response is
truncated, V2 suppresses all returned real stars and expects the heatmap to be
the aggregate fallback. Because the factual heatmap geometry is disabled, the
visible fallback is procedural. Moreover, the API promise of notable-first
selection is not upheld: its CTE orders by `x, y, z`, applies `LIMIT`, and only
then sorts that subset by population and spectral class.

V3 should select an explicit LOD level from semantic scale and projected density,
return bounded aggregate and/or star records for the same generation, and
guarantee current, selected, reference, route and explicit-highlight targets.
Every packet needs bounds, level, cell origin/size, generation, completeness,
truncation and coverage. Transitions must be driven from accepted packet state,
not from a visual ref that can drift out of sync with the UI.

## Rendering and visual review

### What works

- The cold-open whole-Galaxy view gives immediate orientation.
- A single camera model supports explicit Galaxy, results and reference presets.
- Top-down is a deliberate control rather than an accidental extreme pitch.
- Tilt reveals real system height, and pan limits keep the Galaxy reachable.
- Current, selected and reference markers generally remain distinguishable.
- Controls and HUD use a coherent visual language and remain discoverable.
- Demand rendering, DPR bounds, typed buffers and bounded layer counts are
  sensible foundations.
- Resize, WebGL context loss/restoration and renderer failure have explicit
  handling rather than silent blank-canvas behaviour.

### What does not work well enough

The retained screenshots show a map whose strongest visual signal is often the
orange region-boundary network, not the real stellar distribution. At the full
Galaxy scale, many region names compete or overlap; in local Finder views,
system names overlap severely. Density is visually faint or absent while the
procedural glow makes the data provenance impossible to infer. Some frames also
place meaningful content close to HUD/footer occlusion zones.

The single orange/cyan glow vocabulary flattens the hierarchy between factual
regions, selected targets, routes and ambient form. V3 needs a deliberate
visual grammar:

- neutral, data-derived catalogue density as the base spatial evidence;
- regions readable without overpowering the Galaxy;
- high-salience current/selected/reference/route endpoints;
- domain overlays with their own legend and truth class;
- planned, schematic, uncertain and unavailable states distinguishable without
  colour alone; and
- ambient art visibly subordinate and removable.

The V3 Review Lab should capture ambient-on and ambient-off frames using the
same camera, data revision and layer state. If the data-rich Milky Way vanishes
when ambient is disabled, the build fails.

## Camera, input and selection review

V2 demonstrates useful interaction choices:

- wheel/pinch zoom and drag pan;
- keyboard pan/zoom with a switch for single-key shortcuts;
- modal and text-entry protection;
- reduced-motion handling;
- smooth preset changes and camera continuity;
- selected/reference fly-to behaviour; and
- an overlap chooser rather than an arbitrary pick when systems coincide.

The V3 camera should retain these outcomes through renderer-neutral commands and
a Babylon adapter, but extend them with:

- bounded orbit/bearing as well as pitch;
- a real keyboard target-navigation model;
- screen-space hit grouping rather than exact world-coordinate equality;
- deterministic nearest/next target ordering;
- stable focus when LOD packets change;
- semantic announcements for focus, selection, loading, stale/truncated data
  and view transitions; and
- an equivalent virtualized DOM list of current pickable targets.

Babylon's GPU and CPU picking facilities should sit behind one central
`PickingService`. Selection identity must come from the renderer-neutral target
record and lossless `Id64`, never from display index alone.

## Routes and product hand-offs

V2's typed scene and hand-off work correctly recognized that map actions need
application ownership. It includes route directions, progress styling and a
details surface, and it can keep current/selected/guaranteed systems present.

The live composition is narrower than the contract implies. The production
wrapper resolves an interaction but discards the returned command; only direct
Finder and Inspect callbacks are fully integrated. Compare, Saved, Evidence,
Planner and other tested hand-offs are therefore design evidence, not a proven
live journey.

Route geometry also filters unresolved systems before connecting segments. If
waypoint B is missing from A→B→C, the renderer draws A→C, which falsely implies
a valid continuous leg. The filtered array can also shift the current waypoint.

V3 must:

- keep route waypoint identity independent of coordinate resolution;
- render unresolved legs as explicit gaps/errors;
- never create synthetic SystemAddress values for non-system targets;
- preserve selected/current/route endpoints at every LOD;
- emit a typed application intent for Inspect, Compare, Save and Plan; and
- prove the complete composed-app journey, including Back restoration.

## Domain overlay review

The exploration and Powerplay layers are useful prototypes because they treat
the map as an analytical workspace rather than decoration. Personal sync-key
scoping, visited systems, travel trail, scan/map completeness, Powerplay
uncertainty and freshness, route state and detail panels are all strong product
directions.

They should not be ported as renderer-owned behaviours. Each V3 domain must
publish a versioned contribution with:

- owner and truth class;
- source generation/revision and freshness;
- explicit bounds/completeness/truncation;
- stable target identity and picking semantics;
- visual tokens and legend meaning;
- accessible semantic projection; and
- removal/replacement rules.

The V2 cluster layer particularly needs semantic repair: summing counts across
multiple economies can double-count a system, and a fixed 500 LY radius is an
approximation rather than a measured membership hull. Cluster membership,
method, version and uncertainty must remain visible.

Timeline should not remain a check-box “layer” unless time actually filters or
animates spatial records. A bucket-count summary belongs in a panel; a true map
timeline requires a scrubber, time-bound contribution revisions and clear
incomplete-history semantics.

## Accessibility review

V2 includes several good foundations:

- the canvas has a named region/instructions;
- camera controls are buttons as well as gestures;
- single-key shortcuts can be disabled;
- typing and modal contexts block map shortcuts;
- overlap candidates are exposed as buttons; and
- retained Axe runs reported zero automatically detected A/AA violations for
  the composed route.

Automated Axe success is not functional equivalence. Most labels are hidden from
assistive technology, the visible system/region set has no semantic companion,
and there is no live keyboard traversal across map targets. The fallback canvas
is also pointer-only for selection.

V3 acceptance must be task-based: without a pointer, a user can discover current
map state, move among visible/prioritized targets, inspect overlap candidates,
select a system or region, enter the System Map, select a body/site, understand
truth and blocker states, issue an explicit plan intent, and return with focus
and context restored.

## Resilience and performance review

### Worth preserving

- bounded Finder, aggregate and real-star counts;
- demand frame loop rather than permanent full-scene animation;
- typed arrays and explicit buffer budgets;
- renderer resize and DPR synchronization;
- stale/cancelled request protection in the main real-star lane;
- context-loss events and error boundary;
- deterministic stress fixtures; and
- separate browser, memory and physical-GPU receipts.

### Evidence limits

The retained Stage 26E physical-GPU receipt used one Intel UHD/Chromium WebGL2
environment. It recorded p95 GPU time of 18.982 ms at 1280×720 and 27.243 ms at
1440×900, with a recorded maximum near 38.9 ms. That passed the historical 50 ms
provisional gate but does not establish 60 fps at 1440×900 and does not cover a
discrete GPU, Firefox, Babylon, WebGPU or modern product composition.

The live-route memory receipt is encouraging—roughly 27–30 MB CDP heap maxima
against a 256 MiB gate—but isolated fixture readings elsewhere were much higher
and were taken without forced garbage collection. Memory evidence should be
split into:

- stable engine/resource ownership across repeated Galaxy↔System transitions;
- JS/application heap;
- GPU buffer/texture estimates and live resource counts; and
- leak deltas after warm repeated navigation, not a single peak alone.

The original `requestAnimationFrame` sampling mostly measured display cadence,
not per-phase CPU render cost. Later timer-query evidence improved GPU truth,
but V3 still needs CPU update, cull, upload, draw, label layout and picking
breakdowns alongside draw calls, buffer bytes and long-frame distributions.

The V3 baseline must cover approved integrated and discrete Windows hardware,
WebGPU and WebGL2, Chrome and Firefox where applicable, both required viewports,
production-like composition, cold/warm startup, dense and sparse views, and
repeated Galaxy↔System transitions.

## Test and evidence review

V2 has substantial test volume and retained evidence, but the critical density
defect demonstrates why assertions must cross the renderer boundary.

Two examples are decisive:

1. `ProductionMapTab.test.tsx` replaces `R3FMapFoundation` with a DOM mock and
   asserts `data-heatmap-count`. It proves prop composition, not that heatmap
   geometry is mounted or visible.
2. `SceneContents.test.ts` reimplements target-opacity expressions and includes
   a manual checklist. It neither imports the production transition function nor
   renders `SceneContents`, so it cannot detect the hard-disabled density group.

V3 should keep fast unit and contract tests, then add:

- adapter product tests that inspect actual Babylon meshes/materials/instances;
- a rule that factual layer telemetry reflects an accepted rendered revision;
- ambient-off visual goldens at fixed data/camera state;
- empty-density tests that prove no procedural replacement appears;
- API-builder reconciliation tests for every complete density level;
- generated-packet provenance and generation mismatch tests;
- full uint64 identity fixtures through API, store, route, pick and persistence;
- full composed-app keyboard journeys;
- route-gap and missing-association visuals;
- label collision/safe-area fixtures; and
- cross-backend semantic and screenshot comparison.

Historical screenshot names and prose are not sufficient evidence when source
code has since diverged. New receipts must include commit, asset/data hashes,
runtime flags, browser/OS/GPU, backend, viewport/DPR, fixture or generation ID,
layer state and a reproducible command.

## The 2-D fallback

The canvas fallback is simple and comparatively robust. It uses correct x/z
projection, renders the fetched heatmap rather than replacing it, supports basic
pan/zoom/select, bounds DPR and makes a useful no-WebGL diagnostic reference.

It is not a complete accessibility or product fallback:

- it opens around Finder results rather than a complete Galaxy context;
- it has no meaningful y/depth presentation;
- it exposes region centroids but not authoritative boundaries/fills;
- target selection is pointer-only;
- nearest-hit selection has no overlap chooser;
- state is not continuous with the R3F scene;
- resize invalidation is weak;
- heatmap geometry uses requested rather than served voxel size; and
- score remains entangled with the base star/density presentation.

V3's degradation path should be useful DOM search/results/details with preserved
selection and camera description, plus a compatible WebGL2 Babylon backend when
WebGPU is unavailable. The old canvas is evidence, not the intended V3 fallback.

## Preserve, redesign, retire

### Preserve as independently tested behaviour

- explicit Galaxy/results/reference/top-down view presets;
- smooth camera transitions and exact Back restoration;
- zoom hysteresis and request settling;
- current, selected, reference and route-endpoint priority;
- bounded packets and deterministic sampling;
- overlap chooser intent;
- reduced-motion, shortcut toggle and input/modal protection;
- demand rendering, DPR/resize handling and context-loss UX;
- deterministic 42-region derivation from the audited source; and
- receipted browser, GPU, memory and visual evidence.

### Redesign behind V3 contracts

- region fill/boundary/label/lookup and interaction;
- catalogue pyramid and star-detail streaming;
- camera state and Babylon application;
- centralized picking and semantic target projection;
- route geometry and unresolved waypoint states;
- domain overlays and legends;
- label prioritization and safe areas;
- quality tiers, resource lifecycle and performance instrumentation; and
- all product hand-offs.

### Retire; do not port

- `VolumetricGalaxy` as visible factual Galaxy structure;
- `GalaxyBackdrop` random points or procedural clouds as density evidence;
- the `DensitySwirl` naming and score/brightness sizing contract;
- any layer switch whose displayed state differs from accepted rendered state;
- numeric `id64` keys or synthetic negative SystemAddress values;
- coordinate-first capped viewport selection presented as notable-first;
- unresolved-waypoint filtering that draws false direct legs;
- exact-coordinate-only overlap detection;
- permanent frame polling for application-state changes;
- artifact-directory imports in production code;
- renderer-owned domain mechanics; and
- a “Timeline layer” that does not affect the map.

## Gates added to the Babylon programme

This audit directly justifies the following V3 release gates:

1. **Density truth:** all visible `catalogue-density` occupancy/counts reconcile
   to real generation-pinned coordinates; ambient-off remains data-rich; empty
   data never produces factual-looking generated structure.
2. **Region truth:** exactly 42 canonical regions, pinned source hash, exact
   names/IDs, deterministic geometry, and lookup/fill/boundary/label agreement.
3. **Identity:** uint64 maximum and above-safe-integer addresses survive API,
   caching, routing, selection, picking, persistence and cross-workspace return.
4. **Packet honesty:** generation, bounds, level/cell size, completeness,
   truncation, coverage, freshness and source counts remain inspectable.
5. **Rendered-state honesty:** controls, legend, telemetry and accessibility
   describe the accepted rendered revision, not merely fetched props.
6. **LOD continuity:** factual aggregate-to-star transitions preserve guaranteed
   targets and never fall back to procedural occupancy.
7. **Route integrity:** unresolved endpoints remain explicit; no false bridge or
   shifted current waypoint is rendered.
8. **Accessible equivalence:** the complete Galaxy→System→Architect→return task
   works without a pointer and exposes every pickable target semantically.
9. **System truth:** physical, derived, schematic, planned and unavailable
   properties are distinguishable per property; no invented orbital phase.
10. **Evidence:** composed-product WebGPU/WebGL2, browser, physical-GPU, memory,
    visual and failure evidence is tied to immutable code/data identities.

## Final migration decision

V2 should remain frozen historical evidence. The Babylon work should not start
by translating Three components into Babylon classes. It should start from the
renderer-neutral V3 scene, identity, data-generation and truth contracts, then
recreate the proven interaction outcomes with better data honesty, accessibility
and performance observability.

Frozen does not mean ignored. Every V3 map workstream must return to the relevant
V2 source, behaviour, screenshot, test and receipt; identify what V2 did well and
poorly; and define a measurable improvement before implementation is accepted.
Where V2 had no capability, the comparison records that absence and evaluates
the nearest applicable interaction, accessibility, resilience and evidence
patterns. The required method and area-by-area ledger live in the
[V3 delivery plan](v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol).

The most important correction is simple and absolute: the new Galaxy may look
beautiful because real catalogued coordinates form a beautiful structure. It
must never look populated because a shader, random field or painted mask says
that empty or unavailable data is populated.
