# Map Research Closure & Requirement Matrix (Stage 26B)

**Repository Snapshot**: ed-finder @ `69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0`

**Renderer Selection Status**: Three.js/R3F selected for the isolated Stage 26C foundation from the recorded 12-cell Chromium bake-off. This is not a production-readiness or cutover claim.

## Deterministic Local Repair

The quarantined V25 bundle was repaired locally without a new model run. The repair makes one-time auto-fit revision-triggered and consumable, completes the default-map and simultaneous-overlay assertions, and gives the R3F transition machine durable camera state plus explicit `transitionPhase` and `lastAppliedCamera` observables. Strict compilation of the three TypeScript artifacts together, JSON parsing, exact sentinel-plus-42-region comparison with the authoritative snapshot source, targeted semantic checks, and the 17-fixture uniqueness check all passed. These are contract-level validations only; no renderer benchmark or browser runtime measurement was executed.

The subsequent harness implementation review found and repaired a cross-renderer camera-scale and orientation mismatch. `CameraState.zoom` remains renderer-independent LY per pixel: deck.gl receives `log2(1 / lyPerPixel)`, while the R3F orthographic camera receives `1 / lyPerPixel`. All candidates now use the same XY galaxy plane (`x`, `z`), OrbitView maps zero common pitch to its 90-degree top-down posture, and invalid scale values are rejected. This repair is likewise contract-level and does not itself constitute a renderer measurement.

---

## Requirement Coverage Matrix

