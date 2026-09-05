import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { Engine } from '@babylonjs/core/Engines/engine.js';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import { Matrix, Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { CreateBox } from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import { CreateSphere } from '@babylonjs/core/Meshes/Builders/sphereBuilder.js';
import { CreateTorus } from '@babylonjs/core/Meshes/Builders/torusBuilder.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { Scene } from '@babylonjs/core/scene.js';

import type {
  GalaxySceneContract,
  GalaxySystemPoint,
  GalaxySystemsPayload,
  RuntimeCommand,
  RuntimeCommandDispatchResult,
  RuntimeEvent,
  SpatialRendererBackend,
  SpatialRuntime,
  SpatialRuntimeStatusListener,
  SpatialViewport,
} from '../contracts';
import {
  createManagedSpatialRuntime,
  type SpatialBackendSession,
  type SpatialBackendResourceListener,
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

type ProductScene = Readonly<{
  scene: Scene;
  camera: FreeCamera;
  points: readonly GalaxySystemPoint[];
  starMesh: ReturnType<typeof CreateSphere>;
  selectedMarker: ReturnType<typeof CreateTorus> | null;
  markerSizeLy: number;
}>;

function isGalaxySystemsPayload(value: unknown): value is GalaxySystemsPayload {
  if (!value || typeof value !== 'object' || !('systems' in value))
    return false;
  const systems = (value as { systems?: unknown }).systems;
  return (
    Array.isArray(systems) &&
    systems.every((point) => {
      if (!point || typeof point !== 'object') return false;
      const candidate = point as {
        systemId64?: unknown;
        name?: unknown;
        positionLy?: unknown;
      };
      if (
        typeof candidate.systemId64 !== 'string' ||
        typeof candidate.name !== 'string' ||
        !candidate.positionLy ||
        typeof candidate.positionLy !== 'object'
      ) {
        return false;
      }
      const position = candidate.positionLy as {
        x?: unknown;
        y?: unknown;
        z?: unknown;
      };
      return [position.x, position.y, position.z].every(
        (coordinate) =>
          typeof coordinate === 'number' && Number.isFinite(coordinate),
      );
    })
  );
}

function finderPoints(
  scene: GalaxySceneContract,
): readonly GalaxySystemPoint[] {
  for (const contribution of scene.contributions) {
    if (contribution.owner !== 'FINDER') continue;
    for (const layer of contribution.layers) {
      if (
        layer.id === 'finder-systems' &&
        isGalaxySystemsPayload(layer.payload)
      ) {
        return layer.payload.systems;
      }
    }
  }
  return [];
}

function placeCamera(
  camera: FreeCamera,
  focus: Readonly<{ x: number; y: number; z: number }>,
  distance: number,
): void {
  camera.position.set(
    focus.x + distance * 0.24,
    focus.y + distance * 0.34,
    focus.z - distance,
  );
  camera.setTarget(new Vector3(focus.x, focus.y, focus.z));
  camera.minZ = Math.max(0.01, distance / 100_000);
  camera.maxZ = Math.max(10_000, distance * 8);
}

const createGalaxyScene = (
  engine: AbstractEngine,
  contract: GalaxySceneContract,
): ProductScene => {
  const scene = new Scene(engine);
  scene.clearColor = new Color4(0.008, 0.014, 0.028, 1);
  const points = finderPoints(contract);
  const camera = new FreeCamera('galaxy-camera', Vector3.Zero(), scene);
  placeCamera(camera, contract.camera.focusLy, contract.camera.distanceLy);
  scene.activeCamera = camera;

  const light = new HemisphericLight(
    'galaxy-fill',
    new Vector3(-0.2, 1, -0.3),
    scene,
  );
  light.intensity = 0.35;

  const markerSizeLy = Math.max(0.35, contract.camera.distanceLy * 0.009);
  const starMesh = CreateSphere(
    'finder-system-instances',
    { diameter: markerSizeLy * 1.5, segments: 8 },
    scene,
  );
  const starMaterial = new StandardMaterial('finder-system-material', scene);
  starMaterial.disableLighting = true;
  starMaterial.emissiveColor = new Color3(0.25, 0.78, 0.92);
  starMaterial.diffuseColor = new Color3(0.12, 0.5, 0.68);
  starMesh.material = starMaterial;
  starMesh.thinInstanceEnablePicking = true;
  const matrices = new Float32Array(points.length * 16);
  points.forEach((point, index) => {
    Matrix.Translation(
      point.positionLy.x,
      point.positionLy.y,
      point.positionLy.z,
    ).copyToArray(matrices, index * 16);
  });
  starMesh.thinInstanceSetBuffer('matrix', matrices, 16, true);

  const selectedId =
    contract.selection.find((target) => target.kind === 'system')?.systemId64 ??
    null;
  const selectedPoint = points.find((point) => point.systemId64 === selectedId);
  let selectedMarker: ReturnType<typeof CreateTorus> | null = null;
  if (selectedPoint) {
    selectedMarker = CreateTorus(
      'selected-system-marker',
      {
        diameter: markerSizeLy * 3.4,
        thickness: markerSizeLy * 0.22,
        tessellation: 24,
      },
      scene,
    );
    selectedMarker.position.set(
      selectedPoint.positionLy.x,
      selectedPoint.positionLy.y,
      selectedPoint.positionLy.z,
    );
    selectedMarker.rotation.x = Math.PI / 2;
    const selectedMaterial = new StandardMaterial(
      'selected-system-material',
      scene,
    );
    selectedMaterial.disableLighting = true;
    selectedMaterial.emissiveColor = new Color3(1, 0.58, 0.08);
    selectedMarker.material = selectedMaterial;
  }

  return { scene, camera, points, starMesh, selectedMarker, markerSizeLy };
};

export const subscribeToBabylonResourceEvents = (
  engine: Pick<
    AbstractEngine,
    'onContextLostObservable' | 'onContextRestoredObservable'
  >,
  backend: SpatialRendererBackend,
  listener: SpatialBackendResourceListener,
): (() => void) => {
  const prefix = backend === 'WEBGPU' ? 'webgpu-device' : 'webgl2-context';
  const lostObserver = engine.onContextLostObservable.add(() => {
    listener({ state: 'lost', detail: `${prefix}-lost` });
  });
  const restoredObserver = engine.onContextRestoredObservable.add(() => {
    listener({ state: 'recovered', detail: `${prefix}-restored` });
  });
  let subscribed = true;

  return () => {
    if (!subscribed) return;
    subscribed = false;
    lostObserver.remove();
    restoredObserver.remove();
  };
};

const createSession = (
  engine: AbstractEngine,
  backend: SpatialRendererBackend,
): SpatialBackendSession => {
  let scene: Scene | null = null;
  let product: ProductScene | null = null;
  try {
    scene = createDiagnosticScene(engine);
  } catch (error) {
    disposeEngine(engine);
    throw error;
  }

  return {
    backend,
    subscribeResourceEvents: (listener) =>
      subscribeToBabylonResourceEvents(engine, backend, listener),
    resize({ width, height, dpr }: SpatialViewport) {
      engine.setSize(
        Math.max(1, Math.round(width * dpr)),
        Math.max(1, Math.round(height * dpr)),
        true,
      );
    },
    execute(
      command: Exclude<RuntimeCommand, { type: 'RESIZE' }>,
      emit: (event: RuntimeEvent) => void,
    ): RuntimeCommandDispatchResult {
      if (command.type === 'LOAD_SCENE') {
        if (command.scene.kind !== 'galaxy') {
          return { status: 'unsupported', command: command.type };
        }
        const replacement = createGalaxyScene(engine, command.scene);
        const previous = scene;
        scene = replacement.scene;
        product = replacement;
        previous?.dispose();
        return { status: 'executed' };
      }
      if (command.type === 'FLY_TO') {
        if (command.target.kind !== 'system' || !product) {
          return { status: 'unsupported', command: command.type };
        }
        const targetId = command.target.systemId64;
        const point = product.points.find(
          (candidate) => candidate.systemId64 === targetId,
        );
        if (!point) return { status: 'unsupported', command: command.type };
        const distance = Math.max(12, product.markerSizeLy * 24);
        // This first checkpoint deliberately uses an immediate semantic focus
        // for every preference; there is no hidden motion when reduced motion
        // is requested and no continuous renderer-owned animation state.
        placeCamera(product.camera, point.positionLy, distance);
        emit({ type: 'TRANSITION_FINISHED', target: command.target });
        return { status: 'executed' };
      }
      if (command.type === 'PICK') {
        if (!product) return { status: 'unsupported', command: command.type };
        const canvas = engine.getRenderingCanvas();
        const scaleX = canvas?.clientWidth
          ? engine.getRenderWidth() / canvas.clientWidth
          : 1;
        const scaleY = canvas?.clientHeight
          ? engine.getRenderHeight() / canvas.clientHeight
          : 1;
        const hit = product.scene.pick(
          command.screenX * scaleX,
          command.screenY * scaleY,
        );
        let targetId: string | undefined;
        if (hit?.pickedMesh === product.selectedMarker) {
          targetId = product.points.find((point) =>
            product?.selectedMarker?.position.equalsWithEpsilon(
              new Vector3(
                point.positionLy.x,
                point.positionLy.y,
                point.positionLy.z,
              ),
            ),
          )?.systemId64;
        } else if (
          hit?.pickedMesh === product.starMesh &&
          typeof hit.thinInstanceIndex === 'number' &&
          hit.thinInstanceIndex >= 0
        ) {
          targetId = product.points[hit.thinInstanceIndex]?.systemId64;
        }
        emit({
          type: 'TARGET_PICKED',
          target: targetId
            ? { kind: 'system', systemId64: targetId }
            : undefined,
        });
        return { status: 'executed' };
      }
      return { status: 'unsupported', command: command.type };
    },
    render() {
      scene?.render();
    },
    dispose() {
      const currentScene = scene;
      scene = null;
      product = null;
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
  const options = {
    alpha: false,
    antialias: true,
    depth: true,
    powerPreference: 'high-performance',
    preserveDrawingBuffer: true,
    stencil: true,
  } satisfies WebGLContextAttributes;
  if (!canvas.getContext('webgl2', options)) return null;

  const engine = new Engine(
    canvas,
    true,
    { ...options, audioEngine: false },
    false,
  );
  if (engine.webGLVersion !== 2) {
    disposeEngine(engine);
    return null;
  }
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
