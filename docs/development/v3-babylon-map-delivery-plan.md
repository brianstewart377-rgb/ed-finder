# V3 Babylon Galaxy and System Map delivery plan

**Status:** current implementation plan, not programme or product authority
**Date:** 2026-09-14
**Target:** `apps/web/`, Svelte 5/SvelteKit 2 and Babylon.js 9-class
**Scope:** best-in-class Galaxy Map, semantic System Map, and explicit
colonisation/Architect planning participation

The authorities for this plan are the
[V3 roadmap](../ROADMAP.md),
[application stack decision](v3-application-stack-decision.md),
[spatial product contract](../colonisation-redesign/spatial-platform-product-contract.md),
[spatial architecture decision](../colonisation-redesign/spatial-platform-architecture-decision.md),
[search/spatial/derived-data decision](v3-search-spatial-derived-data-decision.md),
[browser validation lanes](v3-browser-validation-lanes.md), and
[Ratings V4 freeze](ratings-v4-freeze/README.md). If this plan conflicts with
one of those documents, the authority wins.

This plan does not authorize production deployment, database mutation, live
data access, or silent Build Plan mutation. It turns the accepted direction
into an executable delivery sequence and identifies the work that can proceed
against deterministic fixtures while Ratings V4 production generation settles.

## Outcome

Deliver one continuous, original ED-Finder spatial experience that is excellent
with every product overlay switched off and becomes more useful as Finder,
colonisation, Commander History, Routes, Powerplay, CPE and CRE contribute
information.

The intended experience is:

1. Explore the full Milky Way and all 42 named regions at a useful wide scale.
2. Move continuously through regional and local scales using real Elite
   Cartesian light-year coordinates.
3. Search, fly to, select, compare and query real systems without losing camera
   or selection context.
4. Deliberately enter a selected system and see an interactive semantic orrery:
   stars, planets, moons, rings, orbital relationships and attached
   infrastructure at the highest fidelity justified by the data.
5. Enter a colonisation/Architect mode in that System Map to understand
   candidate orbital and surface locations, existing and planned facilities,
   dependencies, blockers, construction state and plan consequences.
6. Return to the Galaxy at the exact meaningful place and state from which the
   system was entered.

The product promise is not “a chart next to a result list.” It is a spatial
workspace that makes **Explore → Inspect → Plan → Review/Export** feel like one
journey.

## Owner reference set — 2026-09-14

The supplied Galaxy/System Map images are visual references, not executable
instructions. They establish six non-negotiable product outcomes:

1. Nebula landmarks appear at their real catalogue coordinates. The current
   non-commercial lane consumes every row in EDAstro Mapcharts' purpose-published
   Nebulae Coordinates CSV, retains a stable row identity, source type and region
   ID, visibly credits EDAstro / CMDR Orvidius, and keeps its schematic cloud
   radius separate from coordinate truth.
2. Inspect contains an interactive three-dimensional System Map. Catalogue body
   class, subtype, radius, arrival distance and ring evidence remain factual;
   semantic orbit placement and display radius are explicitly schematic.
3. Individual stars use recognizably different presentation for all supplied
   stellar families: T Tauri/Herbig, Y/T and L brown dwarfs, M/K/G/F/A/B/O
   main-sequence stars and giants, Wolf-Rayet, hypergiant, carbon, white dwarf,
   neutron, black hole and supermassive black hole, plus an honest unknown
   fallback.
4. Real individual-system packets are densest at wider individual-star ranges
   and use progressively smaller bounded budgets at close range. Whole-Galaxy
   scale remains the real catalogue-density layer; it never fabricates stars.
5. Every rendered catalogue star is pickable and opens a semantic information
   card with a keyboard-equivalent result/action path.
6. A separate Commander History heatmap can be toggled from Explore. Its cells
   or markers come only from the local profile's imported journal visits and
   never masquerade as catalogue density.

Each outcome is release-blocking for the requested map experience. Visual
similarity alone is not acceptance: receipts and tests must prove data source,
truth class, interaction and the WebGPU/WebGL2 render product.

## What “best in class” means

Best in class is an acceptance standard, not permission to add decorative
complexity without evidence.

- **Spatially convincing:** a recognisable Milky Way, meaningful depth,
  restrained tilt, clear reference grid, legible systems and smooth semantic
  scale changes.
- **Information rich without lost geography:** all in-frame region names remain
  present; priority may improve placement and emphasis but never suppress a
  region. Secondary non-region overlays yield predictably where necessary.
- **Fast at ED scale:** bounded streaming and GPU-driven presentation stay
  responsive at the production-like 20k/40k tiers and degrade deliberately at
  stress/torture tiers.
- **Truthful:** factual, derived, planned, schematic, ambient and unavailable
  information never blur together.
- **Useful for decisions:** every visual state can lead to a clear action or an
  explanation. Colour, size or proximity never becomes hidden mechanics.
- **Accessible:** every pickable target, layer state, query, selection and
  planning action has a keyboard and semantic DOM equivalent.
- **Resilient:** resize, DPR changes, stale/empty/truncated/error data, backend
  failure and device/context loss never produce a silent blank map.
- **Original:** learn from Elite and community tools without copying Frontier or
  third-party code, assets, trade dress or unlicensed artwork.

## Visual research translated into product requirements