| # | Requirement (short) | Status | Evidence URLs | Artifact Keys | Explanation |
|---|---------------------|--------|---------------|---------------|-------------|
| 0 | Use attached snapshot; disposable renderer | satisfied | `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/frontend/package.json#L1-L78`, `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/frontend/src/features/map/GalacticMap.tsx#L1-L100` | [map-research-closure] | All artifacts are self‑contained; no dependency on the current Canvas renderer. The closure records the SHA. |
| 1 | 42 regions + index‑0 sentinel | satisfied | `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/apps/importer/src/data/region_map.json#L1-L15` | [map-region-verification, map-research-closure] | JSON artifact lists 42 named regions and an explicit sentinel; verification checks confirm no 43rd region. |
| 2 | Dimensions, transform, out‑of‑range, interior label point | satisfied | `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/apps/importer/src/region_map.py#L1-L115` | [map-region-verification, map-research-closure] | JSON records 2048×2048, authoritative pixel scale 0.020263671875, origin (−49985,−24105), rejection for px<0/pz<0/pz>=2048, and RLE fallthrough. Interior‑label‑point method documented in both JSON and map-scene-contract (centroid algorithm). |
| 3 | Provenance & redistribution uncertainty | satisfied | `https://raw.githubusercontent.com/klightspeed/EliteDangerousRegionMap/master/LICENSE`, `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/apps/importer/src/region_map.py#L1-L115` | [map-region-verification, map-research-closure] | MIT license for klightspeed code; importer license status downgraded to unobserved (no license file found in inspected files, full directory listing not captured); region names / RLE rights unresolved, marked as 'may be protected by Frontier Developments rights'. No distribution recommended. |
| 4 | Complete compileable Map scene contract | satisfied | (self‑contained TypeScript) | [map-scene-contract, map-research-closure] | `map-scene-contract.ts` declares MapSceneState and all required members, with multi‑highlight array, executable keyboard‑companion reducer, executable one‑time‑auto‑fit scene reducer, workflow‑return reducer, interior label point method, and feature handoff matrix. The file compiles in isolation. |
| 5 | Arbitrary highlights & cluster contracts | satisfied | (clusterFixture in bake‑off) | [map-scene-contract, map-bakeoff-scenarios, map-research-closure] | ClusterRepresentation includes anchor, members, roles, edges, radius, hull, label, groupContext. clusterFixture constructs a three‑member cluster, asserts every field including memberRoles, and guarantees renderability. |
| 6 | Bidirectional events for 8 surfaces | satisfied | (handoff matrix in contract) | [map-scene-contract, map-bakeoff-scenarios, map-research-closure] | MapInteractionEvent / MapReturnWorkflow unions cover all 8 surfaces. reduceReturnWorkflow applies side effects. Handoff matrix has 8 rows; each fixture reference resolves and every fixture now exercises the return‑workflow round‑trip (clusterFixture calls clusterSearch, simultaneousOverlayFixture calls both savedSystems and evidenceMap, etc.). Planner is read‑only. |
| 7 | Overlap disambiguation & keyboard companion | satisfied | (overlapKeyboardFixture) | [map-scene-contract, map-bakeoff-scenarios, map-research-closure] | Overlap ordering = (distancePx, id64). KeyboardCompanionState with 4 phases, each with explicit key bindings and initialization functions. Executable reduceKeyboardCompanion processes key events and returns side effects; used by all keyboard fixtures. overlapKeyboardFixture initializes overlap candidates and exercises Tab/Shift+Tab/Enter/Escape; confirm and cancel both reachable with concrete assertions. |
| 8 | One‑time auto‑fit & manual camera survival | satisfied | (autoFitFixture) | [map-scene-contract, map-bakeoff-scenarios, map-research-closure] | MapSceneState.oneTimeFitIntent + executable reduceScene applies auto‑fit only when an armed intent meets a new sceneRevision, then consumes the intent. autoFitFixture arms the intent, advances the revision, manually drags camera to (20,30), then applies selection, loadMoreSystems, layerToggle, and setHighlights; the manual camera survives without retriggering. plannerReturnFixture asserts full restored state including layers, clusters, workflow discriminator, and payload. |
| 9 | Bounded data & guaranteed renderability | satisfied | (multiple fixtures) | [map-scene-contract, map-bakeoff-scenarios, map-research-closure] | BoundedResponse exposes count/truncated/continuation. Update guarantees selected/highlighted IDs remain renderable via forced inclusion. Fixtures assert guaranteedSystemIds in cluster, comparison, finder, systemDetail, planner, autoFit scenarios. |
| 10 | Renderer‑independent adapter with completion signaling | satisfied | (map-renderer-adapter.ts) | [map-renderer-adapter, map-research-closure] | Adapter defines mount, update, resize, deliverInteraction, measure, contextLost/recover, startCameraTransition (returns Promise<CameraState>), cancelCameraTransition, retargetCameraTransition, and idempotent dispose. No internal renderer types exposed. |
| 11 | Bake‑off of three candidates with explicit camera transitions and evidence-based selection | satisfied | (adapter, harness, results, and decision record) | [map-renderer-adapter, map-bakeoff-scenarios, map-bakeoff-results, map-research-closure] | The isolated harness ran all three candidates against both dataset sizes and both required viewports. Three.js/R3F is selected for Stage 26C from the recorded evidence; no production cutover is implied. |
| 12 | Shared Vite/React harness with 100k/500k deterministic datasets | satisfied | (bake‑off harness spec) | [map-renderer-adapter, map-bakeoff-scenarios, map-region-verification, map-research-closure] | bake‑off artifact specifies Vite + React, two dataset sizes, region layer, UI controls, fixtures, instrumentation, and a Playwright journey. Datasets generated with deterministic coordinates. |
| 13 | 17 deterministic fixtures with concrete assertions | satisfied | (bake‑off artifact) | [map-bakeoff-scenarios, map-research-closure] | 17 named fixtures emitted. All seven Stage 26 scenarios covered, plus lifecycle fixtures. Keyboard fixtures use keyboard reducer; transition fixtures use corrected machine; simultaneous overlay fixture adds both saved and evidence returns; cluster fixture adds return‑workflow round‑trip; planner fixture asserts full restored state. Keyboard overlay toggle fixture precondition fixed: scene layers initialized via returnFromWorkflow before keyboard phase. |
| 14 | Measurement records with GPU unknown | satisfied | (adapter measurements) | [map-renderer-adapter, map-bakeoff-scenarios, map-research-closure] | MeasurementRecord includes all required metrics; all default to null. GPU timing explicitly unknown. decisionLogForCandidate correctly populates measurements with UNKNOWN_MEASUREMENT. |
| 15 | Gap‑free decision handling & unknown sentinels | satisfied | (decision logs and measurement receipt) | [map-renderer-adapter, map-bakeoff-results, map-region-verification, map-research-closure] | Executed Chromium measurements are recorded per candidate, dataset, and viewport. GPU timing and candidate-specific compressed bundle size remain explicit nulls; legal conclusions remain unresolved. |
| 16 | Desktop viewports 1280×720 & 1440×900 only | satisfied | (bake‑off viewports) | [map-scene-contract, map-renderer-adapter, map-bakeoff-scenarios, map-research-closure] | Bake‑off harness only specifies 1280×720 and 1440×900. No mobile/touch/phone‑width references exist. |
| 17 | Raven Colonial as usability warning only | satisfied | (research closure note) | [map-research-closure] | The closure records Raven Colonial as a usability warning. No Raven layout, styling, assets, or interaction patterns appear in any artifact. |
| 18 | Five complete retained artifacts and closure matrix | satisfied | (all five artifacts emitted) | [map-research-closure] | The `artifacts` array contains the five mandated keys with complete bodies. This closure matrix links every requirement. |
| 19 | Original isolated research run made no product edits or execution claims | satisfied | (original five artifacts) | [map-scene-contract, map-renderer-adapter, map-bakeoff-scenarios, map-region-verification, map-research-closure] | The original Research Control run remained design-only. The later local harness and measurement receipt are explicitly identified follow-up engineering evidence, isolated from the production entry and canonical data paths. |
| 20 | Every code claim cites repo:// URL; external claims cite primary source | satisfied | `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/apps/importer/src/data/region_map.json#L1-L15`, `repo://ed7a9d22-9f4c-4472-b177-1e995cf72b28/69cfb27c68e43865a6e7c5e3fa28f5fd59bafda0/apps/importer/src/region_map.py#L1-L115`, `https://raw.githubusercontent.com/klightspeed/EliteDangerousRegionMap/master/LICENSE` | [map-region-verification, map-research-closure] | All repository code claims in the region verification JSON and closure document cite exact repo:// + commit + path + line URLs copied from captured tool observations. External license claims cite fetched primary sources (klightspeed LICENSE). The V5 report and search results are used only as leads, not evidence. |

