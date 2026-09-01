import { Engine } from '@babylonjs/core/Engines/engine';
import { WebGPUEngine } from '@babylonjs/core/Engines/webgpuEngine';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine';
import { Scene } from '@babylonjs/core/scene';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
import { Camera } from '@babylonjs/core/Cameras/camera';
import { Vector3, Matrix } from '@babylonjs/core/Maths/math.vector';
import type { Ray } from '@babylonjs/core/Culling/ray';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import type { CameraState, MapRuntime, MapRuntimeOptions, PickCandidate, PickResult, PickStrategy, RuntimeBackend, RuntimeCommand, RuntimeEvent, RuntimeTelemetry, SpatialContribution, SpatialSceneContract, SpatialTarget } from '../contracts';
import { spatialTargetId } from '../contracts';
import { applyRevisionedContribution, normalizeScene, selectGpuSceneBuffers, semanticLodPolicy, type CompactSceneBuffers, type SemanticLod } from '../scene-data';
import { boundPickCandidates, buildCpuSpatialPickIndex, cpuSpatialIndexCandidates, type CpuSpatialPickIndex } from '../picking';
import { ResourceRecoveryBridge } from './recovery';

const PITCH_MIN = 0.35;
const PITCH_MAX = Math.PI / 2;

export class BabylonMapRuntime implements MapRuntime {
  private canvas: HTMLCanvasElement | null = null;
  private engine: AbstractEngine | null = null;
  private scene: Scene | null = null;
  private camera: ArcRotateCamera | null = null;
  private stars: Mesh | null = null;
  private state: SpatialSceneContract | null = null;
  private buffers: CompactSceneBuffers | null = null;
  private gpuBuffers: CompactSceneBuffers | null = null;
  private pickIndex: CpuSpatialPickIndex | null = null;
  private gpuSourceIndices = new Set<number>();
  private gpuLodLevel: SemanticLod | undefined;
  private options: MapRuntimeOptions = { preferWebGpu: true, reducedMotion: false };
  private backend: RuntimeBackend = 'WEBGL2';
  private suspended = false;
  private framePending = false;
  private disposed = false;
  private flyAbort: AbortController | null = null;
  private renderedFrames = 0;
  private recovery: RuntimeTelemetry['recoveryOutcome'] = 'not-attempted';
  private lastPickMs: number | null = null;
  private lastStreamMs: number | null = null;
  private recoveryBridge: ResourceRecoveryBridge | null = null;
  private engineGeneration = 0;
  private starOriginLy: CameraState['focusLy'] | null = null;
  private applyingCamera = false;

  async initialize(canvas: HTMLCanvasElement, options: MapRuntimeOptions): Promise<RuntimeBackend> {
    this.dispose();
    this.disposed = false;
    this.options = options;
    const generation = ++this.engineGeneration;
    const selected = await this.createEngine(canvas, options.preferWebGpu);
    if (this.disposed || generation !== this.engineGeneration) {
      selected.engine.dispose();
      return selected.backend;
    }
    this.canvas = selected.canvas;
    this.engine = selected.engine;
    this.backend = selected.backend;
    this.attachRecoveryObservers(selected.engine);
    this.createGpuScene();
    this.emitEvent({ type: 'READY', backend: this.backend });
    return this.backend;
  }

  private async createEngine(canvas: HTMLCanvasElement, preferWebGpu: boolean): Promise<{ engine: AbstractEngine; backend: RuntimeBackend; canvas: HTMLCanvasElement }> {
    if (preferWebGpu && 'gpu' in navigator && await WebGPUEngine.IsSupportedAsync) {
      let engine: WebGPUEngine | null = null;
      try {
        engine = new WebGPUEngine(canvas, { antialias: true, adaptToDeviceRatio: false, useLargeWorldRendering: true });
        await engine.initAsync();
        return { engine, backend: 'WEBGPU', canvas };
      } catch {
        engine?.dispose();
        canvas = freshFallbackCanvas(canvas);
      }
    }
    const gl = canvas.getContext('webgl2', { antialias: true });
    if (!gl) throw new Error('Stage 27B requires WebGPU or WebGL2');
    return { engine: new Engine(gl, true, { adaptToDeviceRatio: false, useLargeWorldRendering: true }), backend: 'WEBGL2', canvas };
  }

