# Stage 27A — Stage 26 Inheritance Matrix

## Status and purpose

This Stage 27A audit records what the next spatial platform inherits from Stages
25 and 26. It is a contract and migration input, not authorization to implement
Babylon, alter the production map, remove the R3F/Three.js map, or begin Stage
27B.

Historical sequence is fixed: Stage 26 established requirements, ran an equal
renderer bakeoff, selected R3F/Three.js, delivered the R3F foundation, and cut
that renderer over to production. Product scope subsequently expanded from a
bounded Galaxy Explore surface to a multi-domain spatial platform, changing the
renderer requirements and motivating the new Babylon direction. Babylon did
not win Stage 26; R3F was not a failure; Three.js was not “simply broken.”

Classification vocabulary:

- **KEEP** — retain the existing behavior or contract without changing its
  meaning.
- **EXPAND** — retain it and extend it for the broader Galaxy/System platform.
- **SUPERSEDED** — replace the old constraint or renderer-specific mechanism,
  while preserving applicable user behavior and migration evidence.
- **HISTORICAL_ONLY** — evidence about the completed Stage 26 decision/delivery,
  not a current implementation instruction.

Test disposition vocabulary is **REUSE**, **ADAPT**, **REPLACE**, or
**HISTORICAL**. “Replace” never means delete before equivalent acceptance
coverage exists.

## Behavior and contract inheritance

