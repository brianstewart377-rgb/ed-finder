# Spatial Platform Architecture Decision

**Decision:** Stage 27A, 2026-08-30
**Implementation status:** contract only; Babylon runtime is not authorized in
this stage.

## Context and historically accurate decision

Stage 26 followed this sequence: requirements contract → equal renderer bakeoff
→ R3F/Three.js selected → isolated R3F foundation delivered → production
cutover completed. Evidence is in `stage-26a-next-generation-map-foundation-contract.md`,
`stage-26b-renderer-bakeoff-decision.md`, `stage-26c-region-first-foundation-contract.md`,
and `stage-26e-cutover-readiness.md`; production activation is recorded in
`CHANGES.md` at commit `3b53477`. R3F was not a failure and Babylon did not win
Stage 26.

Product scope subsequently expanded to a Galaxy/System/Digital-Twin spatial
platform with first-class exploration and bounded planner participation. Those
requirements change the architectural optimization target. We therefore select
a **greenfield Babylon 9-class renderer inside the brownfield ED-Finder
product**, while retaining the current R3F production renderer and rollback
until a later measured bakeoff and explicit Stage 27G cutover.

The August 16 Babylon 6 plan is historical input, not executable authority. Its
monolithic imports, arbitrary `worldScale`, point-cloud stars and narrow
replacement path are superseded.

## One platform and dependency rule

```text
Finder / CRE / CPE / Exploration / Powerplay / Routes
                         |
              SpatialContribution adapters
                         |
             renderer-neutral SpatialSceneContract
                         |
                     MapRuntime
                  /              \
          GalaxyScene          SystemScene
                  \              /
                 BabylonMapRuntime
                         |
                    LayerManager
                         |
                        GPU
```

Domain and feature code **must not import Babylon**. React owns app/domain
orchestration, routing, panels, accessible DOM UI, keyboard and text. The
runtime owns the long-lived spatial scene, GPU resources, layers, camera
implementation, picking/projection and transitions. CRE owns mechanics and
Digital Twin reasoning. CPE owns plan construction/persistence. ED-Finder owns
orchestration/presentation. Babylon renders.

Dependency enforcement in 27B must include import-boundary tests and a single
renderer adapter package. No `@babylonjs/*` type may leak into public contracts.

## Renderer-neutral contract sketches

These sketches are normative shapes, not inert runtime code. IDs are opaque
strings at the renderer boundary; `systemId64` is serialized as a decimal
string to avoid JavaScript integer loss.