  private createGpuScene(): void {
    if (!this.engine || !this.canvas) return;
    this.scene = new Scene(this.engine, { useFloatingOrigin: true });
    this.scene.clearColor.set(0.002, 0.004, 0.012, 1);
    const cameraState = this.state?.camera ?? defaultCamera();
    const distance = 'distanceLy' in cameraState ? cameraState.distanceLy : cameraState.semanticDistance;
    this.camera = new ArcRotateCamera('semantic-camera', cameraState.bearingRad, cameraState.pitchRad, distance, Vector3.Zero(), this.scene);
    this.camera.lowerBetaLimit = PITCH_MIN;
    this.camera.upperBetaLimit = PITCH_MAX;
    this.camera.lowerRadiusLimit = 1;
    this.camera.wheelPrecision = 0.2;
    this.camera.attachControl(this.canvas, true);
    this.camera.onViewMatrixChangedObservable.add(() => { this.syncSemanticCameraFromBabylon(); this.requestFrame('camera'); });
    this.applyCamera(cameraState);
    if (this.buffers) this.rebuildStarResources();
  }

  loadScene(scene: SpatialSceneContract): void {
    this.cancelFlyTo();
    if (scene.kind === 'system') this.disposeStarResources();
    const started = performance.now();
    this.state = scene;
    this.buffers = normalizeScene(scene);
    this.pickIndex = buildCpuSpatialPickIndex(this.buffers, Math.max(1, scene.kind === 'galaxy' ? scene.camera.distanceLy / 20 : 1));
    this.gpuSourceIndices.clear();
    this.gpuLodLevel = undefined;
    this.refreshGpuBuffers(true);
    this.lastStreamMs = performance.now() - started;
    const requested = scene.contributions.reduce((count, contribution) => count + contribution.layers.reduce((sum, layer) => sum + layer.targetCount, 0), 0);
    const truncated = scene.contributions.some((contribution) => contribution.layers.some((layer) => layer.truncated));
    this.emitEvent({ type: 'STREAMING_METRICS', latencyMs: this.lastStreamMs, requested, delivered: this.buffers.targets.length, truncated });
    this.rebuildStarResources();
    // Rebuilding rebases every star around the newly loaded fixture's focus.
    // Apply the camera after that origin exists so its target uses the same
    // coordinate space as the uploaded instances.
    this.applyCamera(scene.camera);
    this.requestFrame('scene-load');
  }

  updateContribution(contribution: SpatialContribution): boolean {
    if (!this.state) return false;
    const result = applyRevisionedContribution(this.state, contribution);
    if (!result.applied) return false;
    this.state = result.scene;
    this.buffers = normalizeScene(result.scene);
    this.pickIndex = buildCpuSpatialPickIndex(this.buffers, Math.max(1, result.scene.kind === 'galaxy' ? result.scene.camera.distanceLy / 20 : 1));
    this.refreshGpuBuffers(true);
    this.rebuildStarResources();
    this.requestFrame('contribution');
    return true;
  }