| Area | Stage 25/26 evidence | Classification | Stage 27 inheritance |
|---|---|---:|---|
| Product role | `stage-25-roadmap.md` §§ Map Product Decision/Stage 25G and `stage-26a-next-generation-map-foundation-contract.md` § Product Decision constrain Map to secondary Explore. | **SUPERSEDED** | Spatial interaction may support Explore → Inspect → Plan → Review. Colony Planner/Cockpit remains the canonical detailed Build Plan workspace and persistence owner; no silent Build Plan mutation or Preview execution is permitted. |
| Renderer history | `stage-26b-renderer-bakeoff-decision.md` §§ Equal Matrix/Measurement Summary/Rationale selects R3F after the equal bakeoff; `stage-26e-cutover-readiness.md` §§ Status/Production Activation Receipt records commit `3b53477` serving it publicly. | **HISTORICAL_ONLY** | Preserve as decision and migration evidence. R3F remains the production baseline and rollback until a future Babylon implementation earns an explicit cutover. |
| Typed scene boundary | `artifacts/map-foundation/stage-26b/map-scene-contract.ts` (`MapSceneState`, `MapInteractionEvent`, `MapReturnWorkflow`) and `frontend/src/features/map-foundation/types.ts` (`FoundationRendererProps`). | **EXPAND** | Generalize to renderer-neutral `SpatialSceneContract`, `GalaxySceneContract`, `SystemSceneContract`, contributions, commands, events, targets and layers. No Babylon/Three types may cross the domain boundary. |
| Camera | Stage 26A requirements 2, 8 and 16; `camera.ts` (`clampCameraCenter`, `snapCameraTopDown`, `zoomCamera`); `R3FMapFoundation.tsx`; `camera.test.ts`; `useSmoothMapZoom.test.tsx`. | **EXPAND** | Preserve top-down excellence, restrained pitch, pan/orbit/zoom, one-time fit, context continuity, bounds, reduced-motion behavior and semantic camera state. Add renderer-neutral Galaxy/System camera contracts and exact Galaxy ↔ System restoration. Replace renderer-specific camera implementation only. |
| Scene lifetime/state | Stage 26A § Scene Boundary; Stage 26C §§ Interaction Boundary/Verification; `feature-handoffs.ts` preserves camera/origin/layers through `applyFeatureHandoff`. | **EXPAND** | Long-lived runtime owns GPU scene/resources; React owns app/domain orchestration. Scene updates must preserve camera, selection, spatial query and compatible layers rather than recreate the scene. |
| Regions | Stage 26A requirement 1 and § Region Data And Legal Gate; `authoritative-regions.ts`; `production-regions.ts`; `AuthoritativeRegionMap.tsx`; `stage-26e-cutover-readiness.md` § Region Data And Legal Gate. | **KEEP** | Keep 42 authoritative named regions plus unmapped sentinel, derived boundaries, verified names and legal provenance. Migrate presentation through a renderer-neutral region contribution; do not reinterpret decorative boundaries as mechanics. |
| Clusters | Stage 26A requirements 4–5; Stage 26C required slice 5; `visibility.ts` (`collectGuaranteedIds`, `buildClusterGeometry`); `feature-handoffs.ts` (`toClusterRepresentation`). | **EXPAND** | Preserve arbitrary anchors/members/roles/edges/radius-or-hull/group context and guaranteed visibility. Extend to spatial query, comparison, colonisation relationships and blockers only from authoritative domain contributions. |
| Routes | Stage 26A requirement 14; `RouteLayer.tsx`, `routeGeometry.ts`, `RouteDetailPanel.tsx`; route tests. | **EXPAND** | Preserve connected geometry, direction/current-waypoint treatment, route details and explicit handoffs. Add route presets, alternate paths and System-scene implications without renderer-owned routing mechanics. |
| Finder | Stage 26D §§ Inbound/Outbound Boundary; `feature-handoffs.ts` `FeatureHandoff` type `finder`; `ProductionMapTab.tsx`; `feature-handoffs.test.ts`. | **EXPAND** | Finder remains owner of filters, Development Score and explanation. Matching systems illuminate, score may affect prominence, irrelevant systems recede, and selected/highlighted systems remain guaranteed. Viewport/reference may feed Finder explicitly; renderer never calculates score. |
| Compare | Stage 26D contract and `FeatureHandoff` type `compare`; `resolveMapInteraction` command `openCompare`. | **EXPAND** | Preserve arbitrary comparison highlights and left/right workflow context; extend to candidates, routes, infrastructure and explicitly planned alternatives while retaining truth classes. |
| Saved/evidence | Stage 26D supports `PinnedEntry`, `WatchlistEntry`, and coordinate-bearing `EvidenceMapEntry`; missing-coordinate rule refuses invented placement. | **EXPAND** | Preserve saved/evidence overlays, provenance and unresolved-coordinate disclosure. Extend evidence at Galaxy/System/body/facility scales; evidence never silently becomes mechanics or planner truth. |
| System Detail | Stage 25C § System Detail as contextual inspect hand-off; Stage 26D `systemDetail` handoff and `openSystemDetail` command. | **EXPAND** | Keep explicit Inspect handoff, then add Enter System and exact return to Galaxy context. System Map is a separate scene/scale; System Detail remains a valid accessible DOM information surface. |
| Planner handoff | Stage 26D read-only planner shapes, `workflowPayload`, `openPlanner`, `plannerSelectionRequired`; test “round-trips planner overlays without mutating a plan payload.” | **EXPAND** | Map may show/compare CPE plans, select proposed locations and initiate explicit planning actions. CPE remains planning owner; no renderer planning logic, silent mutation, Preview execution, or planned-as-built representation. |
| Exploration | `ProductionMapOverlays.explorationVisits/explorationTrail`; `useExplorationLayers.ts`; `explorationGeometry.ts`; `RouteDetailPanel.tsx`. | **EXPAND** | Replace visit-only presentation with one underlying personal exploration record contributing at Galaxy/System and System/body scale. Retain chronology and route geometry; add explainable scan/FSS/DSS/bio/completion facts. Personal evidence is never universal truth. |
| Powerplay | `usePowerplayLayer.ts`, `PowerplayPointLayer.tsx`, `powerplayPresentation.ts`; `PowerplayPointLayer.test.ts`. | **EXPAND** | Preserve source-labelled observation, control-tier size, freshness brightness and per-power colors as one contribution/preset. Keep observation freshness/provenance explicit; renderer does not infer Powerplay state. |
| Selection/highlight guarantees | Stage 26A requirement 4; Stage 26C bounded visibility contract; `visibility.ts`; `ProductionMapTab.test.tsx`. | **KEEP** | Selected systems, arbitrary highlights, cluster anchors/members and route-critical targets bypass normal decluttering/LOD. Extend the guarantee to body/facility targets where relevant, within explicit resource limits. |
| Overlap handling | Stage 26A requirement 7; Stage 26C required slice 6; `visibility.ts` (`groupOverlaps`); `feature-handoffs.ts` handles `overlapChoice`. | **KEEP** | Never choose arbitrarily. Central picking returns explicit overlap candidates and accessible resolution UI at Galaxy and System scales. |
| Bounded visibility | Stage 26A requirement 9; Stage 26C § Bounded Visibility Contract (25,000 rendered background points); `visibility.ts`; `production-parity.ts`. | **EXPAND** | Keep deterministic caps, guaranteed-target bypass and explicit count/truncated/remainder/error metadata. Replace the Stage 26 renderer-specific 25k cap with measured backend/LOD budgets per scene and backend; never send or render unbounded lists. |
| Bounded responses/states | Stage 26A requirement 9; `MapSceneState.boundedResponse`; `ProductionMapTab.tsx` surface states; `viewportSystems.runtime.test.tsx`. | **KEEP** | Preserve explicit loading, empty, stale, truncated and error behavior. New APIs and contribution adapters must expose omissions and unresolved associations rather than inventing data. |
| Presets/layers | `ProductionMapTab.tsx` and `production-parity.ts` support Results/Galaxy/Reference; `useMapLayers.ts` opt-in regions/heatmap/clusters/timeline. | **EXPAND** | Generalize to REALISTIC, FINDER, COLONISATION, POWERPLAY, EXPLORATION and ROUTES combinations. The map and camera/selection/spatial context remain constant while information changes around them. Base Galaxy must remain excellent with ED-Finder overlays off. |
| Accessibility | Stage 26A requirements 10–11; Stage 26C keyboard companion; Stage 26E §§ Closed Engineering Evidence; `R3FMapFoundation.test.tsx` keyboard/focus/reduced-motion tests and `ProductionMapTab.tsx` accessible companion UI. | **KEEP** | React/DOM remains responsible for keyboard/text, named controls, companion lists, overlap choices and explanations. Preserve shortcut disablement, form/dialog non-interference, focus stability, reduced motion and non-canvas equivalents. Extend to System scene. |
| Browser support | Stage 26A requirement 12 said desktop only at 1280×720/1440×900. Current evidence in `docs/development/evidence/26f-deploy-11/README.md` exercises Chromium, Firefox and installed Microsoft Edge; `CLAUDE.md` identifies Windows as primary local-dev target. | **EXPAND** | Current release evidence—not old assumptions—defines the initial lane: desktop Chromium, Firefox and Edge, with the two Stage 26 viewports retained. Stage 27 must separately exercise WebGPU and WebGL2 fallback where supported and report capability-based exclusions; Safari/WebKit is not silently claimed. |
| Performance | Stage 26B matrix measured 100k/500k comparative cells; Stage 26C capped 500k fixture output; Stage 26E measured steady-state frame, GPU timing, buffers and live-route memory. `performance.ts`, `live-route-memory.ts`. | **EXPAND** | Retain instrumentation and bounded budgets. Future standard tiers are 20k/40k production-like, 100k stress, 500k torture and 1m extreme diagnostic. Measure top-down/pitched pan/zoom, LOD/hysteresis, picking, labels, draw calls, visible counts, resource/buffer bytes and idle demand rendering on WebGPU and WebGL2. Torture/diagnostic tiers characterize limits; they are not automatic ship gates. |
| Context loss/recovery | Stage 26A bakeoff measures context-loss recovery; Stage 26C reports lost/restored/usable; Stage 26E records hardware recovery evidence. | **EXPAND** | Preserve observable loss/restoration and post-recovery selection/picking. Add resource rebuild ownership, backend/device-loss telemetry, bounded retry/fallback and an accessible degraded state. “Restored” is not “usable” until a verified render and interaction succeed. |
| Rollback/cutover | `stage-26e-cutover-readiness.md` and `production-route-flag.ts` retain `VITE_STAGE26E_PRODUCTION_MAP=disabled`; commit `3b53477` is the rollback receipt. | **KEEP** | Do not delete or alter the production R3F map in 27A. A later cutover requires parity, browser/backend, accessibility, recovery, performance and product bakeoff evidence plus an explicit rollback path. Stage 27A authorizes only Stage 27B workbench planning. |

