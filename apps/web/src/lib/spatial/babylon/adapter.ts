import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { Engine } from '@babylonjs/core/Engines/engine.js';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { CreateBox } from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import { Scene } from '@babylonjs/core/scene.js';

import type {
  SpatialRendererBackend,
  SpatialRuntime,
  SpatialRuntimeStatusListener,
  SpatialViewport,
} from '../contracts';
import {
  createManagedSpatialRuntime,
  type SpatialBackendSession,
} from '../lifecycle';

const disposeEngine = (engine: AbstractEngine): void => {
  try {
    engine.dispose();
  } catch {
    // Partially initialized engines still need a bounded fallback path.
  }
};

const createDiagnosticScene = (engine: AbstractEngine): Scene => {
  const scene = new Scene(engine);
  scene.clearColor = new Color4(0.015, 0.02, 0.03, 1);

  const camera = new FreeCamera(
    'spatial-foundation-camera',
    new Vector3(0, 0, -5),
    scene,
  );
  camera.setTarget(Vector3.Zero());
  scene.activeCamera = camera;

  const light = new HemisphericLight(
    'spatial-foundation-light',
    new Vector3(0.25, 1, -0.5),
    scene,
  );
  light.intensity = 0.9;

  const marker = CreateBox(
    'spatial-foundation-diagnostic-marker',
    { size: 1.5 },
    scene,
  );
  marker.rotation.set(0.35, 0.65, 0.1);
  const material = new StandardMaterial(
    'spatial-foundation-diagnostic-material',
    scene,
  );
  material.diffuseColor = new Color3(0.28, 0.68, 0.78);
  material.specularColor = Color3.Black();
  marker.material = material;

  return scene;
};

const createSession = (
  engine: AbstractEngine,
  backend: SpatialRendererBackend,
): SpatialBackendSession => {
  let scene: Scene | null = null;
  try {
    scene = createDiagnosticScene(engine);
  } catch (error) {
    disposeEngine(engine);
    throw error;
  }

  return {
    backend,
    resize({ width, height, dpr }: SpatialViewport) {
      engine.setSize(
        Math.max(1, Math.round(width * dpr)),
        Math.max(1, Math.round(height * dpr)),
        true,
      );
    },
    render() {
      scene?.render();
    },
    dispose() {
      const currentScene = scene;
      scene = null;
      try {
        currentScene?.dispose();
      } finally {
        engine.dispose();
      }
    },
  };
};

const createWebGpuSession = async (
  canvas: HTMLCanvasElement,
): Promise<SpatialBackendSession | null> => {
  if (!('gpu' in navigator)) return null;

  const { WebGPUEngine } =
    await import('@babylonjs/core/Engines/webgpuEngine.js');
  if (!(await WebGPUEngine.IsSupportedAsync)) return null;

  const engine = new WebGPUEngine(canvas, {
    antialias: true,
    audioEngine: false,
    powerPreference: 'high-performance',
  });
  try {
    await engine.initAsync();
    return createSession(engine, 'WEBGPU');
  } catch (error) {
    disposeEngine(engine);
    throw error;
  }
};

const createWebGl2Session = (
  canvas: HTMLCanvasElement,
): SpatialBackendSession | null => {
  const context = canvas.getContext('webgl2', {
    alpha: false,
    antialias: true,
    depth: true,
    powerPreference: 'high-performance',
    preserveDrawingBuffer: true,
    stencil: true,
  });
  if (!context) return null;

  const engine = new Engine(
    context,
    true,
    { audioEngine: false, preserveDrawingBuffer: true, stencil: true },
    false,
  );
  return createSession(engine, 'WEBGL2');
};

export interface BabylonRuntimeDependencies {
  createWebGpu(
    canvas: HTMLCanvasElement,
  ): Promise<SpatialBackendSession | null>;
  createWebGl2(canvas: HTMLCanvasElement): SpatialBackendSession | null;
  replaceCanvas(canvas: HTMLCanvasElement): HTMLCanvasElement;
}

const defaultDependencies: BabylonRuntimeDependencies = {
  createWebGpu: createWebGpuSession,
  createWebGl2: createWebGl2Session,
  replaceCanvas(canvas) {
    const replacement = canvas.cloneNode(false) as HTMLCanvasElement;
    canvas.replaceWith(replacement);
    return replacement;
  },
};

export function createBabylonSpatialRuntime(
  canvas: HTMLCanvasElement,
  onStatus: SpatialRuntimeStatusListener,
  dependencies: BabylonRuntimeDependencies = defaultDependencies,
): SpatialRuntime {
  let activeCanvas = canvas;
  return createManagedSpatialRuntime(
    {
      async createWebGpu() {
        try {
          return await dependencies.createWebGpu(activeCanvas);
        } catch (error) {
          // A failed WebGPU initialization may leave its canvas context-bound.
          // WebGL2 therefore receives a fresh equivalent canvas deterministically.
          activeCanvas = dependencies.replaceCanvas(activeCanvas);
          throw error;
        }
      },
      createWebGl2: () => dependencies.createWebGl2(activeCanvas),
    },
    onStatus,
  );
}
