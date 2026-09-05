# Spatial Platform Architecture Decision

**Status:** current V3 renderer-neutral architecture authority

**Browser application:** `apps/web/` (Svelte 5 / SvelteKit 2)

**Renderer target:** a fresh Babylon.js 9-class runtime

## Decision and current state

ED-Finder V3 is one spatial platform spanning Galaxy, System and Digital Twin
views. `apps/web/` is the sole V3 browser destination, and Babylon is its
renderer target. The renderer is greenfield inside the brownfield ED-Finder
product: application and domain code cross a renderer-neutral boundary rather
than carrying React, R3F or Three.js types into V3.

PR #601 is the active integration lane. At known exact head
`12eebac48ca9286e0fd8c180cc5f552dc922d07e`, it contains a real
Explore/Finder -> fresh Babylon -> canonical Inspect slice and the Review Lab
rebase to `apps/web/` plus Babylon. Exact-head validation for that SHA remains
red/stabilizing. This is implemented integration evidence, not a green or
complete checkpoint and not production-promotion authority.

Stage 26 historically selected R3F/Three.js and delivered its map; R3F won that
bakeoff. Those sources remain valuable migration, behaviour, fixture and visual
evidence, but React/R3F/Three is not V3 architecture or current production
authority. Older stage documents never override this decision.

## One platform and dependency rule

```text
Finder / Colonisation / Commander History / Powerplay / Routes / CPE / CRE
                                  |
                     SpatialContribution adapters
                                  |
                  renderer-neutral SpatialSceneContract
                                  |
                              MapRuntime
                           /              \
                   GalaxyScene         SystemScene
                           \              /
                         BabylonMapRuntime
                                  |
                                 GPU
```

Svelte/SvelteKit owns app/domain orchestration, routing, panels,
accessible DOM UI, keyboard and text. Babylon owns the long-lived scene, GPU
resources, camera implementation, layer presentation, picking/projection and
transitions. Renderer-neutral domain handlers decide what a runtime event may
do.

Domain and feature code **must not import Babylon**. Keep one renderer adapter
boundary. No `@babylonjs/*` type may leak into public contracts. Babylon
never owns mechanics, ranking, persistence, query meaning or plan construction.
Finder owns query/ranking behaviour, CRE owns mechanics and Digital Twin
reasoning, CPE owns plan construction and persistence, and ED-Finder owns
orchestration and presentation.

## Renderer-neutral contract

IDs are opaque at the renderer boundary. `systemId64` is a decimal string so
JavaScript cannot lose integer precision.

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
type FacilityRef = Readonly<{
  owner: "EDFINDER" | "CRE" | "CPE"; facilityId: string;
  systemId64: string; body?: BodyRef;
}>;
type SpatialTarget =
  | Readonly<{ kind: "system"; systemId64: string }>
  | Readonly<{ kind: "body"; ref: BodyRef }>
  | Readonly<{ kind: "facility"; ref: FacilityRef }>
  | Readonly<{ kind: "region" | "route" | "cluster"; id: string }>;

type CameraState = Readonly<{
  focusLy: Vec3Ly; distanceLy: number; bearingRad: number; pitchRad: number;
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
  state: "PRESENT" | "ABSENT" | "UNKNOWN"; bands: ReadonlyArray<{
    id: string; ringClass?: Truth<string>; innerRadiusM?: Truth<number>;
    outerRadiusM?: Truth<number>;
  }>;
}>;
type BodyVisualDescriptor = Readonly<{
  ref: BodyRef; parent?: BodyRef; class?: Truth<string>;
  physicalRadiusM?: Truth<number>; displayRadius: number;
  orbital?: OrbitalDescriptor; rings?: RingDescriptor;
}>;
type InfrastructureAttachment = Readonly<{
  facility: FacilityRef; body?: BodyRef; lane?: Truth<"orbital" | "surface">;
  association: "CONFIRMED" | "UNRESOLVED" | "CONFLICT";
}>;