## Stage 26 test inheritance

| Evidence/test group | Disposition | Reason and future assertion |
|---|---:|---|
| `camera.test.ts`, `useSmoothMapZoom.test.tsx` | **ADAPT** | Retain semantic camera, bounds, logarithmic zoom, focal point, top-down snap and reduced motion; move assertions off R3F implementation details and add System camera/round-trip state. |
| `R3FMapFoundation.test.tsx` | **ADAPT** | Reuse keyboard, focus, dialog, shortcut-disable, reduced-motion and semantic core-position behavior against the renderer-neutral runtime/DOM host. R3F event details remain baseline-only. |
| `visibility.test.ts` | **REUSE** | Deterministic bounds, guaranteed systems, arbitrary highlights/clusters, overlap groups and invalid-cap rejection are renderer-neutral. Extend target types and semantic LOD/hysteresis. |
| `feature-handoffs.test.ts` | **ADAPT** | Preserve every existing shape, camera/layer continuity, omission reporting and read-only planner guard; migrate to `SpatialContribution` and commands/events, then add Exploration, CRE and CPE contributions. |
| `authoritative-regions.test.ts`, `production-regions.test.ts` | **REUSE** | Region decode/merge, exact labels, shape validation and transport budget remain data contracts independent of renderer. |
| `production-parity.test.ts` | **ADAPT** | Preserve bounded typed buffers, invalid-coordinate rejection, empty/error state and preset camera intent; broaden to new presets, truth classes and both scenes/backends. |
| `ProductionMapTab.test.tsx` | **ADAPT** | Preserve base map without Finder, bounded composition, selection/Inspect handoff, continuous camera and layer explanations. Replace R3F/GPU-pick implementation assumptions with runtime contracts. |
| `RouteLayer.test.ts`, `RouteDetailPanel.test.tsx` | **ADAPT** | Retain route facts, connected geometry, direction/current waypoint, metadata and selection; rebuild renderer-specific geometry assertions for the new layer implementation. |
| `PowerplayPointLayer.test.ts` | **ADAPT** | Preserve semantic color/tier/freshness mapping at contribution/descriptor level; replace Three geometry details. |
| `explorationGeometry.test.ts` | **ADAPT** | Retain chronology, distinct partial/complete states and pick-ID round-trip; expand from visit markers to explainable body-level facts and truth scope. |
| `viewportSystems*.test.*`, `realStarFade.test.tsx`, `SceneContents.test.ts` | **ADAPT** | Keep distinct enter/exit thresholds, tilted footprint, stale-request removal, current-request error, aggregate fallback and demand invalidation. Rebase thresholds and rendering assertions on semantic LOD/backend profiling. |
| `glowPoints.test.ts` | **REPLACE** | Its Three `Points` shader/size-attenuation contract conflicts with the pinned billboard/instanced-quad direction. Preserve only visual acceptance goals; do not carry `gl_PointSize` architecture forward. |
| `map-presentation.test.ts` | **ADAPT** | Keep solid region paths, label containment/declutter and input normalization; replace Three-specific `Line2` expectations and add semantic label tiers. |
| `live-route-memory.test.ts`, Stage 26E performance artifacts | **ADAPT** | Preserve honest unavailable-metric handling and live-route measurement discipline. Add backend, frame, draw-call, resource, buffer and recovery telemetry at the new benchmark tiers. |
| `production-route-flag.test.ts` | **REUSE** | Keep exact enabled/disabled rollback semantics while R3F is production. A future cutover needs a separately reviewed flag/rollback contract, not an in-place weakening. |
| `MapErrorBoundary.test.tsx`, map API error tests | **REUSE** | Runtime failures remain contained and retryable without replacing surrounding accessible UI; expand to backend/device loss and partial contribution failure. |
| `GalacticMap.test.tsx`, `MapTab.test.tsx` | **HISTORICAL** | These cover the older canvas map and its Stage 25 product posture. Keep while that code remains reachable/used, but do not use its renderer model as the Stage 27 target. |
| `frontend/e2e/smoke.spec.ts` Stage 26E map cases | **ADAPT** | Keep production-route activation, region asset, LOD request, resize synchronization, error containment and selection smoke as parity acceptance. Run against explicit old/new candidates before any later cutover. |
| `frontend/e2e/map-debug.spec.ts`, `simple-map-test.spec.ts` | **HISTORICAL** | Useful diagnostic smoke, but not sufficient acceptance coverage and not the future authoritative suite. |
| Stage 26B bakeoff artifacts and Stage 26C/E Playwright/visual/GPU receipts | **HISTORICAL** | Preserve immutable evidence of the Stage 26 decision and cutover. New Babylon evidence must use current requirements and may not rewrite the earlier result. |

