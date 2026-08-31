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
import type { MapRuntime, MapRuntimeOptions, PickCandidate, PickStrategy, RuntimeBackend, RuntimeTelemetry, SemanticCameraState, SpatialContribution, SpatialSceneContract, SpatialTargetId } from '../contracts';
import { applyRevisionedContribution, normalizeScene, type CompactSceneBuffers } from '../scene-data';
import { cpuSpatialCandidates } from '../picking';

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
  private backend: RuntimeBackend = 'webgl2';
  private suspended = false;
  private framePending = false;
  private disposed = false;
  private flyAbort: AbortController | null = null;
  private renderedFrames = 0;
  private recovery: RuntimeTelemetry['recovery'] = 'not-attempted';
  private lastPickMs: number | null = null;
  private contextLossHandler: (() => void) | null = null;

  async initialize(canvas: HTMLCanvasElement, options: MapRuntimeOptions): Promise<RuntimeBackend> {
    this.dispose();
    this.disposed = false;
    this.canvas = canvas;
    this.options = options;
    const selected = await this.createEngine(canvas, options.preferWebGpu);
    this.engine = selected.engine;
    this.backend = selected.backend;
    this.createGpuScene();
    const gl = canvas.getContext('webgl2');
    this.contextLossHandler = () => { void this.rebuild('backend-loss'); };
    gl?.canvas.addEventListener('webglcontextrestored', this.contextLossHandler);
    return this.backend;
  }

  private async createEngine(canvas: HTMLCanvasElement, preferWebGpu: boolean): Promise<{ engine: AbstractEngine; backend: RuntimeBackend }> {
    if (preferWebGpu && 'gpu' in navigator && await WebGPUEngine.IsSupportedAsync) {
      try {
        const engine = new WebGPUEngine(canvas, { antialias: true, adaptToDeviceRatio: false, useLargeWorldRendering: true });
        await engine.initAsync();
        return { engine, backend: 'webgpu' };
      } catch {
        // Initialization is completed (or rejected) before any Scene/GPU resource exists.
      }
    }
    const gl = canvas.getContext('webgl2', { antialias: true });
    if (!gl) throw new Error('Stage 27B requires WebGPU or WebGL2');
    return { engine: new Engine(gl, true, { adaptToDeviceRatio: false, useLargeWorldRendering: true }), backend: 'webgl2' };
  }

  private createGpuScene(): void {
    if (!this.engine || !this.canvas) return;
    this.scene = new Scene(this.engine, { useFloatingOrigin: true });
    this.scene.clearColor.set(0.002, 0.004, 0.012, 1);
    const cameraState = this.state?.camera ?? { centerLy: [0, 0, 0] as const, distanceLy: 40_000, yawRadians: 0, pitchRadians: Math.PI / 2, mode: 'top-down' as const };
    this.camera = new ArcRotateCamera('semantic-camera', cameraState.yawRadians, cameraState.pitchRadians, cameraState.distanceLy, Vector3.Zero(), this.scene);
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
    if (!this.scene || !this.buffers || !this.state) return;
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
    const matrices = new Float32Array(this.buffers.targetIds.length * 16);
    const origin = this.state.camera.centerLy;
    for (let index = 0; index < this.buffers.targetIds.length; index += 1) {
      Matrix.Translation(
        this.buffers.positionsLy[index * 3]! - origin[0],
        this.buffers.positionsLy[index * 3 + 1]! - origin[1],
        this.buffers.positionsLy[index * 3 + 2]! - origin[2],
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

  setCamera(camera: SemanticCameraState): void {
    if (!this.state) return;
    this.state = { ...this.state, camera: clampCamera(camera) };
    this.applyCamera(this.state.camera); this.rebuildStarResources(); this.requestFrame('camera-set');
  }

  private applyCamera(camera: SemanticCameraState): void {
    if (!this.camera) return;
    this.camera.alpha = camera.yawRadians;
    this.camera.beta = camera.mode === 'top-down' ? PITCH_MAX : Math.max(PITCH_MIN, Math.min(PITCH_MAX - 0.05, camera.pitchRadians));
    this.camera.radius = Math.max(1, camera.distanceLy);
    this.camera.target.set(0, 0, 0);
  }

  async flyTo(targetId: SpatialTargetId, durationMs = 600): Promise<boolean> {
    const targetIndex = this.buffers?.targetIds.indexOf(targetId) ?? -1;
    if (targetIndex < 0 || !this.state || !this.buffers) return false;
    this.cancelFlyTo();
    const abort = new AbortController(); this.flyAbort = abort;
    const destination = [this.buffers.positionsLy[targetIndex * 3]!, this.buffers.positionsLy[targetIndex * 3 + 1]!, this.buffers.positionsLy[targetIndex * 3 + 2]!] as const;
    const start = this.state.camera.centerLy;
    const boundedDuration = this.options.reducedMotion ? 0 : Math.max(0, Math.min(1_500, durationMs));
    const started = performance.now();
    let complete = false;
    while (!complete) {
      if (abort.signal.aborted) return false;
      const progress = boundedDuration === 0 ? 1 : Math.min(1, (performance.now() - started) / boundedDuration);
      this.setCamera({ ...this.state.camera, centerLy: start.map((value, axis) => value + (destination[axis]! - value) * progress) as unknown as readonly [number, number, number] });
      complete = progress >= 1;
      if (!complete) await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    }
    this.flyAbort = null; return true;
  }

  cancelFlyTo(): void { this.flyAbort?.abort(); this.flyAbort = null; }

  async pick(xCss: number, yCss: number, strategy: PickStrategy): Promise<readonly PickCandidate[]> {
    const start = performance.now();
    let candidates: PickCandidate[] = [];
    if (strategy === 'babylon-instance' && this.scene) {
      const hit = this.scene.pick(xCss, yCss);
      const id = hit?.thinInstanceIndex == null ? null : this.buffers?.targetIds[hit.thinInstanceIndex];
      if (id) candidates = [{ targetId: id, distancePx: 0 }];
    } else if (this.buffers && this.state) {
      // ID-buffer candidate is deliberately measurable in this workbench, with CPU
      // identity confirmation. A later bakeoff can replace emulation without moving IDs.
      candidates = cpuSpatialCandidates(this.buffers, this.state.camera.centerLy[0], this.state.camera.centerLy[2], this.state.camera.distanceLy / 20).slice(0, 16);
    }
    this.lastPickMs = performance.now() - start; this.emitTelemetry(); return candidates;
  }

  suspend(): void { this.suspended = true; }
  resume(): void { this.suspended = false; this.requestFrame('resume'); }
  requestFrame(_reason: string): void {
    if (this.suspended || this.framePending || this.disposed) return;
    this.framePending = true;
    requestAnimationFrame(() => { this.framePending = false; if (this.suspended || !this.scene) return; const started = performance.now(); this.scene.render(); this.renderedFrames += 1; this.emitTelemetry(performance.now() - started); });
  }

  async rebuild(_reason: 'backend-loss' | 'manual'): Promise<void> {
    if (!this.canvas) return;
    this.recovery = 'pending';
    const retained = this.state;
    this.scene?.dispose(); this.engine?.dispose();
    try {
      const selected = await this.createEngine(this.canvas, this.options.preferWebGpu);
      this.engine = selected.engine; this.backend = selected.backend; this.createGpuScene();
      if (retained) this.loadScene(retained);
      this.recovery = 'usable'; this.emitTelemetry();
    } catch { this.recovery = 'failed'; this.emitTelemetry(); }
  }

  snapshot() { return { camera: this.state?.camera ?? { centerLy: [0, 0, 0], distanceLy: 1, yawRadians: 0, pitchRadians: Math.PI / 2, mode: 'top-down' }, selectedTargetId: this.state?.selectedTargetId ?? null } as const; }
  private emitTelemetry(cpuFrameMs: number | null = null): void {
    this.options.onTelemetry?.({ backend: this.backend, cpuFrameMs, gpuFrameMs: null, visibleCount: this.buffers?.targetIds.length ?? 0, drawCalls: this.stars ? 1 : 0, resourceCount: this.stars ? 3 : 0, bufferBytes: this.buffers?.bytes ?? 0, pickLatencyMs: this.lastPickMs, recovery: this.recovery, renderedFrames: this.renderedFrames });
  }
  dispose(): void {
    this.disposed = true; this.cancelFlyTo();
    if (this.contextLossHandler && this.canvas) this.canvas.removeEventListener('webglcontextrestored', this.contextLossHandler);
    this.contextLossHandler = null; this.camera?.detachControl(); this.scene?.dispose(); this.engine?.dispose();
    this.scene = null; this.engine = null; this.camera = null; this.stars = null; this.canvas = null; this.framePending = false;
  }
}

export function clampCamera(camera: SemanticCameraState): SemanticCameraState {
  return { ...camera, distanceLy: Math.max(1, camera.distanceLy), pitchRadians: camera.mode === 'top-down' ? PITCH_MAX : Math.max(PITCH_MIN, Math.min(PITCH_MAX - .05, camera.pitchRadians)) };
}