  private rebuildStarResources(): void {
    if (!this.scene || !this.gpuBuffers || !this.state || this.state.kind !== 'galaxy') return;
    this.disposeStarResources();
    // One camera-facing quad and compact instance buffers: never Points/gl_PointSize,
    // and never one mesh per star. Float64 LY truth remains in `buffers`; GPU values
    // are camera-relative Float32 transforms. Babylon 9 LWR/high-precision matrices
    // are enabled as an additional guard, not an application worldScale.
    const quad = MeshBuilder.CreatePlane('instanced-stars', { size: 8 }, this.scene);
    quad.billboardMode = Mesh.BILLBOARDMODE_ALL;
    quad.isPickable = true;
    const material = new StandardMaterial('star-material', this.scene);
    material.disableLighting = true;
    material.emissiveColor = Color3.White();
    quad.material = material;
    const matrices = new Float32Array(this.gpuBuffers.targets.length * 16);
    const origin = this.state.camera.focusLy;
    this.starOriginLy = { ...origin };
    for (let index = 0; index < this.gpuBuffers.targets.length; index += 1) {
      Matrix.Translation(
        this.gpuBuffers.positionsLy[index * 3]! - origin.x,
        this.gpuBuffers.positionsLy[index * 3 + 1]! - origin.y,
        this.gpuBuffers.positionsLy[index * 3 + 2]! - origin.z,
      ).copyToArray(matrices, index * 16);
    }
    quad.thinInstanceSetBuffer('matrix', matrices, 16, true);
    const colors = Float32Array.from(this.gpuBuffers.colors, (value) => value / 255);
    quad.thinInstanceSetBuffer('color', colors, 4, false);
    this.stars = quad;
  }

  resize(cssWidth: number, cssHeight: number, dpr: number): void {
    if (!this.canvas || !this.engine) return;
    const safeDpr = Math.max(0.5, Math.min(2, dpr));
    this.canvas.width = Math.max(1, Math.round(cssWidth * safeDpr));
    this.canvas.height = Math.max(1, Math.round(cssHeight * safeDpr));
    this.canvas.style.width = `${cssWidth}px`; this.canvas.style.height = `${cssHeight}px`;
    this.engine.resize(); this.updateOrthographicBounds(); this.requestFrame('resize');
  }

  setCamera(camera: CameraState): void {
    if (!this.state || this.state.kind !== 'galaxy') return;
    this.state = { ...this.state, camera: clampCamera(camera) };
    this.refreshGpuBuffers(false);
    this.applyCamera(this.state.camera); this.requestFrame('camera-set');
    this.emitEvent({ type: 'CAMERA_CHANGED', camera: this.state.camera });
  }

  private refreshGpuBuffers(force: boolean): void {
    if (!this.buffers || !this.state || this.state.kind !== 'galaxy') { this.gpuBuffers = null; this.gpuSourceIndices.clear(); this.gpuLodLevel = undefined; return; }
    const nextLevel = semanticLodPolicy(this.state.camera, this.gpuLodLevel).level;
    if (!force && nextLevel === this.gpuLodLevel) return;
    const selected = selectGpuSceneBuffers(this.state, this.buffers, this.gpuSourceIndices, this.gpuLodLevel);
    this.gpuBuffers = selected.buffers;
    this.gpuSourceIndices = new Set(selected.sourceIndices);
    this.gpuLodLevel = selected.policy.level;
    if (!force) this.rebuildStarResources();
  }

  private applyCamera(camera: CameraState | import('../contracts').SystemCameraState): void {
    if (!this.camera) return;
    this.applyingCamera = true;
    try {
      this.camera.alpha = camera.bearingRad;
      this.camera.beta = Math.max(PITCH_MIN, Math.min(PITCH_MAX, camera.pitchRad));
      this.camera.radius = Math.max(1, 'distanceLy' in camera ? camera.distanceLy : camera.semanticDistance);
      if ('distanceLy' in camera) {
        this.camera.mode = camera.projection === 'orthographic' ? Camera.ORTHOGRAPHIC_CAMERA : Camera.PERSPECTIVE_CAMERA;
        const origin = this.starOriginLy ?? camera.focusLy;
        this.camera.target.set(camera.focusLy.x - origin.x, camera.focusLy.y - origin.y, camera.focusLy.z - origin.z);
        this.updateOrthographicBounds();
      } else {
        this.camera.mode = Camera.PERSPECTIVE_CAMERA;
        this.camera.target.set(0, 0, 0);
      }
    } finally { this.applyingCamera = false; }
  }