## Feature Handoff Audit

| Surface | Outbound Event | Return Workflow | Fixture Key | Resolves? |
|---------|---------------|-----------------|-------------|-----------|
| Map | `navigateToMap` | `map` | `mapDefaultFixture` | Yes – fixture declared |
| Finder | `navigateToFinder` | `finder` | `finderSelectionFixture` | Yes |
| System Detail | `navigateToSystemDetail` | `systemDetail` | `systemDetailFixture` | Yes |
| Compare | `navigateToCompare` | `compare` | `comparisonFixture` | Yes |
| Saved Systems | `navigateToSavedSystems` | `savedSystems` | `simultaneousOverlayFixture` | Yes – fixture calls savedSystems return |
| Evidence Map | `navigateToEvidenceMap` | `evidenceMap` | `simultaneousOverlayFixture` | Yes – fixture calls evidenceMap return |
| Cluster Search | `navigateToClusterSearch` | `clusterSearch` | `clusterFixture` | Yes – fixture calls clusterSearch return |
| Planner | `navigateToPlanner` | `planner` | `plannerReturnFixture` | Yes |

All eight handoff rows have resolving fixture references. Every fixture exists in `map-bakeoff-scenarios.ts` and exercises the corresponding return‑workflow round‑trip.

## Fixture‑Invariant Matrix (audit)

| Fixture | Guaranteed Renderability | Cluster Integrity | Highlight Integrity | LOD Override | State Restoration | Manual Camera Survival | Transition Sync | Idle Rejection | Preserve Last Applied | Recovery Usability | Overlap Disambiguation | Keyboard Traversal | Keyboard Overlay | Keyboard Search |
|---------|--------------------------|-------------------|---------------------|--------------|------------------|------------------------|-----------------|----------------|-----------------------|-------------------|------------------------|---------------------|-------------------|-----------------|
| clusterFixture | ✓ | ✓ | ✓ | | | | | | | | | | | |
| comparisonFixture | ✓ | | ✓ | | | | | | | | | | | |
| finderSelectionFixture | ✓ | | | | | | | | | | | | | |
| selectedSystemLODOverrideFixture | ✓ | | | ✓ | | | | | | | | | | |
| plannerReturnFixture | ✓ | | | | ✓ | | | | | | | | | |
| simultaneousOverlayFixture | | | ✓ | | | | | | | | | | | |
| autoFitFixture | ✓ | | | | | ✓ | | | | | | | | |
| mapDefaultFixture | | | | | ✓ | | | | | | | | | |
| systemDetailFixture | ✓ | | | | | | | | | | | | | |
| r3fZeroDurationFixture | | | | | | | ✓ | | | | | | | |
| r3fIdleRetargetingFixture | | | | | | | | ✓ | | | | | | | |
| r3fCancelFixture | | | | | | | | | ✓ | | | | | |
| r3fRecoveryFixture | | | | | | | | | | ✓ | | | | |
| overlapKeyboardFixture | | | | | | | | | | | ✓ | | | |
| keyboardSystemTraversalFixture | | | | | | | | | | | | ✓ | | |
| keyboardOverlayToggleFixture | | | | | | | | | | | | | ✓ | |
| keyboardSearchResultFixture | | | | | | | | | | | | | | ✓ |

