export type RepresentationClass = 'AUTHORITATIVE' | 'DERIVED' | 'PLANNED' | 'SCHEMATIC' | 'AMBIENT';
export type Vec3Ly = Readonly<{ x: number; y: number; z: number }>;
export type Provenance = Readonly<{ source: string; observedAt?: string; ruleVersion?: string; confidence?: string; note?: string }>;
export type Truth<T> = Readonly<{ value: T; representation: RepresentationClass; provenance?: readonly Provenance[] }>;
export type BodyRef = Readonly<{ systemId64: string; bodyId: number }>;
export type FacilityRef = Readonly<{ owner: 'EDFINDER' | 'CRE' | 'CPE'; facilityId: string; systemId64: string; body?: BodyRef }>;
export type SpatialTarget =
  | Readonly<{ kind: 'system'; systemId64: string }>
  | Readonly<{ kind: 'body'; ref: BodyRef }>
  | Readonly<{ kind: 'facility'; ref: FacilityRef }>
  | Readonly<{ kind: 'region' | 'route' | 'cluster'; id: string }>;
export type SpatialTargetId = string;
export type CameraState = Readonly<{ focusLy: Vec3Ly; distanceLy: number; bearingRad: number; pitchRad: number; projection: 'perspective' | 'orthographic'; revision: number }>;
export type SystemCameraState = Readonly<{ systemId64: string; focus: SpatialTarget; semanticDistance: number; bearingRad: number; pitchRad: number; revision: number }>;
export type OrbitalDescriptor = Readonly<{ periodDays?: Truth<number>; semiMajorAxisAu?: Truth<number>; eccentricity?: Truth<number>; inclinationDeg?: Truth<number>; ascendingNodeDeg?: Truth<number>; argumentOfPeriapsisDeg?: Truth<number>; meanAnomalyDeg?: Truth<number>; epoch?: Truth<string>; placement: 'OBSERVED_PHASE' | 'COMPUTED_PHASE' | 'DETERMINISTIC_SCHEMATIC' }>;
export type RingBand = Readonly<{ id: string; ringClass?: Truth<string>; innerRadiusM?: Truth<number>; outerRadiusM?: Truth<number> }>;
export type RingDescriptor =
  | Readonly<{ state: 'PRESENT'; bands: readonly [RingBand, ...RingBand[]] }>
  | Readonly<{ state: 'ABSENT' | 'UNKNOWN' }>;
export type BodyVisualDescriptor = Readonly<{ ref: BodyRef; parent?: BodyRef; class?: Truth<string>; physicalRadiusM?: Truth<number>; displayRadius: number; orbital?: OrbitalDescriptor; rings?: RingDescriptor }>;
export type InfrastructureAttachment = Readonly<{ facility: FacilityRef; body?: BodyRef; lane?: Truth<'orbital' | 'surface'>; association: 'CONFIRMED' | 'UNRESOLVED' | 'CONFLICT' }>;

/** Stage 27B's synthetic star payload; it remains renderer-neutral layer data. */
export type SpatialObject = Readonly<{ id: string; target?: SpatialTarget; representation: RepresentationClass; positionLy: Vec3Ly; color: readonly [number, number, number, number]; importance: number }>;
export interface LayerContract<TPayload = unknown> { id: string; version: number; representation: RepresentationClass; payload: TPayload; bounds?: unknown; targetCount: number; truncated: boolean }
export interface SpatialContribution { id: string; owner: 'ED_FINDER_BASE' | 'FINDER' | 'COLONISATION' | 'CRE' | 'CPE' | 'COMMANDER_HISTORY' | 'POWERPLAY' | 'ROUTES'; revision: number; layers: readonly LayerContract[] }
export interface GalaxySceneContract { kind: 'galaxy'; revision: number; camera: CameraState; selection: readonly SpatialTarget[]; contributions: readonly SpatialContribution[] }
export interface SystemSceneContract { kind: 'system'; revision: number; systemId64: string; fidelity: 'S0' | 'S1' | 'S2' | 'S3' | 'S4' | 'S5'; camera: SystemCameraState; selection: readonly SpatialTarget[]; bodies: readonly BodyVisualDescriptor[]; infrastructure: readonly InfrastructureAttachment[]; contributions: readonly SpatialContribution[] }
export type SpatialSceneContract = GalaxySceneContract | SystemSceneContract;