  private updateOrthographicBounds(): void {
    if (!this.camera || this.camera.mode !== Camera.ORTHOGRAPHIC_CAMERA) return;
    const aspect = this.engine ? this.engine.getRenderWidth() / Math.max(1, this.engine.getRenderHeight()) : 1;
    const halfHeight = Math.max(1, this.camera.radius) / 2;
    this.camera.orthoLeft = -halfHeight * aspect;
    this.camera.orthoRight = halfHeight * aspect;
    this.camera.orthoTop = halfHeight;
    this.camera.orthoBottom = -halfHeight;
  }

  private syncSemanticCameraFromBabylon(): void {
    if (this.applyingCamera || !this.camera || !this.state) return;
    if (this.state.kind === 'galaxy') {
      const origin = this.starOriginLy ?? this.state.camera.focusLy;
      const next = clampCamera({ ...this.state.camera,
        focusLy: { x: origin.x + this.camera.target.x, y: origin.y + this.camera.target.y, z: origin.z + this.camera.target.z },
        distanceLy: this.camera.radius, bearingRad: this.camera.alpha, pitchRad: this.camera.beta,
        projection: this.camera.mode === Camera.ORTHOGRAPHIC_CAMERA ? 'orthographic' : 'perspective',
        revision: this.state.camera.revision + 1 });
      if (sameGalaxyCamera(this.state.camera, next)) return;
      this.state = { ...this.state, camera: next };
      this.refreshGpuBuffers(false);
      this.updateOrthographicBounds();
      this.emitEvent({ type: 'CAMERA_CHANGED', camera: next });
      return;
    }
    const next = { ...this.state.camera, semanticDistance: this.camera.radius, bearingRad: this.camera.alpha, pitchRad: this.camera.beta, revision: this.state.camera.revision + 1 };
    if (sameSystemCamera(this.state.camera, next)) return;
    this.state = { ...this.state, camera: next };
    this.emitEvent({ type: 'CAMERA_CHANGED', camera: next });
  }

  async flyTo(target: SpatialTarget, durationMs = 600): Promise<boolean> {
    const targetIndex = this.buffers?.targets.findIndex((candidate) => candidate ? spatialTargetId(candidate) === spatialTargetId(target) : false) ?? -1;
    if (targetIndex < 0 || !this.state || this.state.kind !== 'galaxy' || !this.buffers) return false;
    this.cancelFlyTo();
    const abort = new AbortController(); this.flyAbort = abort;
    const destination = [this.buffers.positionsLy[targetIndex * 3]!, this.buffers.positionsLy[targetIndex * 3 + 1]!, this.buffers.positionsLy[targetIndex * 3 + 2]!] as const;
    const start = this.state.camera.focusLy;
    const boundedDuration = this.options.reducedMotion ? 0 : Math.max(0, Math.min(1_500, durationMs));
    const started = performance.now();
    let complete = false;
    while (!complete) {
      if (abort.signal.aborted) return false;
      const progress = boundedDuration === 0 ? 1 : Math.min(1, (performance.now() - started) / boundedDuration);
      this.setCamera({ ...this.state.camera, focusLy: { x: start.x + (destination[0] - start.x) * progress, y: start.y + (destination[1] - start.y) * progress, z: start.z + (destination[2] - start.z) * progress }, revision: this.state.camera.revision + 1 });
      complete = progress >= 1;
      if (!complete) await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    }
    this.rebuildStarResources();
    this.applyCamera(this.state.camera);
    this.flyAbort = null; this.emitEvent({ type: 'TRANSITION_FINISHED', target }); return true;
  }

  cancelFlyTo(): void { this.flyAbort?.abort(); this.flyAbort = null; }