```ts
type RepresentationClass =
  | "AUTHORITATIVE" | "DERIVED" | "PLANNED" | "SCHEMATIC" | "AMBIENT";

type Vec3Ly = Readonly<{ x: number; y: number; z: number }>;
type Provenance = Readonly<{
  source: string; observedAt?: string; ruleVersion?: string;
  confidence?: string; note?: string;
}>;
type Truth<T> = Readonly<{
  value: T; representation: RepresentationClass; provenance?: Provenance[];
}>;

type BodyRef = Readonly<{ systemId64: string; bodyId: number }>;
type RingRef = Readonly<{ body: BodyRef; ringId: string }>;
type FacilityRef = Readonly<{
  owner: "EDFINDER" | "CRE" | "CPE"; facilityId: string;
  systemId64: string;
}>;
type SpatialTarget =
  | Readonly<{ kind: "system"; systemId64: string }>
  | Readonly<{ kind: "body"; ref: BodyRef }>
  | Readonly<{ kind: "ring"; ref: RingRef }>
  | Readonly<{ kind: "facility"; ref: FacilityRef }>
  | Readonly<{ kind: "relationship" | "annotation"; id: string }>
  | Readonly<{ kind: "region" | "route" | "cluster"; id: string }>;

type CameraState = Readonly<{
  focusLy: Vec3Ly; lyPerPixel: number; bearingRad: number; pitchRad: number;
  projection: "perspective" | "orthographic"; revision: number;
}>;
type SystemCameraState = Readonly<{
  systemId64: string; focus: SpatialTarget; semanticDistance: number;
  bearingRad: number; pitchRad: number; revision: number;
}>;

type OrbitalDescriptor = Readonly<{
  periodDays?: Truth<number>; semiMajorAxisAu?: Truth<number>;
  eccentricity?: Truth<number>; inclinationDeg?: Truth<number>;
  ascendingNodeDeg?: Truth<number>; argumentOfPeriapsisDeg?: Truth<number>;
  meanAnomalyDeg?: Truth<number>; epoch?: Truth<string>;
  placement: "OBSERVED_PHASE" | "COMPUTED_PHASE" | "DETERMINISTIC_SCHEMATIC";
}>;
type RingDescriptor = Readonly<{
  state: Truth<"PRESENT" | "ABSENT" | "UNKNOWN">; bands: ReadonlyArray<{
    id: string; ringClass?: Truth<string>; innerRadiusM?: Truth<number>;
    outerRadiusM?: Truth<number>;
  }>;
}>;
type BodyVisualDescriptor = Readonly<{
  ref: BodyRef; parent?: Truth<BodyRef>; class?: Truth<string>;
  physicalRadiusM?: Truth<number>; displayRadius: number;
  orbital?: OrbitalDescriptor; rings?: RingDescriptor;
}>;
type InfrastructureAttachment = Readonly<{
  facility: FacilityRef; body?: Truth<BodyRef>; lane?: Truth<"orbital" | "surface">;
  association: Truth<"CONFIRMED" | "UNRESOLVED" | "CONFLICT">;
}>;

type GalaxyReturnState = Readonly<{
  camera: CameraState;
  selected?: SpatialTarget; reference?: SpatialTarget;
  comparison: readonly SpatialTarget[];
  activePresetIds: readonly string[]; activeLayerIds: readonly string[];
  activeContributionIds: readonly string[];
  finderQueryState?: unknown; routeState?: unknown; timelineState?: unknown;
  workspaceRevision: number;
}>;

interface LayerContract<TPayload = unknown> {
  id: string; version: number; representation: RepresentationClass;
  payload: TPayload; bounds?: unknown; targetCount: number; truncated: boolean;
}
interface SpatialContribution {
  id: string; owner: "FINDER" | "CRE" | "CPE" | "EXPLORATION" | "POWERPLAY" | "ROUTES";
  revision: number; layers: readonly LayerContract[];
}
interface GalaxySceneContract {
  kind: "galaxy"; revision: number; camera: CameraState;
  selection: readonly SpatialTarget[]; contributions: readonly SpatialContribution[];
}
interface SystemSceneContract {
  kind: "system"; revision: number; systemId64: string; fidelity: "S0"|"S1"|"S2"|"S3"|"S4"|"S5";
  camera: SystemCameraState; bodies: readonly BodyVisualDescriptor[];
  infrastructure: readonly InfrastructureAttachment[];
  contributions: readonly SpatialContribution[];
  galaxyReturn: GalaxyReturnState;
}
type SpatialSceneContract = GalaxySceneContract | SystemSceneContract;

type RuntimeCommand =
  | { type: "LOAD_SCENE"; scene: SpatialSceneContract }
  | { type: "PATCH_CONTRIBUTION"; contribution: SpatialContribution }
  | { type: "SET_CAMERA"; camera: CameraState | SystemCameraState }
  | { type: "FLY_TO"; target: SpatialTarget; reducedMotion: boolean }
  | { type: "PICK"; screenX: number; screenY: number }
  | { type: "RESIZE"; width: number; height: number; dpr: number }
  | { type: "REBUILD_RESOURCES"; reason: "backend-change" | "device-loss" | "context-loss" };
type RuntimeEvent =
  | { type: "READY"; backend: "WEBGPU" | "WEBGL2" }
  | { type: "CAMERA_CHANGED"; camera: CameraState | SystemCameraState }
  | { type: "CAMERA_MOVING"; cameraRevision: number; viewportRevision: number }
  | { type: "CAMERA_SETTLED"; cameraRevision: number; viewportRevision: number }
  | { type: "LOD_BAND_CHANGED"; bandId: string; viewportRevision: number }
  | { type: "VIEWPORT_FOOTPRINT_CHANGED"; viewportRevision: number; footprint: unknown }
  | { type: "TARGET_PICKED"; target?: SpatialTarget }
  | { type: "TRANSITION_FINISHED"; target: SpatialTarget }
  | { type: "RESOURCE_LOST" | "RECOVERED"; detail: string }
  | { type: "METRICS"; frameMs: number; visible: number; drawCalls: number; resources: number; bufferBytes: number };
```