All 17 fixtures are represented. Universal invariants are checked across relevant fixtures.

## Disagreements

- The V24 report incorrectly marked most requirements as "unresolved"; the V25 addendum requires fulfillment‑based grading. This closure assigns `satisfied` to design deliverables that are complete and correctly handle unknowns.
- The V24 claim that the klightspeed repository had no LICENSE was contradicted by a fetched MIT license; this closure records the correct MIT license.
- The V24 report claimed 13 fixtures; the V25 addendum mandates 17. This closure provides exactly 17 fixtures with concrete assertions.
- Reviewer critiques about simultaneous overlay impossibility, missing keyboard reducer, missing scene reducer, unreachable transition assertions, and missing cluster/planner assertions have all been resolved through concrete artifact corrections.

## Known V5 Corrections

- Highlights changed to array to support simultaneous independent highlight groups.
- Executable keyboard‑companion reducer (`reduceKeyboardCompanion`) added; all keyboard fixtures use it.
- Executable one‑time‑auto‑fit scene reducer (`reduceScene`) added; autoFitFixture exercises it.
- R3F transition machine corrected: `initCamera` method added, `start` uses stored camera, zero‑duration synchronous, cancellation preserves `lastApplied`.
- Deck.gl OrbitView and OrthographicView now have explicit transition state machines (`DeckOrbitTransitionMachine`, `DeckOrthoTransitionMachine`) with `tick`, `cancel`, `retarget`, context loss/recovery.
- Cluster fixture now includes `returnFromWorkflow` with `clusterSearch` and asserts `memberRoles`.
- Planner return fixture now asserts `layers`, `clusters`, `workflowDiscriminator`, and `workflowPayload`.
- Simultaneous overlay fixture now calls both `savedSystems` and `evidenceMap` returns; reducer merges highlights.
- R3F recovery fixture gets a second tick to complete transition.
- Keyboard overlay toggle fixture corrected: precondition fixed so scene layers are initialized via `returnFromWorkflow` with type `map` before keyboard phase.
- Noop adapter `measure()` returns a fully‑populated `MeasurementRecord` with all fields `null`.
- ED‑Finder importer license status downgraded to "not‑observed" with uncertainty language.
- Deterministic defect corrections: fixed TypeScript strict-mode error in `computeInteriorLabelPoint` (`regionMapRows[pz]!` non-null assertion for `noUncheckedIndexedAccess`), and corrected keyboard overlay toggle fixture precondition so scene layers are initialized before keyboard phase.

## Bake‑off Execution Plan

1. Build three production bundles (deck.gl OrbitView, deck.gl OrthographicView, Three.js R3F).
2. Using the shared Vite/React harness, mount each candidate at 1280×720 and 1440×900.
3. For each candidate, run both 100k and 500k deterministic datasets.
4. Execute the shared Playwright journey that walks through all 17 fixtures.
5. Collect `MeasurementRecord` for every run; all values start as `null`.
6. After all benchmarks, compare measurement distributions (if measured) and scenario pass/fail results.
7. Renderer selection remains a manual decision outside this research scope.

## Legal Unknowns

- The region names and RLE pixel geometry may be protected by Frontier Developments rights. Redistribution requires legal review. (No primary source confirming ownership was located; this is an inference based on origin from in‑game codex.)
- The ED‑Finder importer code does not have a declared license at the captured commit; its use in a distributed application requires license clarification.

## Measurement Unknowns

- `map-bakeoff-results.json` records one local Chromium observation for every
  candidate, dataset size, and required viewport. It is evidence for the Stage
  26C foundation choice, not a broad hardware/browser performance guarantee.
- GPU timing remains unknown because a GPU timer extension was not used.
- Candidate-specific compressed bundle size remains unknown because the shared
  harness bundle was not split into independent production bundles.
- Context-restored event timing is measured. Post-recovery renderer-backed
  picking passed for R3F and failed for both deck.gl candidates in this run.

## Stage 26B Boundaries

- Only the five map‑foundation artifacts are delivered.
- No integration with the rest of the ED‑Finder frontend is performed.
- No production renderer is selected; all bake‑off execution is planned, not performed.
- The map scene does not connect to a live backend; all data is synthetic/deterministic.