  async pick(xCss: number, yCss: number, strategy: PickStrategy, maxCandidates = 16): Promise<PickResult> {
    const start = performance.now();
    let candidates: PickCandidate[] = [];
    if (strategy === 'cpu-screen-projection') {
      candidates = this.screenSpaceCandidates(xCss, yCss);
    } else if (this.buffers && this.pickIndex && this.state?.kind === 'galaxy') {
      const point = this.galaxyPlanePointAtPointer(xCss, yCss);
      if (point) candidates = cpuSpatialIndexCandidates(this.pickIndex, this.buffers, point.x, point.z, this.state.camera.distanceLy / 20);
    }
    this.lastPickMs = performance.now() - start;
    const result = boundPickCandidates(candidates, Math.max(1, Math.min(64, Math.floor(maxCandidates))), this.lastPickMs);
    this.emitTelemetry(); this.emitEvent({ type: 'PICK_RESULT', ...result }); return result;
  }

  private galaxyPlanePointAtPointer(xCss: number, yCss: number): { x: number; z: number } | null {
    if (!this.scene || !this.camera || !this.engine || !this.canvas || this.state?.kind !== 'galaxy') return null;
    const ray = this.scene.createPickingRay(
      xCss * this.engine.getRenderWidth() / Math.max(1, this.canvas.clientWidth),
      yCss * this.engine.getRenderHeight() / Math.max(1, this.canvas.clientHeight),
      Matrix.Identity(),
      this.camera,
      false,
    );
    return galaxyPlanePointFromRay(ray, this.starOriginLy ?? this.state.camera.focusLy);
  }

  private screenSpaceCandidates(xCss: number, yCss: number): PickCandidate[] {
    if (!this.gpuBuffers || !this.state || this.state.kind !== 'galaxy' || !this.scene || !this.camera || !this.engine || !this.canvas) return [];
    const cssScaleX = this.engine.getRenderWidth() / Math.max(1, this.canvas.clientWidth);
    const cssScaleY = this.engine.getRenderHeight() / Math.max(1, this.canvas.clientHeight);
    const viewport = this.camera.viewport.toGlobal(this.engine.getRenderWidth(), this.engine.getRenderHeight());
    const origin = this.starOriginLy ?? this.state.camera.focusLy;
    const candidates: PickCandidate[] = [];
    for (const index of this.gpuBuffers.selectableIndices) {
      const projected = Vector3.Project(
        new Vector3(this.gpuBuffers.positionsLy[index * 3]! - origin.x, this.gpuBuffers.positionsLy[index * 3 + 1]! - origin.y, this.gpuBuffers.positionsLy[index * 3 + 2]! - origin.z),
        Matrix.IdentityReadOnly, this.scene.getTransformMatrix(), viewport,
      );
      const distancePx = Math.hypot(projected.x - xCss * cssScaleX, projected.y - yCss * cssScaleY) / Math.max(cssScaleX, cssScaleY);
      const target = this.gpuBuffers.targets[index];
      if (target && projected.z >= 0 && projected.z <= 1 && distancePx <= 8) candidates.push({ target, distancePx });
    }
    return candidates.sort((a, b) => a.distancePx - b.distancePx || spatialTargetId(a.target).localeCompare(spatialTargetId(b.target)));
  }

  suspend(): void { this.suspended = true; }
  resume(): void { this.suspended = false; this.requestFrame('resume'); }
  requestFrame(_reason: string): void {
    if (this.suspended || this.framePending || this.disposed) return;
    this.framePending = true;
    requestAnimationFrame(() => { this.framePending = false; if (this.suspended || !this.scene) return; const started = performance.now(); this.scene.render(); this.renderedFrames += 1; this.emitTelemetry(performance.now() - started); });
  }

  private emitEvent(event: RuntimeEvent): void { this.options.onEvent?.(event); }
  private detachRecoveryObservers(): void {
    this.recoveryBridge?.dispose(); this.recoveryBridge = null;
  }
  private attachRecoveryObservers(engine: AbstractEngine): void {
    const generation = ++this.engineGeneration;
    this.recoveryBridge = new ResourceRecoveryBridge(
      { lost: engine.onContextLostObservable, restored: engine.onContextRestoredObservable }, this.backend,
      () => { if (this.disposed || generation !== this.engineGeneration) return; this.rebuildStarResources(); this.recovery = 'usable'; this.requestFrame('resource-restored'); this.emitTelemetry(); },
      (event) => { if (this.disposed || generation !== this.engineGeneration) return; if (event.type === 'RESOURCE_LOST') { this.recovery = 'pending'; this.emitTelemetry(); } this.emitEvent(event); },
    );
    this.recoveryBridge.attach();
  }