Commands are ordered, revisioned and idempotent where possible. Runtime events
describe renderer observations and user intent; they do not mutate domain
models directly. React/domain handlers decide whether an explicit action is
allowed. Camera and viewport revisions are request keys: streaming responses
whose revision no longer matches the active footprint are stale and must be
discarded. Moving/settled and LOD-band events drive bounded fetches and render
invalidation; the contract does not require permanent React `requestAnimationFrame`
polling.

## Coordinates, camera and scale

Canonical CPU coordinates remain actual Elite light-years. Do not introduce an
arbitrary application `worldScale` as truth. Babylon 9's Large World Rendering
and high-precision/floating-origin path is the preferred workbench hypothesis,
to be verified with ED-Finder ranges and camera transitions before commitment.
The official Babylon documentation describes `useLargeWorldRendering` as
high-precision CPU matrices plus camera-relative GPU uniforms. This is a
technical mechanism, not permission to alter canonical coordinates.

The renderer implements ED-Finder's semantic `CameraState`; it does not expose
or blindly adopt `ArcRotateCamera`. Top-down and restrained tilted navigation,
zoom hysteresis, transition cancellation and exact Galaxy-state restoration are
contract tests. `lyPerPixel` is the canonical renderer-neutral Galaxy zoom
measure. Perspective camera distance may be derived internally but cannot
replace that semantic contract. `focusLy` remains actual ED coordinates;
bearing, pitch, projection/top-down semantics, revision, and reduced-motion
transition behavior remain explicit.

## Backend and package direction

Stage 27B evaluates a modern Babylon **9-class** release, with modular
tree-shakeable `@babylonjs/core/...` ES-module imports rather than the legacy
monolithic `babylonjs` package. As verified on 2026-08-30, the official npm
package is in the 9.x line and documents individual imports for tree shaking:
<https://www.npmjs.com/package/@babylonjs/core>.

Use WebGPU first after capability/initialization checks, with WebGL2 fallback
chosen before scene/GPU resource creation. Backend fallback or loss rebuilds
resources from CPU contracts; no hidden backend-specific domain state exists.
This is an ED-Finder architecture consequence: backend-specific GPU resources
are created only after backend selection, so changing backend or recovering
from loss reconstructs them from the renderer-neutral CPU scene contract. It
does not rely on a narrower WebXR-specific limitation as a general engine rule.

## Stars, buffers, LOD and render cadence

Stars use instanced camera-facing quads/billboards or equivalent custom
instance buffers. They are **not** `PointsCloudSystem`/`gl_PointSize`, and never
one mesh per star. Babylon's official instance documentation confirms instance
rendering and picking support, but built-in picking remains a benchmark
candidate, not a predetermined winner:
<https://github.com/BabylonJS/Documentation/blob/master/content/features/featuresDeepDive/mesh/copies/instances.md>.
Babylon's current `PointsCloudSystem` source explicitly documents that its
`pointSize` has no effect under WebGPU, which is why the cross-backend contract
does not depend on variable point primitives:
<https://github.com/BabylonJS/Babylon.js/blob/master/packages/dev/core/src/Particles/pointsCloudSystem.ts>.

Scene data is normalized into typed struct-of-arrays/buffers. React sends
revisioned contributions; it does not rebuild GPU arrays per render. LOD is
semantic, hysteretic and backend-aware. Wide aggregates, regional systems,
local relationships and System scene are distinct budgets.

The runtime is long-lived and renders on demand when idle. Camera motion,
transitions, animations, streaming, hover/picking and dirty layers schedule
frames; stable state stops continuous work. Workers remain possible through
serializable contracts and transferable buffers, but 27B is main-thread-first
until profiling justifies off-thread complexity.

