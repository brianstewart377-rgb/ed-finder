// === Map Renderer Adapter ===
// ED‑Finder Stage 26B — Renderer‑independent lifecycle, typed interactions,
// measurements with unknown states, camera transitions for three candidates
// with explicit animation specs and completion signaling.
// Imports only emitted relative artifacts.

import type { MapSceneState, CameraState, MapInteractionEvent } from './map-scene-contract';

// ── Measurement Records ──
export interface MeasurementRecord {
  frameTimeP50Ms: number | null;
  frameTimeP95Ms: number | null;
  frameTimeP99Ms: number | null;
  initialLoadMs: number | null;
  clickLatencyMs: number | null;
  memoryUsageMB: number | null;
  compressedBundleBytes: number | null;
  contextLossRecoveryMs: number | null;
  regionCorrectness: number | null;
  overlapHandlingCorrect: boolean | null;
  keyboardWorkflowCorrect: boolean | null;
  scenarioResultsPassed: number | null;
  gpuFrameTimeMs: number | null;
}

export type EnvironmentRecord = {
  browser: string;
  os: string;
  viewportWidth: number;
  viewportHeight: number;
  candidateId: string;
  datasetSize: 100_000 | 500_000;
  timestamp: string;
};

export type DecisionLog = {
  environment: EnvironmentRecord;
  measurements: MeasurementRecord;
  scenarioStatuses: Record<string, 'pass' | 'fail' | 'unknown'>;
  legalConclusion: 'unresolved';
  notes: string;
};

// ── Renderer Candidate IDs ──
export type RendererCandidateId = 'deckgl-orbit' | 'deckgl-ortho' | 'threejs-r3f';

// ── Camera Mapping per Candidate ──
export function pixelsPerLy(camera: CameraState): number {
  if (!Number.isFinite(camera.zoom) || camera.zoom <= 0) {
    throw new Error('Camera zoom must be a finite LY-per-pixel value greater than zero');
  }
  return 1 / camera.zoom;
}

export function toDeckZoom(camera: CameraState): number {
  // deck.gl zoom 0 maps one world unit to one pixel; each +1 doubles scale.
  return Math.log2(pixelsPerLy(camera));
}

export function toDeckOrbitView(camera: CameraState): Record<string, unknown> {
  return {
    target: [camera.center.x, camera.center.z, 0],
    zoom: toDeckZoom(camera),
    rotationOrbit: camera.bearingDeg,
    // OrbitView rotationX=90 is top-down; common pitch tilts away from it.
    rotationX: 90 - camera.pitchDeg,
    minZoom: 0.05,
    maxZoom: 60,
  };
}

export function toDeckOrthoView(camera: CameraState): Record<string, unknown> {
  return {
    target: [camera.center.x, camera.center.z, 0],
    zoom: toDeckZoom(camera),
  };
}

export function toThreeJSR3F(camera: CameraState): Record<string, unknown> {
  return {
    projection: 'orthographic',
    position: [camera.center.x, camera.center.z, 1000],
    rotation: [camera.pitchDeg * Math.PI / 180, 0, -camera.bearingDeg * Math.PI / 180],
    zoom: pixelsPerLy(camera),
  };
}

// ── Camera Transition Specifications per Candidate ──

// Deck.gl OrbitView: built‑in transitionDuration.
export function createDeckOrbitTransition(target: CameraState, durationMs: number): { viewState: Record<string, unknown>; transitionDuration: number } {
  return {
    viewState: toDeckOrbitView(target),
    transitionDuration: durationMs,
  };
}
// State machine wrapping OrbitView's imperative transition API.
export class DeckOrbitTransitionMachine {
  private _disposed = false;
  private _resolve: ((v: CameraState) => void) | null = null;
  private _target: CameraState | null = null;
  private _current: CameraState | null = null;

  start(target: CameraState, durationMs: number, currentCamera: CameraState): Promise<CameraState> {
    if (this._disposed) throw new Error('Disposed');
    this._current = currentCamera;
    this._target = target;
    return new Promise<CameraState>((resolve) => {
      this._resolve = resolve;
      if (durationMs === 0) {
        this._current = target;
        this._resolve(target);
        this._resolve = null;
        this._target = null;
      }
    });
  }
  tick(_elapsedMs: number, _deltaMs: number): CameraState | null {
    return null; // real implementation would interpolate
  }
  complete(): void {
    if (this._resolve && this._target) {
      this._current = this._target;
      this._resolve(this._target);
      this._resolve = null;
      this._target = null;
    }
  }
  cancel(): void {
    if (this._resolve) {
      this._resolve(this._current!);
      this._resolve = null;
      this._target = null;
    }
  }
  retarget(newTarget: CameraState, newDurationMs: number): void {
    if (this._target) {
      this._target = newTarget;
      if (newDurationMs === 0) {
        this._current = newTarget;
        this._resolve?.(newTarget);
        this._resolve = null;
        this._target = null;
      }
    } else {
      throw new Error('Cannot retarget when idle');
    }
  }
  contextLost(): void { this._resolve = null; this._target = null; this._current = null; }
  recoverContext(_camera: CameraState): void { /* ready */ }
  dispose(): void { this._disposed = true; this._resolve = null; }
  get isDisposed(): boolean { return this._disposed; }
  get lastApplied(): CameraState | null { return this._current; }
}