  async rebuild(reason: 'backend-change' | 'device-loss' | 'context-loss'): Promise<void> {
    if (!this.canvas) return;
    const started = performance.now();
    this.recovery = 'pending'; this.emitEvent({ type: 'RESOURCE_LOST', detail: `${reason}: explicit rebuild` });
    const previousBackend = this.backend;
    const generation = ++this.engineGeneration;
    this.detachRecoveryObservers(); this.scene?.dispose(); this.engine?.dispose();
    try {
      const selected = await this.createEngine(this.canvas, this.options.preferWebGpu);
      if (this.disposed || generation !== this.engineGeneration) { selected.engine.dispose(); return; }
      this.canvas = selected.canvas; this.engine = selected.engine; this.backend = selected.backend; this.attachRecoveryObservers(selected.engine); this.createGpuScene();
      const outcome = recoveryOutcome(previousBackend, selected.backend);
      this.recovery = 'usable'; this.emitEvent({ type: 'RECOVERY_RESULT', outcome, detail: `${reason}: retained CPU state restored${outcome === 'FALLBACK' ? ` using ${selected.backend}` : ''}`, latencyMs: performance.now() - started }); this.emitTelemetry();
    } catch { this.recovery = 'failed'; this.emitEvent({ type: 'RECOVERY_RESULT', outcome: 'FAILED', detail: `${reason}: rebuild failed`, latencyMs: performance.now() - started }); this.emitTelemetry(); }
  }

  dispatch(command: RuntimeCommand): Promise<unknown> | unknown {
    switch (command.type) {
      case 'LOAD_SCENE': return this.loadScene(command.scene);
      case 'PATCH_CONTRIBUTION': return this.updateContribution(command.contribution);
      case 'SET_CAMERA':
        if ('focusLy' in command.camera) this.setCamera(command.camera);
        else if (this.state?.kind === 'system') {
          this.state = { ...this.state, camera: command.camera };
          this.applyCamera(command.camera);
          this.emitEvent({ type: 'CAMERA_CHANGED', camera: command.camera });
          this.requestFrame('camera-set');
        }
        return undefined;
      case 'FLY_TO': return this.flyTo(command.target, command.reducedMotion ? 0 : undefined);
      case 'PICK': return this.pick(command.screenX, command.screenY, 'cpu-screen-projection', command.maxCandidates);
      case 'RESIZE': return this.resize(command.width, command.height, command.dpr);
      case 'REBUILD_RESOURCES': return this.rebuild(command.reason);
    }
  }
  snapshot() { return { camera: this.state?.camera ?? null, selection: this.state?.selection ?? [] } as const; }
  private emitTelemetry(cpuFrameMs: number | null = null): void {
    const visibleCount = this.gpuBuffers?.targets.length ?? 0;
    const telemetry = { backend: this.backend, cpuFrameMs, gpuFrameMs: null, streamLatencyMs: this.lastStreamMs, streamTruncated: sourceStreamTruncated(this.state), visibleCount, drawCalls: this.stars ? 1 : 0, resourceCount: this.stars ? 3 : 0, bufferBytes: this.stars ? thinInstanceBufferBytes(visibleCount) : 0, pickLatencyMs: this.lastPickMs, recoveryOutcome: this.recovery, renderedFrames: this.renderedFrames } satisfies RuntimeTelemetry;
    this.options.onTelemetry?.(telemetry);
    this.emitEvent({ type: 'METRICS', cpuFrameMs: telemetry.cpuFrameMs, gpuFrameMs: telemetry.gpuFrameMs, visibleCount: telemetry.visibleCount, drawCalls: telemetry.drawCalls, resources: telemetry.resourceCount, bufferBytes: telemetry.bufferBytes });
  }
  dispose(): void {
    this.disposed = true; this.engineGeneration += 1; this.cancelFlyTo(); this.detachRecoveryObservers();
    this.camera?.detachControl(); this.scene?.dispose(); this.engine?.dispose();
    this.scene = null; this.engine = null; this.camera = null; this.stars = null; this.canvas = null; this.framePending = false; this.gpuBuffers = null; this.pickIndex = null; this.gpuSourceIndices.clear(); this.gpuLodLevel = undefined;
  }