export type RuntimeCommand =
  | { type: 'LOAD_SCENE'; scene: SpatialSceneContract }
  | { type: 'PATCH_CONTRIBUTION'; contribution: SpatialContribution }
  | { type: 'SET_CAMERA'; camera: CameraState | SystemCameraState }
  | { type: 'FLY_TO'; target: SpatialTarget; reducedMotion: boolean }
  | { type: 'PICK'; screenX: number; screenY: number; maxCandidates: number }
  | { type: 'RESIZE'; width: number; height: number; dpr: number }
  | { type: 'REBUILD_RESOURCES'; reason: 'backend-change' | 'device-loss' | 'context-loss' };
export type RuntimeEvent =
  | { type: 'READY'; backend: 'WEBGPU' | 'WEBGL2' }
  | { type: 'CAMERA_CHANGED'; camera: CameraState | SystemCameraState }
  | ({ type: 'PICK_RESULT' } & PickResult)
  | { type: 'TRANSITION_FINISHED'; target: SpatialTarget }
  | { type: 'RESOURCE_LOST'; detail: string }
  | { type: 'RECOVERY_RESULT'; outcome: 'RECOVERED' | 'FALLBACK' | 'FAILED'; detail: string; latencyMs: number }
  | { type: 'STREAMING_METRICS'; latencyMs: number; requested: number; delivered: number; truncated: boolean }
  | { type: 'METRICS'; cpuFrameMs: number | null; gpuFrameMs: number | null; visibleCount: number; drawCalls: number; resources: number; bufferBytes: number };
export type RuntimeBackend = 'WEBGPU' | 'WEBGL2';
export type PickCandidate = Readonly<{ target: SpatialTarget; distancePx: number }>;
export type PickResult = Readonly<{ candidates: readonly PickCandidate[]; truncated: boolean; totalCandidates?: number; latencyMs: number }>;
/** Stage 27B exposes only picking paths it actually implements and measures. */
export type PickStrategy = 'cpu-screen-projection' | 'cpu-spatial-index';
export type RuntimeTelemetry = Readonly<{ backend: RuntimeBackend; cpuFrameMs: number | null; gpuFrameMs: number | null; streamLatencyMs: number | null; streamTruncated: boolean; visibleCount: number; drawCalls: number; resourceCount: number; bufferBytes: number; pickLatencyMs: number | null; recoveryOutcome: 'not-attempted' | 'pending' | 'usable' | 'failed'; renderedFrames: number }>;
export type MapRuntimeOptions = Readonly<{ preferWebGpu: boolean; reducedMotion: boolean; onTelemetry?: (telemetry: RuntimeTelemetry) => void; onEvent?: (event: RuntimeEvent) => void }>;
export interface MapRuntime { initialize(canvas: HTMLCanvasElement, options: MapRuntimeOptions): Promise<RuntimeBackend>; dispatch(command: RuntimeCommand): Promise<unknown> | unknown; snapshot(): Readonly<{ camera: CameraState | SystemCameraState | null; selection: readonly SpatialTarget[] }>; dispose(): void }

export function spatialTargetId(target: SpatialTarget): SpatialTargetId {
  if (target.kind === 'system') return `system:${target.systemId64}`;
  if (target.kind === 'body') return `body:${target.ref.systemId64}:${target.ref.bodyId}`;
  if (target.kind === 'facility') {
    const bodyIdentity = target.ref.body ? `${target.ref.body.systemId64}:${target.ref.body.bodyId}` : 'none';
    return `facility:${target.ref.owner}:${target.ref.systemId64}:${bodyIdentity}:${target.ref.facilityId}`;
  }
  return `${target.kind}:${target.id}`;
}
export function isSelectableObject(object: SpatialObject): object is SpatialObject & { target: SpatialTarget } { return object.representation !== 'AMBIENT' && object.target !== undefined; }