## Future benchmark and browser acceptance matrix

Every benchmark fixture must report source size, returned/visible/guaranteed
counts, truncation, backend, viewport/DPR, camera mode, frame percentiles, pick
latency, draw calls, buffer/resource bytes and recovery result. Required dataset
tiers are 20k and 40k production-like, 100k stress, 500k torture, and 1m extreme
diagnostic. Exercise top-down and restrained-pitch camera states, pan and zoom,
semantic LOD with hysteresis, search/fly-to, overlap picking, labels, routes,
clusters, selection/highlight guarantees, presets, stale/empty/truncated/error
responses, resize and DPR changes, reduced motion, and idle/demand rendering.

The release lane inherited from current repository evidence is desktop Chromium,
Firefox and Microsoft Edge at 1280×720 and 1440×900. Stage 27 adds a capability
matrix for WebGPU-first and WebGL2 fallback, including device/context loss and
resource rebuild. Unsupported WebGPU must produce a measured fallback, not a
failed or falsely green cell. Any wider Safari/WebKit or mobile claim requires
new explicit owner/release evidence.

## Deterministic future fixture inheritance

Stage 26's deterministic Galaxy fixtures (42 regions; overlapping systems;
arbitrary highlighted/cluster systems; bounded 100k and 500k populations;
Finder/Compare/saved/evidence/System Detail/Planner handoffs; live updates) are
**EXPAND** inputs. The spatial platform must also define these deterministic
System fixtures:

| Fixture | Minimum contract purpose |
|---|---|
| Simple single-star | S1 stellar truth, semantic scale and stable schematic fallback. |
| Binary and multiple-star | Parent/hierarchy handling without invented relationships or present orbital phase. |
| Moon-rich | Deep hierarchy, selection, labels and bounded semantic layout. |
| Ring-rich | Multiple bands, class/inner/outer radii/provenance; prove unknown rings are not “no rings.” |
| Exploration-rich | Personal chronological scan/FSS/DSS/bio facts and explainable counts; prove personal state is not universal truth. |
| Colonised | Authoritative facilities/infrastructure attached only through resolved identities. |
| Incomplete-data | Unknown fields and missing hierarchy remain unknown and visible; no fabricated parent or association. |
| Schematic-orbit | Deterministic layout marked SCHEMATIC/UNCERTAIN; prove its position is never exposed as authoritative present phase. |
| CPE planning | Planned/proposed facilities, sequence, alternatives and blocked options remain PLANNED/HYPOTHETICAL and never appear built. |
| CRE Digital Twin | Evidence, confidence, contradictions and history layer onto the same System scene without becoming a competing map or unqualified fact. |

Cross-fixture truth tests must additionally prove unresolved body/facility joins
are not forced, ambient dust/nebula/background never enters mechanics data,
display-scaled radius never overwrites physical radius, and a bare body ID or
display name is never treated as globally unique. Canonical body selection uses
the system-scoped identity concept `{ systemId64, bodyId }`.

## Migration and acceptance consequence

Stage 27B may build only an isolated workbench after Stage 27A governance marks
it authorized. It must consume renderer-neutral contracts, keep the production
R3F route unchanged, and demonstrate a representative thin vertical slice of
all four architecture stress tests: Finder, Colonisation, Exploration and
System Map. No Stage 26 test may be removed merely because its implementation
is renderer-specific: first preserve it as historical evidence or land the
replacement behavioral assertion. Production cutover, rollback retirement and
R3F deletion remain later, explicit decisions.