  private disposeStarResources(): void {
    this.stars?.dispose(false, true);
    this.stars = null;
    this.starOriginLy = null;
  }
}

export function defaultCamera(): CameraState { return { focusLy: { x: 0, y: 0, z: 0 }, distanceLy: 40_000, bearingRad: 0, pitchRad: PITCH_MAX, projection: 'orthographic', revision: 0 }; }
export function clampCamera(camera: CameraState): CameraState {
  return { ...camera, distanceLy: Math.max(1, camera.distanceLy), pitchRad: Math.max(PITCH_MIN, Math.min(PITCH_MAX, camera.pitchRad)) };
}

export function freshFallbackCanvas(canvas: HTMLCanvasElement): HTMLCanvasElement {
  const replacement = canvas.cloneNode(true) as HTMLCanvasElement;
  canvas.parentNode?.replaceChild(replacement, canvas);
  return replacement;
}

export function recoveryOutcome(previous: RuntimeBackend, next: RuntimeBackend): 'RECOVERED' | 'FALLBACK' {
  return previous === next ? 'RECOVERED' : 'FALLBACK';
}

/** Bytes uploaded for each thin instance: a 4x4 Float32 matrix plus RGBA Float32 color. */
export function thinInstanceBufferBytes(instanceCount: number): number {
  return Math.max(0, Math.floor(instanceCount)) * (16 + 4) * Float32Array.BYTES_PER_ELEMENT;
}

/** Source delivery telemetry is independent from client-side semantic LOD culling. */
export function sourceStreamTruncated(scene: SpatialSceneContract | null): boolean {
  return scene?.contributions.some((contribution) => contribution.layers.some((layer) => layer.truncated)) ?? false;
}

/** Convert a Babylon camera ray into absolute LY coordinates on the galaxy's XZ plane. */
export function galaxyPlanePointFromRay(ray: Pick<Ray, 'origin' | 'direction'>, originLy: CameraState['focusLy']): { x: number; z: number } | null {
  if (Math.abs(ray.direction.y) <= Number.EPSILON) return null;
  const distance = -ray.origin.y / ray.direction.y;
  if (distance < 0) return null;
  return {
    x: originLy.x + ray.origin.x + ray.direction.x * distance,
    z: originLy.z + ray.origin.z + ray.direction.z * distance,
  };
}

function sameGalaxyCamera(left: CameraState, right: CameraState): boolean {
  return left.projection === right.projection
    && nearlyEqual(left.focusLy.x, right.focusLy.x) && nearlyEqual(left.focusLy.y, right.focusLy.y) && nearlyEqual(left.focusLy.z, right.focusLy.z)
    && nearlyEqual(left.distanceLy, right.distanceLy) && nearlyEqual(left.bearingRad, right.bearingRad) && nearlyEqual(left.pitchRad, right.pitchRad);
}

function sameSystemCamera(left: import('../contracts').SystemCameraState, right: import('../contracts').SystemCameraState): boolean {
  return nearlyEqual(left.semanticDistance, right.semanticDistance) && nearlyEqual(left.bearingRad, right.bearingRad) && nearlyEqual(left.pitchRad, right.pitchRad);
}

function nearlyEqual(left: number, right: number): boolean { return Math.abs(left - right) <= 1e-7; }