## Picking, labels and overlap

A central `PickingService` owns hit testing and stable target resolution. 27B
benchmarks built-in instance picking, GPU ID buffer, and CPU spatial index plus
GPU confirmation at 20k/40k/100k/500k/1m tiers. Labels use a prioritized,
bounded layout with selected/highlighted/reference guarantees, collision
handling, hysteresis and accessible DOM equivalents. Picking and label layers
cannot silently choose different identities.

## Truth, ambience and SystemScene

Truth metadata remains outside shader-only buffers and survives picking/detail
projection. Ambient density, dust and nebulae cannot be queried as systems or
fed to Finder/CRE/CPE. Unknown rings, hierarchy, associations and orbital phase
remain unknown. System semantic placement is deterministic when factual phase
is unavailable and labelled `SCHEMATIC`; physical measurements remain separate.
Explicit parent evidence wins over parser-derived hierarchy. A name-derived
parent is `DERIVED` or `SCHEMATIC` with provenance, never a bare authoritative
relationship; unresolved parentage stays absent/unresolved. The same rule
applies to facility attachment and relationship/annotation targets.

`SystemSceneContract` is a separate scene-scale contract sharing runtime,
identity, contributions, selection, telemetry and recovery infrastructure with
Galaxy. CRE Digital Twin is a contribution to that scene. CPE plans are
`PLANNED` contributions. Exploration remains personal and sync-key-scoped.
Its required `GalaxyReturnState` carries semantic Galaxy camera, selection and
reference, comparison context, active presets/layers/contributions, and opaque
Finder/query, route, and timeline state so leaving System restores the prior
meaningful Galaxy workspace without giving the renderer domain ownership.

## Lifecycle, telemetry, fixtures and recovery

Runtime lifecycle is create → initialize backend → load scene → patch
contributions → suspend/resume → rebuild → dispose. All observers, buffers,
textures, workers and event bridges have explicit disposal. Recovery reloads
renderer-neutral CPU state and emits loss/recovery events.

Required telemetry: backend, frame CPU/GPU duration where available, visible
count, draw calls, resource count, buffer bytes, streaming latency/truncation,
pick latency, and recovery outcome. It must contain no credentials or personal
exploration payloads.

Fixtures and truth assertions are those in
`spatial-platform-product-contract.md`; Stage 26 fixtures/tests are classified
in `stage-27a-stage26-inheritance-matrix.md`.

## Migration, bakeoff and cutover

1. **27B:** isolated runtime workbench; no production wiring.
2. **27C–27F:** baseline, streaming, parity and workflows behind explicit
   isolation/flags with contract adapters.
3. **27G:** production-shaped Babylon versus current R3F bakeoff, browser lane,
   accessibility, recovery, backend and rollback evidence; explicit owner
   decision required.
4. R3F remains production and rollback until Babylon earns cutover. Removal is
   a later separately authorized decision.
5. **27H–27K:** System data/rendering contract, System Map, infrastructure, CPE
   and CRE layering. 27A does not authorize these implementations.

## Rejected alternatives and consequences

- **Execute the August 16 plan wholesale:** rejected because it targets Babylon
  6, arbitrary scaling, point-cloud stars and a narrow replacement.
- **Extend R3F indefinitely without a new decision:** rejected for the expanded
  programme, not because Stage 26 failed. R3F remains the measured baseline.
- **Renderer-specific domain DTOs:** rejected; they couple every owner to
  Babylon and prevent honest fallback/bakeoff.
- **Separate CRE Digital Twin map:** rejected; it fragments spatial truth.
- **Renderer-owned mechanics/planning:** rejected; violates repo ownership.
- **Literal astronomical System scale or invented current phase:** rejected for
  usability and truth reasons.
- **Immediate worker/offscreen runtime:** rejected pending profiling.

Consequences: Stage 27 needs adapter/version governance, explicit truth metadata,
CPU-state retention for rebuild, dual-backend evidence, and more fixtures before
visual implementation. It also gains one coherent Galaxy/System platform and a
cutover path that preserves Stage 26 value.