interface LayerContract<TPayload = unknown> {
  id: string; version: number; representation: RepresentationClass;
  payload: TPayload; bounds?: unknown; targetCount: number; truncated: boolean;
}
interface SpatialContribution {
  id: string;
  owner: "FINDER" | "COLONISATION" | "COMMANDER_HISTORY" | "POWERPLAY" | "ROUTES" | "CPE" | "CRE";
  revision: number; layers: readonly LayerContract[];
}
interface GalaxySceneContract {
  kind: "galaxy"; revision: number; camera: CameraState;
  selection: readonly SpatialTarget[]; contributions: readonly SpatialContribution[];
}
interface SystemSceneContract {
  kind: "system"; revision: number; systemId64: string;
  fidelity: "S0" | "S1" | "S2" | "S3" | "S4" | "S5";
  camera: SystemCameraState; bodies: readonly BodyVisualDescriptor[];
  infrastructure: readonly InfrastructureAttachment[];
  contributions: readonly SpatialContribution[];
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
  | { type: "TARGET_PICKED"; target?: SpatialTarget }
  | { type: "TRANSITION_FINISHED"; target: SpatialTarget }
  | { type: "RESOURCE_LOST" | "RECOVERED"; detail: string }
  | { type: "METRICS"; frameMs: number; visible: number; drawCalls: number; resources: number; bufferBytes: number };
```

Commands are ordered, revisioned and idempotent where practical. Events report
renderer observations and user intent; they do not mutate domain models.
Layer/query results must carry explicit total or returned counts, bounds and a
`truncated` state. No UI may imply complete coverage from a bounded response.

## Coordinates, camera and semantic scale

Canonical CPU coordinates are true Elite Cartesian light-years. There is no
arbitrary application `worldScale` masquerading as truth. Floating-origin or
Babylon Large World Rendering is an implementation technique to verify, not a
change to canonical coordinates.

The continuous Galaxy camera preserves meaningful camera, selection, reference
and layers while crossing four semantic scales:

1. **Wide:** aggregate density, all 42 named regions, major references and route
   overview.
2. **Regional:** real and important systems, labels and regional facts.
3. **Local:** system relationships, colonisation, infrastructure, routes and
   bounded spatial queries.
4. **System:** an explicit transition to `SystemScene`, preserving Galaxy state
   for return.

LOD is semantic and hysteretic. Selected, highlighted, reference and active
route targets survive LOD and aggregation transitions. Top-down and restrained
tilted navigation, transition cancellation, reduced motion and exact Galaxy
state restoration are contract requirements.

## Search, spatial queries, picking and overlap

The platform supports search/fly-to, stable picking and keyboard/text
equivalents for every pickable target. Overlap is resolved through a bounded,
accessible disambiguation UI; hit testing and labels cannot silently disagree
about identity. Labels have priority, collision handling and guarantees for
selected/highlighted/reference targets.

Finder supports **Search From Here** and **Systems Within...** with explicit
viewport, reference, region and radius inputs. Finder remains query and ranking
owner. Cluster membership is a domain-derived contribution with provenance,
never a renderer-generated gameplay fact.

The search/spatial-index/grid/cluster design is an active decision gate. Current
local Finder search uses raw `x`/`y`/`z` distance, not a grid as a first-class
accelerator. Do not canonize a grid, PostgreSQL index strategy, cluster
algorithm, streaming envelope or cache until measured query shapes, bounds,
cardinality and explain plans support that choice. PostgreSQL 18 derived-data
bootstrap is gated by the same decision.

The scoring/data contract is also open: repository code still applies Ratings
v3.4 in places, while roadmap intent has moved some judgement toward archetypes.
An explicit product/data decision must choose ownership, migration and
compatibility before the full PostgreSQL 18 derived-data build. The renderer
must not settle that decision or reproduce either scoring model.

## Domain contributions and truth

- **Finder** contributes bounded matches, highlights and score explanations;
  ranking stays outside Babylon.
- **Commander History / Journal** contributes commander-scoped visits,
  discoveries, scans, records, expeditions and routes. Personal observations
  never become universal catalogue truth.
- **Routes**, **Powerplay** and **Colonisation** contribute their own typed,
  provenance-bearing facts and relationships.
- **CPE** contributes `PLANNED` facilities and alternatives while retaining
  construction, validation and persistence ownership.
- **CRE Digital Twin** contributes mechanics-owned state, reasoning, evidence,
  history and uncertainty to the shared System scene.

The five runtime representation classes have fixed meanings:

- `AUTHORITATIVE`: retained observation or accepted catalogue fact.
- `DERIVED`: reproducible result from named inputs and rules.
- `PLANNED`: a user/CPE proposal, never portrayed as built.
- `SCHEMATIC`: deterministic presentation or unresolved association, clearly
  labelled as such.
- `AMBIENT`: decorative context that is neither selectable truth nor mechanics
  input.

Missing evidence remains unknown. Provenance and representation live outside
shader-only buffers and survive picking and detail projection.

## System Map

`SystemScene` shares identity, selection, contribution, telemetry and recovery
infrastructure with Galaxy while using a separate semantic scale. `BodyRef`
(`systemId64` plus system-scoped `bodyId`) is canonical; a name is a label, not
identity.

Physical values remain factual while display radius and spacing may be
semantic. Current orbital phase is never invented: when phase/epoch is
insufficient, placement is deterministic and explicitly `SCHEMATIC`. Unknown
rings, hierarchy and facility/body association remain unknown. Infrastructure
attachments carry `CONFIRMED`, `UNRESOLVED` or `CONFLICT` rather than forcing a
join. CPE proposals remain `PLANNED`; CRE Digital Twin evidence retains its own
truth and uncertainty.

## Runtime, performance and recovery

Use modular `@babylonjs/core/...` imports. Choose WebGPU only after capability
and initialization checks, with WebGL2 fallback selected before scene/GPU
resource creation. Backend fallback or device/context loss rebuilds from
renderer-neutral CPU state.

Stars use instanced camera-facing quads/billboards or equivalent typed instance
buffers, never one mesh per star or factual point-cloud shortcuts. The
Svelte/SvelteKit application sends revisioned contributions and does not rebuild
GPU arrays per component render. Render on demand when idle; camera movement,
transition, animation, streaming, hover and dirty layers schedule frames.

Workers and transferable buffers are measured options, not default complexity.
Picking/index candidates must be benchmarked at representative 20k/40k/100k,
500k and 1m diagnostic tiers. Report WebGPU and WebGL2 separately, including
visible/returned counts, truncation, frame CPU/GPU timing where available, draw
calls, resources, buffer bytes, streaming latency, pick latency and recovery.

Lifecycle is create -> initialize -> load -> patch -> suspend/resume -> rebuild
-> dispose. Observers, buffers, textures, workers and bridges have explicit
disposal. Telemetry contains no credentials or commander payloads.

## Browser evidence and consequences

Product E2E/Visual Acceptance and Review Lab are separate exact-head lanes as
defined in `docs/development/v3-browser-validation-lanes.md`. Both exercise
`apps/web/` plus Babylon. Review Lab varies deterministic synthetic data and its
isolated environment; it does not validate a React/R3F substitute and does not
replace Product E2E.

The architecture requires versioned adapters, truth metadata, CPU-state
retention, bounded-query semantics, accessible DOM parity, dual-backend evidence
and deterministic fixtures. Implementation readiness is earned by the relevant
exact-head checks; PR #601's current red/stabilizing state must not be described
as a completed checkpoint.