The visual review used current and historical Elite Galaxy/System Map images,
the [Elite Dangerous Galaxy Map tutorial](https://www.youtube.com/watch?v=k2l9V4c90cU&t=4s),
the official Trailblazers colonisation material, the two repository research
reports, and retained Stage 26 screenshots. These are research references, not
pixel-level design authority.

### Galaxy Map lessons

Elite's Galaxy Map succeeds because it combines a dense spatial field with a
small number of strongly prioritized cues: current location, selected target,
route, grid/plane, labels and contextual information. Different viewing modes
change the information while the Galaxy remains recognizable.

ED-Finder should preserve those interaction truths while improving analytical
clarity:

- one stable selection and reference language across mouse, keyboard and touch;
- current, reference, selected, Finder match, route waypoint, colony and
  warning states that remain distinguishable at a glance;
- an optional plane/grid and restrained axis/depth cues;
- search/fly-to, focus-current and restore-previous-view controls;
- top-down as a first-class working view, not a degraded 3-D camera angle;
- controlled tilt/orbit for depth inspection;
- filters and presets that alter contributions rather than replace the scene;
- route and range visualization without turning every nearby system into a
  permanent line network;
- a details surface that explains the selected system without covering the
  spatial task; and
- guaranteed labels for the current, selected, reference and explicit
  highlighted targets.

#### Zoomed stars and reference-grid benchmark

The tutorial's useful visual benchmark is the continuous move from Galaxy scale
into real individual systems: the star field retains depth, named targets remain
anchored, the selected target gets a crisp focus treatment, and a perspective
coordinate grid makes tilt and distance readable. ED-Finder does not need to
copy the surrounding Elite panel or trade dress to preserve those strengths.

- Individual-system translations are always the exact catalogue
  `x_ly/y_ly/z_ly` values. Zoom may change only presentation radius, label
  placement, LOD choice and visibility; it must never flatten, jitter or
  cosmetically redistribute stars.
- The reference grid is explicitly `SCHEMATIC`, lies on canonical Galactic
  `Y=0`, uses disclosed light-year intervals and changes interval at semantic
  scale boundaries. It cannot snap or move factual targets.
- Wide-to-local transitions remain one camera journey. Aggregate density and
  individual stars may cross-fade only when both packets belong to the same
  accepted catalogue generation; empty or truncated detail never reveals a
  generated substitute.
- At local scale, star cores remain crisp and restrained, glow remains a halo
  rather than the position itself, and the selected marker stays distinct
  without obscuring neighbouring systems.
- Tests prove the exact Babylon thin-instance translations, adaptive grid
  interval and bounded line count. Browser evidence captures tilted, top-down,
  wide and local states on WebGPU and WebGL2.

### Non-negotiable Galaxy truth gates

The in-game regions and the visible density field are release-blocking data
contracts, not art-direction approximations. A beautiful render that fails
either contract is not an acceptable Galaxy Map.

#### All 42 in-game regions

- The canonical region source is the audited
  [`apps/importer/src/data/region_map.json`](../../apps/importer/src/data/region_map.json):
  exactly 42 non-empty region IDs/names plus its declared origin, pixel scale
  and run-length-encoded lookup map.
- [`assets/PROVENANCE.json`](../../assets/PROVENANCE.json) pins the reviewed
  upstream revision and canonical LF-encoded repository SHA-256
  `910142d4deb510d80128509bf68cf3b8de8a2c45006d99d4233ee33d95321152`.
  Build/release validation recalculates that hash and rejects an unreviewed
  source change.
- A deterministic build step may decode the source into renderer-neutral masks,
  boundary geometry, label anchors and topology-preserving LODs. It must retain
  the exact region ID/name mapping and coordinate transform. Babylon receives
  those derived resources; it does not invent, hand-draw or procedurally smooth
  factual boundaries.
- Region fill, boundary, label, hover, selection and coordinate-to-region lookup
  must agree in top-down and tilted views. Unknown/outside-source coordinates
  remain explicitly unknown rather than being assigned to the nearest region.
- Simplified LOD geometry is permitted only with a documented maximum error and
  lookup regression tests against the canonical raster. Selected and current
  regions remain guaranteed through every LOD transition.
- The region layer ships with visible attribution and the retained
  [licence notice](../../frontend/public/assets/elite-dangerous-region-map.LICENSE.txt).
  The existing Frontier-derived/non-commercial provenance constraint must be
  resolved before any commercial deployment; visual polish cannot waive it.
- The release gate verifies 42/42 unique IDs and exact names, the pinned source
  hash, deterministic derived output, known coordinate fixtures, lookup/render
  agreement and no missing region resource on either rendering backend.

#### Real catalogue density, never a generated swirl

- The factual layer is named `catalogue-density` in code and **Known systems
  density** in the UI. Every occupied cell and every count originates from real
  system records with exact `x_ly/y_ly/z_ly` coordinates in the published
  canonical systems catalogue. Ratings V4 is neither an input nor a filter for
  this base layer.
- `v3_spatial.cell_summary` is the production LOD source. Its cell origin,
  centroid and `system_count` are built reproducibly from every coordinate row
  in that catalogue. At every complete pyramid level, the sum of
  `system_count` must reconcile to the complete source-system count for the
  pinned canonical generation. A derived-generation identifier may serve as a
  publication envelope, but it must never reduce density to rated systems.
- The renderer may apply a versioned count-to-size/opacity/colour transfer
  function so dense and sparse areas remain legible. It may not invent cell
  occupancy or positions with spiral equations, random points, noise fields,
  texture brightness, artist-painted masks or procedural star distributions.
- The shape can look like a galactic swirl because the real coordinates form
  that shape; it must never be made to look more spiral-like by adding factual-
  looking generated density. No procedural result participates in picking,
  filtering, search, LOD refinement, labels, region summaries or mechanics.
- Optional dust, nebula, starfield and Milky Way artwork is a separate,
  independently toggleable, non-pickable `AMBIENT` backdrop. It is visually
  subordinate, carries no density legend and cannot affect the factual density
  layer. The map must remain fully usable and recognizably data-rich with that
  backdrop disabled.
- The UI discloses that this is density of the current **catalogued/discovered
  dataset**, not a complete model of the roughly 400-billion-system Milky Way.
  Generation identity, source-system count, coverage/freshness, pyramid version,
  bounds and truncation state travel with the response and remain inspectable.
- Fixture, builder, API and visual tests prove deterministic cell output, source
  reconciliation, correct empty-space behaviour, no procedural/random input in
  the factual layer, cross-backend equivalence and a clean ambient-off baseline.

### System Map and colonisation lessons

Elite's System Map uses a semantic layout rather than literal astronomical
scale. Bodies remain recognizable and selectable, orbit structure is visible,
and a details panel follows selection. Its colonisation Architect mode overlays
candidate construction positions and construction information onto the same
system context.

ED-Finder should make that mode more explanatory and plan-aware:

- stars, barycentric groups, planets, moons, belts, rings and infrastructure are
  arranged as a legible hierarchy;
- physical measurements remain in details while display radius and spacing are
  separate semantic presentation values;
- an orbit is factual only property-by-property; absent trusted epoch/phase
  produces deterministic, labelled `SCHEMATIC` placement;
- candidate orbital lanes and body surface capacity are shown only when an
  owning mechanics contract supplies them;
- built, under construction, proposed, alternative, invalid, blocked,
  unresolved and unavailable states use more than colour alone;
- selecting a potential site explains why it is available or blocked and what
  would change if used;
- a spatial selection emits a planning intent; it does not mutate a plan;
- only an explicit confirmed action may ask CPE/Colony Planner to add or replace
  a placement; and
- the user can compare alternatives and return to the same Galaxy camera and
  selected system.

### Research references

- [Full V2 Map review and V3 migration disposition](v2-map-review-for-v3-babylon.md)
- [Exhaustive ED starmap research](../research/2026-08-12-ed-starmap-research-report.md)
- [ED open-source, data and asset ecosystem](../research/2026-08-12-elite-dangerous-ecosystem-research-report.md)
- [Elite Galaxy Map image reference](https://interfaceingame.com/screenshots/elite-dangerous-galaxy-map/)
- [Official Trailblazers/System Colonisation overview](https://www.elitedangerous.com/zh-Hans/%E6%9B%B4%E6%96%B0%E8%AF%B4%E6%98%8E/4-1-0-0)
- [Odyssey System Map discussion and screenshot](https://forums.frontier.co.uk/threads/confusing-system-map.576995/)
- [System Colonisation Architect screenshot/discussion](https://forums.frontier.co.uk/threads/elite-dangerous-system-colonisation-beta-details-feedback.634055/page-71)
- [Babylon Large World Rendering](https://github.com/BabylonJS/Documentation/blob/master/content/features/featuresDeepDive/scene/large_world.md)
- [Babylon WebGPU support](https://github.com/BabylonJS/Documentation/blob/master/content/setup/support/webGPU.md)
- [Babylon instances and custom instance buffers](https://github.com/BabylonJS/Documentation/blob/master/content/features/featuresDeepDive/mesh/copies/instances.md)
- [Babylon WGSL shader guidance](https://github.com/BabylonJS/Documentation/blob/master/content/setup/support/webGPU/webGPUWGSL.md)

### V2 migration disposition

The [full V2 review](v2-map-review-for-v3-babylon.md) is a migration input, not
an endorsement of the retired renderer. It found reusable behaviours alongside
release-blocking data and accessibility defects.

- **Preserve as behaviour:** deliberate Galaxy/results/reference/top-down
  presets, smooth camera restoration, LOD hysteresis, guaranteed targets,
  overlap-chooser intent, bounded buffers, reduced-motion/shortcut safeguards,
  context-loss UX, deterministic region derivation and receipted evidence.
- **Redesign behind V3 contracts:** region interaction and label layout,
  generation-pinned density/star streaming, camera state, central picking,
  routes, domain overlays, application hand-offs and accessible target
  projection.
- **Do not port:** the procedural `VolumetricGalaxy` factual presentation,
  the hard-disabled real heatmap path, score-as-density styling, numeric or
  synthetic `id64`, coordinate-first capped viewport selection, false route
  bridges, exact-coordinate-only overlaps, application-state frame polling,
  runtime imports from artifact directories or non-spatial “map layers.”

V3 acceptance tests must inspect the actual Babylon render product and accepted
scene revision. A fetched buffer, enabled toggle or adapter count is not proof
that the corresponding factual layer is visible.

## V2-first continuous improvement protocol

Every map workstream starts by asking **“How did V2 do this?”** and then **“How
will V3 do it better?”** This applies to product behaviour, data, visuals,
accessibility, performance, failure handling, tests and delivery evidence—not
only to renderer code.

This is a comparison discipline, not a parity trap. V3 may deliberately differ
from V2, but it may not lose a useful behaviour accidentally or repeat a known
defect without an explicit reviewed decision.

### Required comparison packet

Before implementation begins, each bounded work item records:

1. **V2 baseline:** source paths, owning component/API, screenshots or live
   observation, data semantics, user-visible behaviour and known flags.
2. **V2 evidence quality:** what its tests and receipts prove, what they mock or
   infer, and any gap between metadata and the rendered product.
3. **V2 strengths:** behaviours, limits or safeguards users would notice if V3
   lost them.
4. **V2 defects/debt:** truth, UX, accessibility, performance, resilience,
   ownership and maintainability failures.
5. **V3 decision:** preserve, improve, replace or retire, with the reason and
   affected authority/contract.
6. **Measurable improvement:** scenario, fixture or generation, target metric or
   observable outcome, supported backends/viewports and failure expectation.
7. **Comparative evidence:** V2 and V3 captured under equivalent data, camera,
   viewport/DPR and interaction state wherever equivalence is possible.
8. **Disposition:** accepted improvement, intentional difference with rationale,
   or unresolved regression that blocks the work item.

The packet belongs with the work item's durable evidence and names the reviewed
V2 commit/file state. A verbal claim that Babylon is “better” is not acceptance.

If V2 never implemented the capability, record **V2: absent**. System Map and
Architect work then use the nearest relevant V2 behaviour—selection, camera,
details, hand-off, accessibility, failure and evidence patterns—plus current
product authority and deterministic fixtures. Absence is a baseline, not
permission to skip comparison or invent mechanics.

### Comparison ledger by area

| Area                     | Establish from V2                                                                       | V3 improvement to prove                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Scene/runtime ownership  | R3F lifecycle, parallel overlay props, artifact imports and remount behaviour           | One maintained neutral contract, long-lived Babylon runtime, atomic accepted revisions and no domain/artifact leakage                       |
| Identity and coordinates | Numeric `id64`, axis mapping and synthetic waypoint IDs                                 | Lossless branded `Id64`, typed non-system identities, exact Elite coordinates and tested Babylon handedness/precision                       |
| Catalogue density        | Rated-system API, disabled `DensitySwirl` and procedural visible replacement            | Reconciled real-coordinate pyramid, honest coverage, rendered-state proof and useful ambient-off Galaxy                                     |
| Regions                  | 42-region source, build output, lookup, lines, labels and licence receipt               | Same pinned truth plus exact validation, fill/hover/select/query, LOD agreement and superior label hierarchy                                |
| Camera and navigation    | Galaxy/results/reference/top-down presets, pan/zoom/pitch, clamps and restoration       | Preserve continuity while adding bounded bearing/orbit, clearer controls, shared state machine and exact Back/focus restoration             |
| Streaming and LOD        | 250 ms settle, hysteresis, caps, coordinate-first SQL and truncation fallback           | Revisioned generation packets, importance-aware deterministic selection, guaranteed targets and explicit complete/truncated/too-wide states |
| Stars and aggregates     | Point buffers, spectral colours, brightness/score coupling and fixed cluster hulls      | Physical appearance where supported, honest analytical emphasis, versioned cluster ownership and measured GPU budgets                       |
| Labels and safe areas    | Region/Finder collisions, clipping corrections and guaranteed labels                    | Deterministic priority/occlusion layout, all HUD safe areas, stable focus and measurable collision budgets                                  |
| Picking and overlap      | Three raycast, exact-coordinate chooser and display-index mapping                       | Central Babylon picking, screen-space candidate grouping, stable target identity, latency budget and DOM parity                             |
| Routes and range         | Direction/progress visuals, filtered missing waypoints and synthetic IDs                | Preserve useful cues, expose gaps/unresolved legs, canonical progress and no fabricated identity                                            |
| Finder and hand-offs     | Results/reference selection plus partially integrated typed commands                    | One command boundary with composed-app Explore→Inspect/Compare/Plan→return evidence                                                         |
| Domain overlays          | Exploration, trail, completeness, Powerplay, cluster and timeline prototypes            | Versioned owner contributions with truth class, freshness, bounds, legend, accessible targets and honest unavailable states                 |
| Visual language          | Orange boundary/glow dominance, selected/reference cues and procedural backdrop         | Data-first hierarchy, distinct truth classes, restrained effects, licensed ambient separation and side-by-side visual acceptance            |
| Accessibility            | Canvas instructions, shortcut protections, overlap buttons and missing target traversal | Complete keyboard/touch/screen-reader task equivalence, virtualized target list/tree, focus continuity and announcements                    |
| Performance              | Demand loop, typed/bounded buffers and Stage 26 single-device receipts                  | Phase-level CPU/GPU/pick/resource metrics, integrated/discrete hardware, WebGPU/WebGL2 and repeat-transition stability                      |
| Resilience               | Resize/DPR, stale guards, error boundary and WebGL context recovery                     | Equivalent or better explicit recovery across application data, Babylon WebGPU/WebGL2 and useful DOM degradation                            |
| Tests and evidence       | Broad unit suites, mocked renderer blind spot, screenshots and historical receipts      | Actual render-product assertions, immutable code/data identity, ambient-off/empty-data tests and reproducible comparative receipts          |
| Fallback                 | Simple 2-D canvas with limited depth, regions and access                                | Useful semantic DOM/results fallback and WebGL2 feature tier without factual or workflow loss                                               |
| System Map               | Absent                                                                                  | New truthful semantic orrery that reuses improved identity, selection, camera, access, resilience and evidence patterns                     |
| Colonisation/Architect   | Absent                                                                                  | New plan-aware System contribution and explicit intent flow with no renderer-owned mechanics or silent mutation                             |

### Definition of “better”

An improvement must satisfy at least one explicit dimension without silently
regressing another:

- greater data truth, provenance or explanatory clarity;
- a task users can complete more quickly, reliably or continuously;
- stronger keyboard, touch or assistive-technology equivalence;
- clearer visual hierarchy or lower measured label/selection ambiguity;
- lower or more stable CPU, GPU, memory, payload or pick cost;
- better stale/error/truncation/device-loss recovery;
- cleaner ownership, identity or lifecycle boundaries; or
- stronger, reproducible evidence that exercises what the user actually sees.

Where V3 intentionally trades one dimension for another, the packet records the
trade-off and approver. “Different engine” and “looks newer” are never sufficient
justification.

## Durable ownership and architecture

```text
Svelte/SvelteKit routes, panels, commands, accessibility and domain state
                                  |
 Finder / History / Routes / Powerplay / Colonisation / CPE / CRE adapters
                                  |
        versioned renderer-neutral SpatialSceneContract contributions
                                  |
            long-lived MapRuntime and central PickingService
                       /                         \
                  GalaxyScene                SystemScene
                       \                         /
                     BabylonSpatialRuntime
                                  |
         LayerManager + GPU resources + camera + projection + telemetry
```

The rules are:

- only the Babylon adapter/runtime imports `@babylonjs/*`;
- domain code never constructs Babylon meshes, materials, cameras or vectors;
- canonical CPU coordinates remain exact Elite light-years;
- Babylon presentation state never becomes canonical product truth;
- renderer events express observations or intent and never mutate a plan,
  journal, rating, cluster or mechanics model directly;
- revisioned scene/contribution commands are idempotent where possible;
- the runtime retains enough renderer-neutral CPU state to rebuild after
  backend/context/device loss; and
- Galaxy and System scenes share identity, contribution, selection, telemetry,
  recovery and accessibility infrastructure without pretending they use the
  same scale or layout rules.

## Using Babylon.js to the maximum justified extent

“Use Babylon to the max” means deliberately exploiting its modern engine,
buffer, shader, instancing, material, post-process, picking, lifecycle and
instrumentation capabilities wherever measurements show a product benefit. It
does not mean putting scoring, planning or data aggregation into the renderer.

### Engine and precision

- Stay on a pinned Babylon 9-class modular package set and use exact ES-module
  imports so unused facilities remain tree-shakeable.
- Attempt `WebGPUEngine` first and initialize it asynchronously before any scene
  or GPU resource is created.
- Select WebGL2 fallback before scene creation. A failed WebGPU initialization
  receives a clean canvas and fresh resource build.
- Enable and verify Babylon 9 Large World Rendering/high-precision matrices and
  floating origin for the Galaxy scene. Do not introduce an application
  `worldScale` that changes coordinate truth.
- Use right/left-handed transforms only behind one tested adapter. The public
  contract always uses Elite `x/y/z` light years.
- Maintain separate Galaxy and System camera controllers behind the neutral
  `CameraState` contracts rather than leaking `ArcRotateCamera` or `FreeCamera`.

### Star and aggregate rendering

- Replace sphere-per-result presentation with a data-oriented star layer using
  camera-facing instanced quads/billboards or an equivalent custom vertex and
  instance-buffer path.
- Benchmark thin instances with custom per-instance buffers against a compact
  custom star buffer. Choose by measured memory, upload time, draw calls,
  picking and frame time at every required tier.
- Store only presentation attributes needed by the GPU: camera-relative
  position, apparent size/salience, colour, alpha, representation flags and a
  stable pick index. Keep names, provenance and explanations in CPU/domain
  structures.
- Use a dedicated star material. Prefer native WGSL for the WebGPU path to avoid
  runtime GLSL conversion overhead, with an explicitly equivalent WebGL2 shader
  path.
- Use physically informed temperature/blackbody colour when trustworthy source
  temperature exists, then spectral-class approximation, then a clearly defined
  unknown fallback.
- Use absolute magnitude/luminosity when available for salience. Ratings,
  population and Finder rank may affect analytical emphasis only through an
  explicit contribution; they do not masquerade as stellar brightness.
- Keep the brightest/notable and guaranteed user targets visible through LOD
  transitions so semantic anchors do not blink out.

### GPU and WebGPU enhancements

- Treat compute shaders as a profiled WebGPU enhancement for view-frustum/LOD
  selection, compacting visible indices, density transforms or GPU picking—not
  as a required source of domain results.
- Provide deterministic CPU/WebGL2 fallbacks with the same semantic output and
  explicit lower budgets where necessary.
- Evaluate GPU ID-buffer picking for dense layers against Babylon thin-instance
  picking and a CPU spatial index plus GPU confirmation. One central
  `PickingService` publishes stable targets regardless of technique.
- Use Babylon render targets and asynchronous WebGPU readback correctly; never
  block the main thread waiting for a pick result.
- Evaluate snapshot rendering/frozen static resources for stable passes only.
  Do not freeze dynamic camera, selection or streaming state incorrectly.
- Use transferable typed arrays and Web Workers for decoding/normalizing large
  packets only after profiling identifies main-thread pressure.

### Materials, lighting and visual finish

- Use Node Material or dedicated shaders for reusable, inspectable materials
  where it improves maintainability; use direct WGSL/GLSL where data density or
  exact control requires it.
- Use restrained bloom/glow for emissive stars, route focus and selection. Glow
  is emphasis, never an unreadable wash or the only status channel.
- Use high-dynamic-range colour handling and tone mapping only after cross-
  backend visual calibration.
- Keep ambient Milky Way artwork, dust, nebulae and background stars explicitly
  `AMBIENT`; they are never density evidence, selectable systems or inputs to
  mechanics. Known-system density is the separate data-derived layer defined by
  the truth gate above.
- In System Map, use procedurally composed/PBR materials for stars, planet
  classes, atmospheres and rings only as presentation of known properties.
  Unknown inputs get honest generic visuals.
- Consider Babylon volumetric lighting or atmosphere facilities for a selected
  star/body hero view only after accessibility, legibility and performance
  gates; never run cinematic effects across the analytical overview by default.
- Apply effects through quality tiers and `prefers-reduced-motion`; every effect
  must be independently disableable for diagnostics.

### Layers, labels and UI

- A `LayerManager` owns explicit layer resources, budgets, visibility,
  contribution revision, dirty state and disposal.
- Labels remain Svelte/DOM overlays projected from Babylon coordinates. A
  prioritized collision/hysteresis service guarantees selected, current,
  reference and explicit highlighted labels.
- The canvas does not own menus, tooltips, details panels, legends, commands,
  focus order or screen-reader text.
- Projection and overlap disambiguation remain renderer services, while target
  identity and permitted actions remain domain decisions.

### Visual quality and wow gate

Truth is the foundation, not an excuse for a flat engineering visual. The
default Galaxy and System views must feel premium, deep and immediately
compelling before analytical overlays are enabled.

- The wide Galaxy view must read as a luminous, volumetric stellar structure
  built from real density, with convincing depth falloff, a restrained dynamic
  range and a clear focal hierarchy. Debug spheres, uniformly bright blobs and
  an opaque region-colour map are not shippable art direction.
- The supplied BSSA-style Milky Way reference is the target for the factual
  heatmap's visual read: cool sparse outskirts, warm cream/white
  concentrations, irregular real-data structure and visible dark gaps. It is a
  look reference, never a density texture, mask or substitute for catalogue
  cells.
- Factual cells and real systems may receive presentation halos, bloom and
  exposure treatment, but every luminous signal must retain its source-derived
  position and must disappear when its factual layer is disabled. Ambient dust
  or star fields remain separately toggleable and separately identified.
- Regions use subtle cartographic glass/fill at rest, a precise boundary and a
  premium hover/selection response. They support orientation without painting
  over the stellar subject.
- Camera motion, semantic-scale transitions and Galaxy ↔ System entry must be
  composed deliberately, with stable focus, parallax and continuity rather than
  abrupt scene replacement. Reduced-motion mode preserves spatial clarity
  without cinematic travel.
- The System Map is a hero-quality semantic orrery: physically informed light,
  material, atmosphere and ring cues where the data supports them, honest
  generic treatment where it does not, and construction overlays that remain
  analytical rather than game-like decoration.
- Visual acceptance requires paired 1280×720 and 1440×900 screenshots plus live
  motion review on WebGPU and WebGL2. Reviewers must be able to identify the
  factual density, current selection, region context and available action at a
  glance. “Technically rendered” is not acceptance.
- Elite Dangerous references guide interaction quality and spatial drama, not
  trade dress. ED-Finder's colour, typography, materials, motion and composition
  remain original.

### Render cadence and resource lifetime

- Render on demand while stable. Camera motion, transitions, streaming,
  selection, hover/picking and animated layers schedule frames; idle scenes stop
  continuous work.
- Reuse buffers and update subranges rather than rebuilding scenes or full GPU
  arrays for every Svelte update.
- Explicitly dispose observers, materials, textures, render targets, buffers,
  workers and scene resources.
- Report backend, visible targets, CPU/GPU frame distributions where supported,
  draw calls, resource counts, buffer bytes, upload/stream latency, pick latency,
  truncation and recovery outcome.

## Galaxy experience

### Canonical workspace

Provide a shareable Galaxy workspace route while allowing the same long-lived
spatial context to participate in Explore and other journey surfaces. Route
changes must not accidentally reset the map.

The workspace has four coordinated areas:

1. the spatial canvas;
2. a query/layer/preset surface;
3. a selection/details/action surface; and
4. an accessible target/results representation.

The named presets are starting configurations:
`REALISTIC`, `FINDER`, `COLONISATION`, `POWERPLAY`, `EXPLORATION`, and `ROUTES`.
Changing preset patches contributions and presentation. It does not create a
different map or discard camera/selection.

### Semantic scales

| Scale        | Base presentation                                                                         | Data budget and guarantees                                                            |
| ------------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Wide         | Ambient backdrop, real catalogue-density cells, regions, major references, route overview | Cell/aggregate budget; current, selected, reference and route endpoints guaranteed    |
| Regional     | Real/notable systems, region context, prioritized labels and domain summaries             | Bounded cell plus star budget; brightest/notable and user targets guaranteed          |
| Local        | Real systems, ranges, relationships, infrastructure and spatial query results             | Bounded star/edge/label budgets; selection and active contribution members guaranteed |
| System entry | Explicit transition affordance on a real system                                           | No accidental transition caused by zoom; retain Galaxy return state                   |

Entry and exit thresholds use hysteresis. Data and presentation cross-fade only
when both sides are ready; a failed finer request leaves the coarser truthful
layer in place with a visible state explanation.

### Base layers

- independently toggleable ambient Milky Way/dust context;
- galactic plane, axes/reference grid and scale indication;
- all 42 named regions with licensed/provenanced geometry;
- real, generation-pinned catalogue-density cells;
- real/notable systems with physical star appearance where supported;
- current, selected and reference system treatments;
- labels; and
- route/range primitives supplied by their owning domains.

### Core interactions

- pan, orbit, restrained tilt and zoom with mouse, keyboard and touch;
- top-down preset and restore-previous-camera;
- search and fly-to with cancellation;
- focus current, selected or reference target;
- click/tap selection, keyboard selection and overlap chooser;
- hover preview that never changes canonical selection;
- multi-select through stable identities;
- set reference;
- Find Around Here / Systems Within… with explicit bounded radius;
- Open System / Enter System;
- compare, plot route, show cluster and Plan From Here; and
- URL/share restoration of meaningful route, target, camera/preset and query
  state without serializing transient GPU details.

## Galaxy data and streaming

Migration `004_v3_search_spatial_clusters.sql` defines the generation-scoped
search projection, multi-resolution spatial cells and independent cluster
products. Schema existence is not publication evidence. Builders, validators,
stable application functions/endpoints and production receipts are separate
deliverables.

### Required application boundary

Add stable `v3_app`-backed endpoints/functions for:

- semantic-scale map cells by frustum/bounds and target budget;
- real/notable systems by bounded 3-D viewport and target budget;
- exact target lookup/fly-to;
- named regions and region summary;
- published cluster metadata/membership by owner and run identity; and
- selected-system summary required by the spatial workspace.

Every response identifies the canonical/derived generation and relevant
pyramid/cluster/rules versions, plus bounds, returned count, target budget,
truncation, continuation/refinement information and freshness/provenance. Cell
responses also expose the eligible source-system count and coverage timestamp so
the client can label the density honestly and validators can reconcile totals.

### Pyramid and star selection

- Configure hierarchical power-of-two 3-D cells from measured workloads; do
  not freeze a cell size through intuition.
- Exact `x/y/z` stays canonical truth. A cell key is an aggregation/LOD address,
  never a system position.
- A populated cell exists only because one or more eligible real system records
  occupy it. There is no procedural fallback when catalogue coverage is sparse
  or a request returns no data.
- Choose level from semantic scale, visible volume, screen density and target
  budget.
- Cell summaries carry factual counters and explicitly versioned analytical
  summaries. They never become canonical system truth.
- Star selection is deterministic and importance-aware. Preserve bright/rare,
  populated, current, selected, reference, route, Finder, personal-history and
  explicitly highlighted systems according to documented priority lanes.
- The server communicates which priority guarantees were applied. The client
  never claims a complete viewport when the result is sampled or truncated.
- Requests are cancellable and stale revisions cannot overwrite a newer camera
  state.

### Clusters

Cluster membership is published by an owning domain and algorithm version. The
map renders summaries, members and hulls; it never discovers a cluster from
screen proximity. Cluster ownership must be settled before a cluster layer is a
required production-map capability.

## System Map

### Scene and identity

`SystemScene` is a deliberate scene-scale transition inside the same spatial
platform. The canonical body identity is a system-scoped
`BodyRef { systemId64, bodyId }`. Display name is never an identity and a local
database primary key must not be reinterpreted as Journal `BodyID` without
source proof.

Use the existing S0–S5 fidelity ladder property-by-property:

- S0: system identity/coordinates;
- S1: stellar members/properties;
- S2: body hierarchy;
- S3: orbital/ring detail;
- S4: attached infrastructure; and
- S5: CRE Digital Twin/evidence/history/planning contributions.

A system can support S4 overall while an individual orbit, ring or station-body
association remains unknown, conflicted or schematic.

### Semantic orrery layout

- Resolve and display verified parent/child hierarchy where available.
- Where hierarchy is unavailable, show an explicit structured list or
  unresolved group; never invent a parent from name/distance heuristics.
- Preserve factual physical radius, mass, distance and orbital elements in
  details.
- Compute separate deterministic display radius and semantic spacing for
  legibility.
- Draw orbital paths only from the supplied property set and label incomplete
  or schematic geometry.
- Never animate a claimed present-time orbital phase without a trustworthy
  epoch and complete required elements.
- Support single, binary and multiple stars, barycentres, moon-rich and
  ring-rich systems through deterministic fixtures before real-data claims.
- Keep bodies selectable at every supported scale with prioritized labels and a
  keyboard/tree equivalent.
- Use smooth, cancellable camera transitions between whole-system, star group,
  body, rings and infrastructure focus.

### System layers

- stellar/body/ring base truth;
- infrastructure and confirmed/unresolved attachment lanes;
- personal exploration scan/map/biological/Codex state;
- current colony state;
- colonisation candidates and constraints;
- selected CPE plan, alternatives and blockers; and
- CRE Digital Twin evidence/state/history when a reviewed interchange contract
  exists.

## Colonisation and Architect mode

Architect mode is an explicit System Map preset/workspace, not a separate map.
It spatially assists planning while Colony Planner/CPE remains mechanics and
persistence owner.

### Information model

Each rendered colonisation target carries:

- stable system/body/facility/site identity where available;
- owner and representation class;
- existing, under-construction, planned, alternative, rejected, blocked,
  conflicted, unresolved or unavailable lifecycle;
- orbital/surface lane and association status;
- capacity/slot facts only from the owning mechanics contract;
- relevant suitability, prerequisites, dependencies and effects as explanatory
  domain output;
- evidence/provenance/rules version; and
- a text explanation equivalent to the visual treatment.

### Interaction contract

1. The user selects a star, body, ring/lane, existing facility or candidate
   site.
2. The map emits a renderer-neutral target selection.
3. The colonisation/CPE adapter returns allowed actions, constraints, effects
   and explanations.
4. The map previews an option as `PLANNED` without changing the canonical plan.
5. The user compares the option with alternatives and existing/planned state.
6. An explicit **Add to plan**, **Replace option**, or **Open in Colony
   Planner** command crosses into the owning planning workflow.
7. The owner validates and persists—or rejects—the command and returns a new
   revisioned contribution.

No drag, click, hover, camera movement or layer toggle silently changes a plan.

### Architect visual language

- built/current: solid factual treatment;
- construction in progress: factual structure plus progress/state treatment;
- planned: distinct blueprint/hologram treatment;
- valid candidate: interactive but visually subordinate until selected;
- invalid/blocked: visible on request with reason, never merely red;
- unresolved association: detached/listed or explicitly schematic;
- conflict: warning pattern and details, never auto-resolved visually; and
- unavailable property/capability: absent or labelled unavailable, never shown
  as zero capacity.

Architect mode must answer, without requiring an external spreadsheet:

- what exists and where it is associated;
- what is under construction;
- what is proposed in the active plan;
- which alternatives are available;
- why a site/facility is valid or blocked;
- which dependencies or construction points affect it;
- which effects and trade-offs the owning model predicts; and
- what explicit action will change the plan.

## State, routing and continuity

Maintain application-owned spatial state for:

- Galaxy camera and semantic scale;
- System camera per selected system where useful;
- selected and reference targets;
- active preset and layer visibility;
- active Finder/query scope;
- active route/cluster/plan contribution identities;
- return transition state; and
- last successfully applied scene/contribution revisions.

Persist only stable, versioned, user-meaningful state. GPU handles, Babylon
objects, transient hover, frame caches and backend-specific details are never
stored. Cold links fail closed when an identity/version is no longer valid.

## Accessibility

- Every pickable spatial target appears in a synchronized semantic list/tree or
  result surface.
- All commands have keyboard controls and visible focus.
- Overlapping targets open an accessible chooser rather than cycling invisibly.
- Target details and status changes use appropriate headings/live regions,
  without announcing continuous camera motion.
- Colour is never the only carrier of selection, validity, lifecycle,
  representation or confidence.
- Reduced motion makes fly-to and Galaxy/System transitions short,
  deterministic and interruptible; nonessential ambient animation stops.
- Canvas failure leaves search, selection, details and planning paths usable.

## Performance and quality budgets

Budgets are fixed before a milestone is judged, then recorded per backend and
hardware class. Initial targets are deliberately demanding and may be revised
only with retained evidence and an explicit decision.

### Required datasets

- single-star and small-result functional fixtures;
- 20k and 40k production-like Galaxy scenes;
- 100k stress scene;
- 500k torture scene;
- 1m diagnostic/extreme scene;
- dense-core, sparse-rim and mixed-depth distributions;
- binary, multiple-star, moon-rich, ring-rich, incomplete and conflicted System
  scenes; and
- colonised, under-construction, planned, alternative and blocked Architect
  scenes.

### Initial interactive targets

- 20k/40k WebGPU navigation: 60 fps target on the agreed representative
  discrete-GPU machine, with frame p95 at or below 20 ms after warm-up.
- Representative integrated GPU: no sustained interaction below 30 fps at the
  declared supported quality tier.
- WebGL2: explicit tier/budget with no semantic loss, even when density or
  effects are reduced.
- pointer-to-visible-selection p95 at or below 100 ms;
- keyboard selection and DOM detail response within one animation frame when
  data is local;
- no unbounded main-thread task during normal camera movement;
- no scene recreation for ordinary selection, layer visibility or camera
  changes;
- stable memory across repeated Galaxy ↔ System transitions and route remounts;
  and
- device/context-loss recovery produces an explicit state and either rebuilds
  successfully or presents a usable fallback.

The 500k and 1m tiers diagnose scaling and inform future budgets; they are not a
promise that every supported device renders every star individually.

## Validation and evidence

### Unit and contract tests

- renderer-neutral import boundary;
- 42-region source hash, exact ID/name set, RLE decode, coordinate transform,
  lookup fixtures and derived-geometry determinism;
- catalogue-density cell totals reconciled to eligible generation records,
  deterministic coordinate-to-cell assignment and an enforced ban on
  procedural/random inputs to the factual layer;
- coordinate/handedness and large-world precision;
- camera reducer, hysteresis and exact restoration;
- layer revision/idempotency and resource disposal;
- LOD/priority guarantees and deterministic sampling;
- bounded/truncated/stale/error responses;
- BodyRef/facility identity and unresolved associations;
- semantic layout, schematic truth and physical/display separation;
- Architect intent versus explicit plan mutation; and
- accessibility projection and overlap identity parity.

### Product E2E / Visual Acceptance

Use the normal `apps/web` application and approved production-like fixtures/API
for:

- search → map → selection → Inspect → return;
- wide → regional → local → System → Galaxy continuity;
- top-down and tilted Galaxy views;
- all 42 regions, including label/fill/lookup agreement and region transitions;
- real dense and sparse catalogue LOD transitions, with disclosed coverage;
- ambient-off Galaxy acceptance proving no artwork is posing as density;
- mouse and keyboard selection/overlap;
- System body/ring/infrastructure selection;
- Architect option preview and explicit plan hand-off;
- resize/DPR/remount;
- Chrome and Firefox; and
- accessibility checks plus approved screenshots at 1280×720 and 1440×900.

### Review Lab

Use the same Svelte/Babylon product runtime with isolated synthetic data for:

- backend initialization failure and WebGPU → WebGL2 fallback;
- empty/stale/truncated/error packets;
- empty catalogue-density packets without a generated replacement;
- delayed/out-of-order revisions;
- high density and overlap;
- injected resource loss/recovery;
- incomplete System data, unknown rings, missing hierarchy and unresolved
  infrastructure;
- planned versus built/conflicted states; and
- deterministic visual/performance evidence.

### Physical GPU lane

Retain receipted WebGPU and WebGL2 results on representative Windows discrete
and integrated GPUs. Record browser/OS/adapter, capabilities, quality tier,
viewport/DPR, cold/warm startup, frame distributions, long frames, draw calls,
visible count, resources, buffer bytes, upload time, pick latency and supported
GPU timing provenance. Cloud/software rendering is never labelled physical GPU
evidence.

### Implementation checkpoint 01 — truthful density and region foundation

The first fixture implementation slice is recorded in the
[density and regions comparison packet](evidence/v3-map/implementation-slice-01-density-regions.md).
It establishes the strict `catalogue-density` contract, no-substitute empty-data
behaviour, exact audited 42-region derivation, actual Babylon render-product
receipts and a non-product Review Lab. It does **not** complete M2: production
density, region labels, camera navigation, semantic LOD, complete accessibility,
performance and physical-GPU acceptance remain open.

### Implementation checkpoint 02 — exact region interaction

The next fixture slice is recorded in the
[exact region interaction comparison packet](evidence/v3-map/implementation-slice-02-region-interaction.md).
It turns the pinned RLE truth into 42 exact Babylon fill meshes, requires
mesh/CPU-lookup agreement for region hits, adds throttled hover and selection,
provides a native 42-region semantic chooser, and patches selection-only scene
revisions without rebuilding Galaxy geometry. It closes the fill/hover/select/
query kernel, not projected labels, topology-preserving LOD, full accessibility,
performance or product-route acceptance.

### Implementation checkpoint 03 — truthful visual foundation

The visual kernel is recorded in the
[visual foundation comparison packet](evidence/v3-map/implementation-slice-03-visual-foundation.md).
It adds ACES tone mapping, controlled exposure/contrast, dithering, a dark
vignette and focused Babylon glow while restricting luminous treatment to
factual density and system geometry. Region fills remain subordinate
cartographic context. This is the first high-end presentation baseline, not the
finished Galaxy: production density, scale-aware volume rendering, camera
motion, labels, both renderer lanes, physical-GPU performance and the System
Map visual language remain open.

### Implementation checkpoint 04 — navigation and soft density

The [navigation and density comparison packet](evidence/v3-map/implementation-slice-04-navigation-density.md)
records a renderer-neutral camera with pan/orbit/zoom, exact top-down orientation,
smooth cancellable travel and reduced-motion handling. Camera commands update
the existing Babylon scene. Source-centred soft density quads replace the
diagnostic density spheres; all 42 regions can be inspected in an overview and
focused individually. The local diagnostics command is isolated from Product
E2E and the guarded Review Lab. Projected labels, real density refinement,
precision/performance, System Map and product acceptance remain open.

### Implementation checkpoint 05 — projected labels

The [projected labels comparison packet](evidence/v3-map/implementation-slice-05-projected-labels.md)
adds a shared renderer-neutral projection and collision solver for source-derived
region anchors and accepted Finder systems. It gives selected, hovered and
current targets deterministic placement priority, applies safe areas and a
system-label budget, and renders crisp non-interactive labels above the Babylon
scene. Region priority never controls visibility: all 42 exact names appear in
the whole-Galaxy atlas, while every in-frame region remains named at closer
scales even if collision fallback must tolerate overlap. A dedicated top-down
plane fit makes the region overview use the canvas effectively without changing
the general 3-D fit. Overlap selection, full target traversal, unified semantic
LOD, production data/performance and visual acceptance remain open.

### Implementation checkpoint 06 — region hover and stellar heatmap

The [region-hover and stellar-heatmap comparison packet](evidence/v3-map/implementation-slice-06-region-hover-stellar-heatmap.md)
adds exact-fill cyan hover with a distinct amber selection state and upgrades
the real-density presentation to the count-driven `stellar-heatmap-v2` palette
and compact core/halo kernel. It also corrects the production dependency: the
spatial pyramid is built from every coordinate row in the canonical systems
catalogue and can proceed while Ratings V4 finishes. The legacy rated-score
heatmap is not a valid density source. Full-catalogue packet integration and
production-scale visual acceptance remain open.

### Implementation checkpoint 07 — live density refresh

The [live-density refresh comparison packet](evidence/v3-map/implementation-slice-07-live-density-refresh.md)
implements the neutral `PATCH_CONTRIBUTION` path for a newer accepted
catalogue-density generation. It replaces and disposes only the owned density
GPU resources, rejects stale revisions, publishes an explicit contribution
receipt and preserves the live Babylon scene, camera, Finder stars, regions and
selection. A deterministic 34→40 coordinate browser scenario proves the update
on WebGPU and WebGL2 without implying that production spatial transport is
already connected.

### Implementation checkpoint 08 — product regions and stable selection

The [product-region and stable-selection packet](evidence/v3-map/implementation-slice-08-product-regions-selection.md)
moves the audited 42-region experience into the normal Explore workspace. It
adds a complete keyboard region selector, whole-Galaxy and selected-region
views, exact hover/selection status and explicit fail-closed resource loading.
Stable Finder/region contribution identities also let both system and region
selection update the existing Babylon scene without resetting camera or
rebuilding unrelated GPU resources. The accompanying
[Galaxy RC1 readiness table](evidence/v3-map/galaxy-rc1-readiness.md) separates
the assembled code candidate from the still-required Product E2E, owner visual,
bundle, physical-GPU and production-density gates.

### Implementation checkpoint 09 — adaptive LY grid and exact star zoom

The [zoom/grid comparison packet](evidence/v3-map/implementation-slice-09-exact-star-grid-zoom.md)
translates the tutorial benchmark into an adaptive Babylon reference grid and a
smaller, screen-readable individual-star treatment. The grid uses deterministic
1/2/5 light-year intervals on Galactic `Y=0`, fades towards its edge and rebuilds
only when its visible geometry changes. Finder star matrices retain exact source
coordinates through every camera change; only the non-factual marker radius is
scaled. The UI discloses the active grid interval. Production catalogue-star
streaming and generation-matched aggregate-to-star cross-fade remain M3/M4
release gates.

### Implementation checkpoint 10 — catalogue stars, picking and travel history

The [catalogue-star, picking and travel-history packet](evidence/v3-map/implementation-slice-10-stars-picking-history.md)
connects Explore to bounded exact-coordinate viewport packets, assigns the
owner-supplied stellar families distinct tested presentation, opens a native
facts card from central Babylon picking and adds a separate journal-only
Commander History heat layer. Star budgets descend as the camera closes in;
no synthetic stars or visits are introduced.

### Implementation checkpoint 11 — complete attributed nebula inventory

The [nebula-inventory packet](evidence/v3-map/implementation-slice-11-nebulae.md)
adds a deterministic 5,842-record asset from EDAstro Mapcharts' dedicated
Nebulae Coordinates CSV, with stable source identity, exact catalogue
coordinates, source classification, region ID, a default-on map toggle and
visible EDAstro / CMDR Orvidius attribution. Cloud extent remains explicitly
schematic. The source page and raw CSV are linked from the product.
The refreshed [Mapcharts data-source inventory](../colonisation-redesign/edastro-data-source-inventory.md)
ranks the combined POI feed as the next small map enrichment and the global
Codex feed as a separate server-side follow-up.

### Implementation checkpoint 12 — interactive S1 System Map

The [3-D System Map packet](evidence/v3-map/implementation-slice-12-system-map.md)
extends the shared Babylon runtime with lit body spheres, known rings,
schematic orbit geometry, orbit/zoom controls, body picking and an accessible
facts/list equivalent. Catalogue body facts retain provenance, while layout,
phase and display scale are clearly disclosed as deterministic schematic
presentation. Local WebGPU and forced-WebGL2 diagnostics now cover both the
Galaxy and System products.

## Delivery sequence

The work packages are ordered so visual/interaction development can proceed on
fixtures without racing Ratings V4 database publication.

### M0 — Plan, baselines and contract closure

**Can start now.**

- adopt this plan and reconcile stale map/Finder documents that still say
  migration `004` is unwritten;
- adopt the V2 review's preserve/redesign/retire register and inventory reusable
  renderer-neutral behaviour and static Stage 26 visual/evidence fixtures;
- create the per-workstream V2→V3 comparison ledger and evidence-packet template;
- create the deterministic Galaxy, System and Architect fixture catalogue;
- pin the audited 42-region source/derived-resource contract and the
  catalogue-density reconciliation contract;
- define benchmark machines, quality tiers and evidence schema;
- define the canonical Galaxy workspace route/state envelope;
- specify application-facing map response contracts and version metadata;
- reserve System/Architect contribution types without claiming unavailable real
  data; and
- record visual principles/mood boards from licensed or reference-only sources.

**Exit:** current docs agree; fixtures and measurable acceptance gates exist,
including the 42/42 region and non-procedural density gates; no production
dependency is implied and no retired V2 renderer/data contract is on the port
path. Every scheduled map workstream has a V2 baseline or an explicit `absent`
entry plus a measurable V3 improvement target.

### M1 — Production-grade Babylon runtime

**Can start now against fixtures.**

- enable and prove Large World Rendering;
- replace diagnostic camera placement with tested Galaxy and System camera
  controllers;
- complete neutral `SET_CAMERA`, `PATCH_CONTRIBUTION`, `FLY_TO`, `PICK` and
  `REBUILD_RESOURCES` behaviour;
- build `LayerManager`, target registry and central picking service;
- add typed buffer/resource ownership and telemetry;
- prove on-demand cadence, disposal and resource rebuild; and
- establish modular shader/material and quality-tier infrastructure;
- compare lifecycle, camera application, resize/DPR, failure and resource
  evidence with the equivalent V2 paths.

**Exit:** the runtime can host either scene, survive lifecycle faults and report
truthful backend/resource state without domain imports.

### M2 — Best-in-class fixture Galaxy

**Can start now against fixtures.**

- build the independently toggleable ambient backdrop, plane/grid, all 42
  source-derived regions, fixture catalogue-density, star and label layers;
- implement interactive top-down/tilted camera, fly-to and state restoration;
- implement a scale-aware Galactic-plane grid with disclosed light-year
  intervals that never changes factual target positions;
- implement selected/current/reference/highlight/route visual grammar;
- benchmark star buffer and picking candidates;
- implement semantic zoom/hysteresis with fixture cell/star packets;
- build the Svelte workspace, accessible target list and overlap chooser; and
- capture equivalent V2/V3 camera, region, label, selection, overlap,
  ambient-on/off and failure frames for the first approved comparative baseline.

**Exit:** an excellent production-independent Galaxy experience exists at every
semantic scale using deterministic inputs; 42/42 regions pass lookup/render
tests, fixture density is traceable to fixture coordinates, and the ambient-off
baseline is useful and visually accepted.

### M3 — V3 spatial generation and API

**The real-density lane can start now from the existing systems coordinates;
it does not depend on Ratings V4 completing. Search/rating summaries retain
their reviewed derived-generation dependencies.**

- apply the reviewed migration sequence only through production authority;
- implement the spatial-pyramid builder directly from every coordinate row in
  the pinned canonical systems generation, independently of rating state;
- implement the resumable search projection as its separate derived product;
- make each density level reconcile exactly to the complete canonical-system
  count for its generation and emit a validation receipt;
- settle initial pyramid encoding/levels through benchmarks;
- settle cluster ownership and implement only approved domain runs;
- add coverage, integrity, reproducibility and query-plan validators;
- expose stable generation-pinned map/search endpoints; and
- prove atomic publication/rollback with receipts; and
- close each V2 API-semantic defect in the comparison ledger, including rated
  versus catalogue density, actual cell size, notable-first selection,
  too-wide/empty distinction and missing provenance.

**Exit:** real bounded map data is reproducible, published and queryable without
retired `public.*` dependencies; density reconciliation and provenance receipts
are complete.

### M4 — Real Galaxy streaming and LOD

**Depends on M2 and M3.**

- connect the workspace to generation-pinned cell/star endpoints;
- replace fixture density only with reconciled `v3_spatial.cell_summary` data;
- implement request cancellation, cache, refinement and stale-revision guards;
- preserve guaranteed targets across cell/star transitions;
- integrate physical star colour/salience and deterministic importance lanes;
- tune dense-core/sparse-rim sampling; and
- prove budgets on production-scale data;
- compare V2/V3 settle, hysteresis, stale/cancel, truncation and visual
  continuity scenarios using equivalent bounds and guaranteed targets.

**Exit:** wide, regional and local real-Galaxy navigation is bounded, smooth,
truthful and accepted on both backends, with no procedural density path and a
passing ambient-off visual baseline.

### M5 — Finder and domain hand-offs

**Depends on the V3 Finder API plus M4.**

- synchronize Finder query/results, map emphasis and selection;
- implement Find Around Here, Systems Within…, Set Reference, Inspect, Compare,
  Show Cluster, Plot Route and Plan From Here hand-offs;
- preserve ranking/explanation ownership outside Babylon; and
- prove query/result/map continuity by E2E;
- compare every live V2 hand-off and explicitly close the gap between its tested
  command matrix and its narrower production integration.

**Exit:** Finder and the Galaxy Map operate as one discovery workflow.

### M6 — Fixture System Map and truth ladder

**Can prototype against fixtures after M1; real activation waits for identity and
data-readiness gates.**

- implement `SystemScene`, semantic orrery layout and System camera;
- render stellar/body/ring/infrastructure fixtures across S0–S4;
- prove physical/display separation and schematic placement;
- implement System selection, details, hierarchy tree and Galaxy return;
- handle binary/multiple-star, moon/ring-rich and incomplete systems; and
- benchmark materials, labels and transitions;
- record `V2: absent` for the System scene while comparing its selection,
  details, camera, focus, Back, error and evidence behaviours to the nearest V2
  Galaxy implementations.

**Exit:** System Map truth and interaction contracts are visually and
accessibly proven without overstating real data readiness.

### M7 — Colonisation/Architect planning surface

**Depends on reviewed BodyRef/association APIs and owning CPE/Colony Planner
contracts.**

- adapt current colony/infrastructure truth into System contributions;
- add candidate/constraint/plan contribution contracts;
- render orbital/surface lanes, facilities, construction and option states;
- implement option explanation/comparison;
- implement explicit Add/Replace/Open-in-Planner command flow;
- prove that spatial interactions cannot silently mutate plans; and
- integrate Review/Export evidence for the chosen plan;
- record `V2: absent` for Architect while explicitly improving on the nearest V2
  selection, hand-off, state explanation, accessibility and recovery patterns.

**Exit:** a commander can understand and spatially plan a system while the
planner remains the only mechanics/persistence authority.

### M8 — Commander History, Routes, Powerplay, CPE and CRE expansion

**Later bounded slices.**

- visits, trail, discoveries, scan/map/bio/Codex completeness and expeditions;
- route planning/replay and range layers;
- Powerplay observations and strategy;
- richer colonisation alternatives/dependencies;
- CPE plan projections; and
- CRE Digital Twin evidence/state/history.

Each owner publishes a versioned neutral contribution. The renderer does not
absorb the owner's mechanics. Each bounded slice completes its own V2 baseline,
improvement target and comparative evidence before acceptance.

### M9 — Hardening and production promotion

- complete physical-GPU, memory, bundle, accessibility, recovery and visual
  evidence;
- close every comparison-ledger row with accepted improvement evidence or an
  explicit reviewed trade-off;
- prove both browser validation lanes on the exact release head;
- remove or explicitly disposition remaining React/R3F parity dependencies;
- publish immutable build provenance and backend/feature flags;
- canary through the current application promotion authority; and
- retain a schema-compatible rollback target and map feature kill switches that
  degrade to useful DOM/results rather than a blank route.

**Exit:** the accepted immutable release serves the new Babylon experience with
reviewed operational evidence.

## Parallel work while Ratings V4 completes

The safe parallel lane includes M0, M1, M2, the M3 spatial-pyramid builder/API,
M4 client integration against validated packets, and fixture-only portions of
M6. The real-density source is the coordinate catalogue already present; it is
not waiting for ratings to identify Galaxy structure.

Production writes still require the reviewed migration/publication authority,
and real-data claims require a reconciled spatial receipt rather than the mere
existence of migration `004`. Ratings-derived analytical overlays remain gated
on their own generation. Real System activation additionally requires
BodyRef/hierarchy/association readiness. Architect persistence additionally
requires an owning planner contract.

## Explicit non-goals for the first release

- reproducing all 400 billion procedurally generated systems;
- fabricating unvisited systems or Stellar Forge output;
- literal-scale System rendering;
- invented present orbital phase;
- renderer-owned ratings, Finder ranking, clusters or colonisation mechanics;
- silent plan mutation;
- direct Babylon GUI ownership of application panels/accessibility;
- VR/WebXR without a separate product and acceptance decision;
- physics merely for visual motion;
- unbounded individual-star rendering at whole-Galaxy scale; and
- copying Frontier or unlicensed community assets/code.

## Definition of complete

The Babylon map programme is complete when:

- the Galaxy is an excellent continuous spatial workspace from wide through
  local scales;
- every map area has an evidence-backed V2 baseline (or explicit absence), a
  recorded V3 disposition and a verified improvement or reviewed trade-off;
- all 42 in-game regions are present from the pinned audited source and region
  lookup, labels and rendered geometry agree;
- the visible density field is reproducibly derived from real generation-pinned
  system coordinates, reconciles to its source count and remains distinct from
  optional ambient art;
- the user can deliberately enter an interactive truthful System Map and return
  without losing context;
- colonisation/Architect mode explains current, candidate and planned system
  development and hands explicit actions to the canonical planner;
- every contribution preserves ownership, provenance, truth class, bounds and
  truncation;
- every spatial action has an accessible equivalent;
- production-like data and required hardware/backend tiers meet recorded
  budgets;
- device/context/data failures recover or degrade visibly and usefully;
- deterministic fixtures and both browser lanes protect the whole journey; and
- the release is immutable, receipted, reversible where schema-compatible, and
  contains no dependency on the retired React/R3F runtime.