// Deck.gl OrthographicView: explicit lerp state machine.
export class DeckOrthoTransitionMachine {
  private _disposed = false;
  private _resolve: ((v: CameraState) => void) | null = null;
  private _from: CameraState | null = null;
  private _to: CameraState | null = null;
  private _startTime: number | null = null;
  private _durationMs: number | null = null;
  private _lastApplied: CameraState | null = null;

  start(from: CameraState, to: CameraState, durationMs: number): Promise<CameraState> {
    if (this._disposed) throw new Error('Disposed');
    this._from = from;
    this._to = to;
    this._durationMs = durationMs;
    this._startTime = null;
    this._lastApplied = from;
    return new Promise<CameraState>((resolve) => {
      this._resolve = resolve;
      if (durationMs === 0) {
        this._lastApplied = to;
        this._resolve(to);
        this._resolve = null;
        this._startTime = 0;
      }
    });
  }
  tick(currentTime: number): CameraState | null {
    if (this._disposed || !this._resolve || !this._from || !this._to || this._durationMs == null) return null;
    if (this._startTime === null) this._startTime = currentTime;
    if (this._durationMs === 0) {
      this._lastApplied = this._to;
      this._resolve(this._to);
      this._resolve = null;
      return this._to;
    }
    const elapsed = currentTime - this._startTime;
    const t = Math.min(elapsed / this._durationMs, 1);
    const interp: CameraState = {
      center: {
        x: this._from.center.x + (this._to.center.x - this._from.center.x) * t,
        z: this._from.center.z + (this._to.center.z - this._from.center.z) * t,
      },
      zoom: this._from.zoom + (this._to.zoom - this._from.zoom) * t,
      pitchDeg: this._from.pitchDeg + (this._to.pitchDeg - this._from.pitchDeg) * t,
      bearingDeg: this._from.bearingDeg + (this._to.bearingDeg - this._from.bearingDeg) * t,
    };
    if (t >= 1) {
      this._lastApplied = this._to;
      this._resolve(this._to);
      this._resolve = null;
      return this._to;
    }
    this._lastApplied = interp;
    return interp;
  }
  cancel(): void {
    if (this._resolve) {
      this._resolve(this._lastApplied!);
      this._resolve = null;
    }
  }
  retarget(newTarget: CameraState, newDurationMs: number): void {
    if (this._resolve && this._lastApplied) {
      this._from = this._lastApplied;
      this._to = newTarget;
      this._durationMs = newDurationMs;
      this._startTime = null;
    } else {
      throw new Error('Cannot retarget when idle');
    }
  }
  contextLost(): void { this._resolve = null; this._from = null; this._to = null; this._lastApplied = null; }
  recoverContext(_camera: CameraState): void { /* ready */ }
  dispose(): void { this._disposed = true; this._resolve = null; }
  get isDisposed(): boolean { return this._disposed; }
  get lastApplied(): CameraState | null { return this._lastApplied; }
}

// ── R3FCameraTransitionMachine ──
type EasingFunction = (t: number) => number;

type TransitionState = {
  phase: 'active';
  from: CameraState;
  to: CameraState;
  startTime: number | null;
  durationMs: number;
  easing: EasingFunction;
  lastApplied: CameraState;
  resolve: (value: CameraState) => void;
} | null;

export class R3FCameraTransitionMachine {
  private state: TransitionState = null;
  private _disposed = false;
  private _currentCamera: CameraState | null = null;

  // Set the initial camera before any transition starts.
  initCamera(camera: CameraState): void {
    if (this._disposed) throw new Error('Disposed');
    this._currentCamera = camera;
  }

  start(target: CameraState, durationMs: number, easing: EasingFunction = (t) => t): Promise<CameraState> {
    if (this._disposed) throw new Error('Transition machine disposed');
    const from = this.state?.lastApplied ?? this._currentCamera ?? target;
    return new Promise<CameraState>((resolve) => {
      this.state = {
        phase: 'active',
        from,
        to: target,
        startTime: null,
        durationMs,
        easing,
        lastApplied: from,
        resolve,
      };
    });
  }

