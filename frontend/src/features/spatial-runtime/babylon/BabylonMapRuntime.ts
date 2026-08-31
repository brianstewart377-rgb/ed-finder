import { Engine } from '@babylonjs/core/Engines/engine';
import { WebGPUEngine } from '@babylonjs/core/Engines/webgpuEngine';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine';
import { Scene } from '@babylonjs/core/scene';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
import { Vector3, Matrix } from '@babylonjs/core/Maths/math.vector';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import type { CameraState, MapRuntime, MapRuntimeOptions, PickCandidate, PickStrategy, RuntimeBackend, RuntimeCommand, RuntimeEvent, RuntimeTelemetry, SpatialContribution, SpatialSceneContract, SpatialTarget } from '../contracts';
import { spatialTargetId } from '../contracts';
import { applyRevisionedContribution, normalizeScene, type CompactSceneBuffers } from '../scene-data';
import { cpuSpatialCandidates } from '../picking';
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
  private options: MapRuntimeOptions = { preferWebGpu: true, reducedMotion: false };
  private backend: RuntimeBackend = 'WEBGL2';
  private suspended = false;
  private framePending = false;
  private disposed = false;
  private flyAbort: AbortController | null = null;
  private renderedFrames = 0;
  private recovery: RuntimeTelemetry['recovery'] = 'not-attempted';
  private lastPickMs: number | null = null;
  private recoveryBridge: ResourceRecoveryBridge | null = null;
  private engineGeneration = 0;

  async initialize(canvas: HTMLCanvasElement, options: MapRuntimeOptions): Promise<RuntimeBackend> {
    this.dispose();
    this.disposed = false;
    this.canvas = canvas;
    this.options = options;
    const selected = await this.createEngine(canvas, options.preferWebGpu);
    this.engine = selected.engine;
    this.backend = selected.backend;
    this.attachRecoveryObservers(selected.engine);
    this.createGpuScene();
    this.emitEvent({ type: 'READY', backend: this.backend });
    return this.backend;
  }

  private async createEngine(canvas: HTMLCanvasElement, preferWebGpu: boolean): Promise<{ engine: AbstractEngine; backend: RuntimeBackend }> {
    if (preferWebGpu && 'gpu' in navigator && await WebGPUEngine.IsSupportedAsync) {
      try {
        const engine = new WebGPUEngine(canvas, { antialias: true, adaptToDeviceRatio: false, useLargeWorldRendering: true });
        await engine.initAsync();
        return { engine, backend: 'WEBGPU' };
      } catch {
        // Initialization is completed (or rejected) before any Scene/GPU resource exists.
      }
    }
    const gl = canvas.getContext('webgl2', { antialias: true });
    if (!gl) throw new Error('Stage 27B requires WebGPU or WebGL2');
    return { engine: new Engine(gl, true, { adaptToDeviceRatio: false, useLargeWorldRendering: true }), backend: 'WEBGL2' };
  }

  private createGpuScene(): void {
    if (!this.engine || !this.canvas) return;
    this.scene = new Scene(this.engine, { useFloatingOrigin: true });
    this.scene.clearColor.set(0.002, 0.004, 0.012, 1);
    const cameraState = this.state?.kind === 'galaxy' ? this.state.camera : defaultCamera();
    this.camera = new ArcRotateCamera('semantic-camera', cameraState.bearingRad, cameraState.pitchRad, cameraState.distanceLy, Vector3.Zero(), this.scene);
    this.camera.lowerBetaLimit = PITCH_MIN;
    this.camera.upperBetaLimit = PITCH_MAX;
    this.camera.lowerRadiusLimit = 1;
    this.camera.wheelPrecision = 0.2;
    this.camera.attachControl(this.canvas, true);
    this.camera.onViewMatrixChangedObservable.add(() => this.requestFrame('camera'));
    this.applyCamera(cameraState);
    if (this.buffers) this.rebuildStarResources();
  }

  loadScene(scene: SpatialSceneContract): void {
    this.state = scene;
    this.buffers = normalizeScene(scene);
    this.applyCamera(scene.camera);
    this.rebuildStarResources();
    this.requestFrame('scene-load');
  }

  updateContribution(contribution: SpatialContribution): boolean {
    if (!this.state) return false;
    const result = applyRevisionedContribution(this.state, contribution);
    if (!result.applied) return false;
    this.state = result.scene;
    this.buffers = normalizeScene(result.scene);
    this.rebuildStarResources();
    this.requestFrame('contribution');
    return true;
  }

  private rebuildStarResources(): void {
    if (!this.scene || !this.buffers || !this.state || this.state.kind !== 'galaxy') return;
    this.stars?.dispose(false, true);
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
    const matrices = new Float32Array(this.buffers.targets.length * 16);
    const origin = this.state.camera.focusLy;
    for (let index = 0; index < this.buffers.targets.length; index += 1) {
      Matrix.Translation(
        this.buffers.positionsLy[index * 3]! - origin.x,
        this.buffers.positionsLy[index * 3 + 1]! - origin.y,
        this.buffers.positionsLy[index * 3 + 2]! - origin.z,
      ).copyToArray(matrices, index * 16);
    }
    quad.thinInstanceSetBuffer('matrix', matrices, 16, true);
    const colors = Float32Array.from(this.buffers.colors, (value) => value / 255);
    quad.thinInstanceSetBuffer('color', colors, 4, false);
    this.stars = quad;
  }

  resize(cssWidth: number, cssHeight: number, dpr: number): void {
    if (!this.canvas || !this.engine) return;
    const safeDpr = Math.max(0.5, Math.min(2, dpr));
    this.canvas.width = Math.max(1, Math.round(cssWidth * safeDpr));
    this.canvas.height = Math.max(1, Math.round(cssHeight * safeDpr));
    this.canvas.style.width = `${cssWidth}px`; this.canvas.style.height = `${cssHeight}px`;
    this.engine.resize(); this.requestFrame('resize');
  }

  setCamera(camera: CameraState): void {
    if (!this.state || this.state.kind !== 'galaxy') return;
    this.state = { ...this.state, camera: clampCamera(camera) };
    this.applyCamera(this.state.camera); this.rebuildStarResources(); this.requestFrame('camera-set');
    this.emitEvent({ type: 'CAMERA_CHANGED', camera: this.state.camera });
  }

  private applyCamera(camera: CameraState | import('../contracts').SystemCameraState): void {
    if (!this.camera) return;
    this.camera.alpha = camera.bearingRad;
    this.camera.beta = Math.max(PITCH_MIN, Math.min(PITCH_MAX, camera.pitchRad));
    this.camera.radius = Math.max(1, 'distanceLy' in camera ? camera.distanceLy : camera.semanticDistance);
    this.camera.target.set(0, 0, 0);
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
    this.flyAbort = null; this.emitEvent({ type: 'TRANSITION_FINISHED', target }); return true;
  }

  cancelFlyTo(): void { this.flyAbort?.abort(); this.flyAbort = null; }

  async pick(xCss: number, yCss: number, strategy: PickStrategy): Promise<readonly PickCandidate[]> {
    const start = performance.now();
    let candidates: PickCandidate[] = [];
    if (strategy === 'babylon-instance' && this.scene) {
      const hit = this.scene.pick(xCss, yCss);
      const target = hit?.thinInstanceIndex == null ? null : this.buffers?.targets[hit.thinInstanceIndex];
      if (target) candidates = [{ target, distancePx: 0 }];
    } else if (this.buffers && this.state?.kind === 'galaxy') {
      // ID-buffer candidate is deliberately measurable in this workbench, with CPU
      // identity confirmation. A later bakeoff can replace emulation without moving IDs.
      candidates = cpuSpatialCandidates(this.buffers, this.state.camera.focusLy.x, this.state.camera.focusLy.z, this.state.camera.distanceLy / 20).slice(0, 16);
    }
    this.lastPickMs = performance.now() - start; this.emitTelemetry(); this.emitEvent({ type: 'TARGET_PICKED', target: candidates[0]?.target }); return candidates;
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
    this.recovery = 'pending'; this.emitEvent({ type: 'RESOURCE_LOST', detail: `${reason}: explicit rebuild` });
    const retained = this.state;
    const generation = ++this.engineGeneration;
    this.detachRecoveryObservers(); this.scene?.dispose(); this.engine?.dispose();
    try {
      const selected = await this.createEngine(this.canvas, this.options.preferWebGpu);
      if (this.disposed || generation !== this.engineGeneration) { selected.engine.dispose(); return; }
      this.engine = selected.engine; this.backend = selected.backend; this.attachRecoveryObservers(selected.engine); this.createGpuScene();
      if (retained) this.loadScene(retained);
      this.recovery = 'usable'; this.emitEvent({ type: 'RESOURCE_RECOVERED', detail: `${reason}: retained CPU state restored` }); this.emitTelemetry();
    } catch { this.recovery = 'failed'; this.emitTelemetry(); }
  }

  dispatch(command: RuntimeCommand): Promise<unknown> | unknown {
    switch (command.type) {
      case 'LOAD_SCENE': return this.loadScene(command.scene);
      case 'PATCH_CONTRIBUTION': return this.updateContribution(command.contribution);
      case 'SET_CAMERA': if ('focusLy' in command.camera) this.setCamera(command.camera); else this.applyCamera(command.camera); return undefined;
      case 'FLY_TO': return this.flyTo(command.target, command.reducedMotion ? 0 : undefined);
      case 'PICK': return this.pick(command.screenX, command.screenY, 'babylon-instance');
      case 'RESIZE': return this.resize(command.width, command.height, command.dpr);
      case 'REBUILD_RESOURCES': return this.rebuild(command.reason);
    }
  }
  snapshot() { return { camera: this.state?.camera ?? null, selection: this.state?.kind === 'galaxy' ? this.state.selection : [] } as const; }
  private emitTelemetry(cpuFrameMs: number | null = null): void {
    const telemetry = { backend: this.backend, cpuFrameMs, gpuFrameMs: null, visibleCount: this.buffers?.targets.length ?? 0, drawCalls: this.stars ? 1 : 0, resourceCount: this.stars ? 3 : 0, bufferBytes: this.buffers?.bytes ?? 0, pickLatencyMs: this.lastPickMs, recovery: this.recovery, renderedFrames: this.renderedFrames } satisfies RuntimeTelemetry;
    this.options.onTelemetry?.(telemetry);
    this.emitEvent({ type: 'METRICS', frameMs: cpuFrameMs ?? 0, visible: telemetry.visibleCount, drawCalls: telemetry.drawCalls, resources: telemetry.resourceCount, bufferBytes: telemetry.bufferBytes });
  }
  dispose(): void {
    this.disposed = true; this.engineGeneration += 1; this.cancelFlyTo(); this.detachRecoveryObservers();
    this.camera?.detachControl(); this.scene?.dispose(); this.engine?.dispose();
    this.scene = null; this.engine = null; this.camera = null; this.stars = null; this.canvas = null; this.framePending = false;
  }
}

export function defaultCamera(): CameraState { return { focusLy: { x: 0, y: 0, z: 0 }, distanceLy: 40_000, bearingRad: 0, pitchRad: PITCH_MAX, projection: 'orthographic', revision: 0 }; }
export function clampCamera(camera: CameraState): CameraState {
  return { ...camera, distanceLy: Math.max(1, camera.distanceLy), pitchRad: Math.max(PITCH_MIN, Math.min(PITCH_MAX, camera.pitchRad)) };
}
