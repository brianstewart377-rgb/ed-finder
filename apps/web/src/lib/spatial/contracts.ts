/**
 * Renderer-neutral Stage 27 spatial contracts.
 *
 * Coordinates in galaxy scenes are canonical Elite light-years. Renderers may
 * choose a precision strategy internally, but no renderer scale is domain
 * truth and no renderer-specific type may cross this boundary.
 */
export type RepresentationClass =
  'AUTHORITATIVE' | 'DERIVED' | 'PLANNED' | 'SCHEMATIC' | 'AMBIENT';

export type Vec3Ly = Readonly<{ x: number; y: number; z: number }>;

export type Provenance = Readonly<{
  source: string;
  observedAt?: string;
  ruleVersion?: string;
  confidence?: string;
  note?: string;
}>;

export type Truth<T> = Readonly<{
  value: T;
  representation: RepresentationClass;
  provenance?: readonly Provenance[];
}>;

export type BodyRef = Readonly<{ systemId64: string; bodyId: number }>;

export type FacilityRef = Readonly<{
  owner: 'EDFINDER' | 'CRE' | 'CPE';
  facilityId: string;
  systemId64: string;
  body?: BodyRef;
}>;

export type SpatialTarget =
  | Readonly<{ kind: 'system'; systemId64: string }>
  | Readonly<{ kind: 'body'; ref: BodyRef }>
  | Readonly<{ kind: 'facility'; ref: FacilityRef }>
  | Readonly<{ kind: 'region' | 'route' | 'cluster'; id: string }>;

export type CameraState = Readonly<{
  focusLy: Vec3Ly;
  distanceLy: number;
  bearingRad: number;
  pitchRad: number;
  projection: 'perspective' | 'orthographic';
  revision: number;
}>;

export type SystemCameraState = Readonly<{
  systemId64: string;
  focus: SpatialTarget;
  semanticDistance: number;
  bearingRad: number;
  pitchRad: number;
  revision: number;
}>;

export type LayerContract<TPayload = unknown> = Readonly<{
  id: string;
  version: number;
  representation: RepresentationClass;
  payload: TPayload;
  bounds?: unknown;
  targetCount: number;
  truncated: boolean;
}>;

export type SpatialContribution = Readonly<{
  id: string;
  owner:
    'FINDER' | 'CRE' | 'CPE' | 'COMMANDER_HISTORY' | 'POWERPLAY' | 'ROUTES';
  revision: number;
  layers: readonly LayerContract[];
}>;

export type OrbitalDescriptor = Readonly<{
  periodDays?: Truth<number>;
  semiMajorAxisAu?: Truth<number>;
  eccentricity?: Truth<number>;
  inclinationDeg?: Truth<number>;
  ascendingNodeDeg?: Truth<number>;
  argumentOfPeriapsisDeg?: Truth<number>;
  meanAnomalyDeg?: Truth<number>;
  epoch?: Truth<string>;
  placement: 'OBSERVED_PHASE' | 'COMPUTED_PHASE' | 'DETERMINISTIC_SCHEMATIC';
}>;

export type RingDescriptor = Readonly<{
  state: 'PRESENT' | 'ABSENT' | 'UNKNOWN';
  bands: ReadonlyArray<
    Readonly<{
      id: string;
      ringClass?: Truth<string>;
      innerRadiusM?: Truth<number>;
      outerRadiusM?: Truth<number>;
    }>
  >;
}>;

export type BodyVisualDescriptor = Readonly<{
  ref: BodyRef;
  parent?: BodyRef;
  class?: Truth<string>;
  physicalRadiusM?: Truth<number>;
  displayRadius: number;
  orbital?: OrbitalDescriptor;
  rings?: RingDescriptor;
}>;

export type InfrastructureAttachment = Readonly<{
  facility: FacilityRef;
  body?: BodyRef;
  lane?: Truth<'orbital' | 'surface'>;
  association: 'CONFIRMED' | 'UNRESOLVED' | 'CONFLICT';
}>;

export type GalaxySceneContract = Readonly<{
  kind: 'galaxy';
  revision: number;
  camera: CameraState;
  selection: readonly SpatialTarget[];
  contributions: readonly SpatialContribution[];
}>;

export type SystemSceneContract = Readonly<{
  kind: 'system';
  revision: number;
  systemId64: string;
  fidelity: 'S0' | 'S1' | 'S2' | 'S3' | 'S4' | 'S5';
  camera: SystemCameraState;
  bodies: readonly BodyVisualDescriptor[];
  infrastructure: readonly InfrastructureAttachment[];
  contributions: readonly SpatialContribution[];
}>;

export type SpatialSceneContract = GalaxySceneContract | SystemSceneContract;

export type RuntimeCommand =
  | Readonly<{ type: 'LOAD_SCENE'; scene: SpatialSceneContract }>
  | Readonly<{
      type: 'PATCH_CONTRIBUTION';
      contribution: SpatialContribution;
    }>
  | Readonly<{
      type: 'SET_CAMERA';
      camera: CameraState | SystemCameraState;
    }>
  | Readonly<{
      type: 'FLY_TO';
      target: SpatialTarget;
      reducedMotion: boolean;
    }>
  | Readonly<{ type: 'PICK'; screenX: number; screenY: number }>
  | Readonly<{ type: 'RESIZE'; width: number; height: number; dpr: number }>
  | Readonly<{
      type: 'REBUILD_RESOURCES';
      reason: 'backend-change' | 'device-loss' | 'context-loss';
    }>;

export type RuntimeEvent =
  | Readonly<{ type: 'READY'; backend: 'WEBGPU' | 'WEBGL2' }>
  | Readonly<{
      type: 'CAMERA_CHANGED';
      camera: CameraState | SystemCameraState;
    }>
  | Readonly<{ type: 'TARGET_PICKED'; target?: SpatialTarget }>
  | Readonly<{ type: 'TRANSITION_FINISHED'; target: SpatialTarget }>
  | Readonly<{
      type: 'RESOURCE_LOST' | 'RECOVERED';
      detail: string;
    }>
  | Readonly<{
      type: 'METRICS';
      frameMs: number;
      visible: number;
      drawCalls: number;
      resources: number;
      bufferBytes: number;
    }>;

export type SpatialViewport = Readonly<{
  width: number;
  height: number;
  dpr: number;
}>;

export type SpatialRendererBackend = 'WEBGPU' | 'WEBGL2';
export type SpatialRuntimeFailure =
  'BACKEND_UNAVAILABLE' | 'INITIALIZATION_FAILED' | 'RUNTIME_FAILED';

export type SpatialRuntimeStatus =
  | Readonly<{ state: 'created' | 'starting' | 'disposed' }>
  | Readonly<{ state: 'ready'; backend: SpatialRendererBackend }>
  | Readonly<{ state: 'failed'; failure: SpatialRuntimeFailure }>;

export interface SpatialRuntime {
  getStatus(): SpatialRuntimeStatus;
  start(): Promise<SpatialRuntimeStatus>;
  resize(viewport: SpatialViewport): void;
  dispose(): void;
}

export type SpatialRuntimeStatusListener = (
  status: SpatialRuntimeStatus,
) => void;