  tick(currentTime: number): CameraState | null {
    if (this._disposed) return null;
    if (!this.state || this.state.phase !== 'active') return null;

    if (this.state.startTime === null) {
      this.state.startTime = currentTime;
      if (this.state.durationMs === 0) {
        this.state.lastApplied = this.state.to;
        const cam = this.state.to;
        this._currentCamera = cam;
        this.state.resolve(cam);
        this.state = null;
        return cam;
      }
    }

    const elapsed = currentTime - this.state.startTime;
    const raw = Math.min(elapsed / this.state.durationMs, 1);
    const t = this.state.easing(raw);

    const from = this.state.from;
    const to = this.state.to;
    const interpolated: CameraState = {
      center: {
        x: from.center.x + (to.center.x - from.center.x) * t,
        z: from.center.z + (to.center.z - from.center.z) * t,
      },
      zoom: from.zoom + (to.zoom - from.zoom) * t,
      pitchDeg: from.pitchDeg + (to.pitchDeg - from.pitchDeg) * t,
      bearingDeg: from.bearingDeg + (to.bearingDeg - from.bearingDeg) * t,
    };

    if (raw >= 1) {
      this.state.lastApplied = to;
      this._currentCamera = to;
      this.state.resolve(to);
      this.state = null;
      return to;
    }

    this.state.lastApplied = interpolated;
    this._currentCamera = interpolated;
    return interpolated;
  }

  cancel(): void {
    if (this._disposed || !this.state) return;
    const last = this.state.lastApplied;
    this._currentCamera = last;
    this.state.resolve(last);
    this.state = null;
  }

  retarget(newTarget: CameraState, newDurationMs: number): void {
    if (this._disposed) return;
    if (!this.state) throw new Error('Cannot retarget when idle');
    this.state.from = this.state.lastApplied;
    this.state.to = newTarget;
    this.state.startTime = null;
    this.state.durationMs = newDurationMs;
  }

  contextLost(): void {
    if (this._disposed) return;
    if (this.state) {
      this._currentCamera = this.state.lastApplied;
      this.state.resolve(this.state.lastApplied);
    }
    this.state = null;
  }

  recoverContext(): void {
    if (this._disposed) return;
  }

  dispose(): void {
    if (this._disposed) return;
    this.state = null;
    this._disposed = true;
  }

  get isDisposed(): boolean {
    return this._disposed;
  }

  get lastApplied(): CameraState | null {
    return this.lastAppliedCamera;
  }

  get transitionPhase(): 'active' | 'idle' {
    return this.state ? 'active' : 'idle';
  }

  get lastAppliedCamera(): CameraState | null {
    return this.state?.lastApplied ?? this._currentCamera;
  }
}

// ── Renderer‑Independent Adapter Contract ──
export interface MapRendererAdapter {
  mount(container: HTMLElement): void;
  update(scene: MapSceneState): void;
  resize(width: number, height: number): void;
  deliverInteraction(event: MapInteractionEvent): void;
  measure(): MeasurementRecord;
  contextLost(): void;
  recoverContext(container: HTMLElement): void;
  startCameraTransition(target: CameraState, durationMs: number): Promise<CameraState>;
  cancelCameraTransition(): void;
  retargetCameraTransition(target: CameraState, durationMs: number): void;
  dispose(): void;
}

// ── Concrete Adapter (no‑op; replaced at bake‑off) ──
export class NoopMapRendererAdapter implements MapRendererAdapter {
  private _disposed = false;
  mount(_container: HTMLElement): void {}
  update(_scene: MapSceneState): void {}
  resize(_width: number, _height: number): void {}
  deliverInteraction(_event: MapInteractionEvent): void {}
  measure(): MeasurementRecord {
    return {
      frameTimeP50Ms: null,
      frameTimeP95Ms: null,
      frameTimeP99Ms: null,
      initialLoadMs: null,
      clickLatencyMs: null,
      memoryUsageMB: null,
      compressedBundleBytes: null,
      contextLossRecoveryMs: null,
      regionCorrectness: null,
      overlapHandlingCorrect: null,
      keyboardWorkflowCorrect: null,
      scenarioResultsPassed: null,
      gpuFrameTimeMs: null,
    };
  }
  contextLost(): void {}
  recoverContext(_container: HTMLElement): void {}
  async startCameraTransition(_target: CameraState, _durationMs: number): Promise<CameraState> { return _target; }
  cancelCameraTransition(): void {}
  retargetCameraTransition(_target: CameraState, _durationMs: number): void {}
  dispose(): void { this._disposed = true; }
}
