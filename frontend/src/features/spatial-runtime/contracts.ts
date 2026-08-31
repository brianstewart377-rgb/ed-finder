export type SpatialTargetKind = 'system' | 'body' | 'facility' | 'ambient';
export type SpatialTruthClass = 'factual' | 'observed' | 'planned' | 'hypothetical' | 'ambient';
export type SpatialTargetId = `${'system' | 'body' | 'facility'}:${string}`;

export type SpatialObject = Readonly<{
  id: string;
  targetId: SpatialTargetId | null;
  kind: SpatialTargetKind;
  truthClass: SpatialTruthClass;
  positionLy: readonly [number, number, number];
  color: readonly [number, number, number, number];
  importance: number;
}>;

export type SpatialContribution = Readonly<{
  id: string;
  revision: number;
  objects: readonly SpatialObject[];
}>;

export type SemanticCameraState = Readonly<{
  centerLy: readonly [number, number, number];
  distanceLy: number;
  yawRadians: number;
  pitchRadians: number;
  mode: 'top-down' | 'pitched';
}>;

export type SpatialSceneContract = Readonly<{
  revision: number;
  contributions: readonly SpatialContribution[];
  camera: SemanticCameraState;
  selectedTargetId: SpatialTargetId | null;
  highlightedTargetIds: readonly SpatialTargetId[];
  referenceTargetIds: readonly SpatialTargetId[];
}>;

export type RuntimeBackend = 'webgpu' | 'webgl2';
export type PickCandidate = Readonly<{ targetId: SpatialTargetId; distancePx: number }>;
export type PickStrategy = 'babylon-instance' | 'gpu-id-buffer' | 'cpu-index-gpu-confirm';
export type RuntimeTelemetry = Readonly<{
  backend: RuntimeBackend;
  cpuFrameMs: number | null;
  gpuFrameMs: number | null;
  visibleCount: number;
  drawCalls: number;
  resourceCount: number;
  bufferBytes: number;
  pickLatencyMs: number | null;
  recovery: 'not-attempted' | 'pending' | 'usable' | 'failed';
  renderedFrames: number;
}>;

export type MapRuntimeOptions = Readonly<{
  preferWebGpu: boolean;
  reducedMotion: boolean;
  onTelemetry?: (telemetry: RuntimeTelemetry) => void;
  onSelection?: (targetId: SpatialTargetId | null) => void;
}>;

export interface MapRuntime {
  initialize(canvas: HTMLCanvasElement, options: MapRuntimeOptions): Promise<RuntimeBackend>;
  loadScene(scene: SpatialSceneContract): void;
  updateContribution(contribution: SpatialContribution): boolean;
  resize(cssWidth: number, cssHeight: number, dpr: number): void;
  setCamera(camera: SemanticCameraState): void;
  flyTo(targetId: SpatialTargetId, durationMs?: number): Promise<boolean>;
  cancelFlyTo(): void;
  pick(xCss: number, yCss: number, strategy: PickStrategy): Promise<readonly PickCandidate[]>;
  suspend(): void;
  resume(): void;
  requestFrame(reason: string): void;
  rebuild(reason: 'backend-loss' | 'manual'): Promise<void>;
  snapshot(): Readonly<{ camera: SemanticCameraState; selectedTargetId: SpatialTargetId | null }>;
  dispose(): void;
}

export function isSelectableObject(object: SpatialObject): object is SpatialObject & { targetId: SpatialTargetId } {
  return object.kind !== 'ambient' && object.truthClass !== 'ambient' && object.targetId !== null;
}
