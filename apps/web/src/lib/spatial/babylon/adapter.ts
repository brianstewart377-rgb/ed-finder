import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { Camera } from '@babylonjs/core/Cameras/camera.js';
import '@babylonjs/core/Culling/ray.js';
import { Engine } from '@babylonjs/core/Engines/engine.js';
import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight.js';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color.js';
import {
  Matrix,
  Quaternion,
  Vector3,
} from '@babylonjs/core/Maths/math.vector.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { ImageProcessingConfiguration } from '@babylonjs/core/Materials/imageProcessingConfiguration.js';
import { GlowLayer } from '@babylonjs/core/Layers/glowLayer.js';
import { CreateBox } from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import { CreateLineSystem } from '@babylonjs/core/Meshes/Builders/linesBuilder.js';
import { CreateSphere } from '@babylonjs/core/Meshes/Builders/sphereBuilder.js';
import { CreateTorus } from '@babylonjs/core/Meshes/Builders/torusBuilder.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData.js';
import { Scene } from '@babylonjs/core/scene.js';

import type {
  CameraState,
  BodyVisualDescriptor,
  GalaxySceneContract,
  GalaxySystemPoint,
  GalaxySystemsPayload,
  RenderedLayerReceipt,
  RuntimeCommand,
  RuntimeCommandDispatchResult,
  RuntimeEvent,
  SpatialContribution,
  SpatialRendererBackend,
  SpatialRuntime,
  SpatialRuntimeStatusListener,
  SpatialTarget,
  SpatialViewport,
  SystemCameraState,
  SystemSceneContract,
} from '../contracts';
import {
  GALAXY_CAMERA_FOV_RAD,
  galaxyCameraPose,
  normalizeGalaxyCamera,
  interpolateGalaxyCamera,
  focusGalaxyCamera,
} from '../galaxy-camera';
import {
  galaxyReferenceGrid,
  type GalaxyGridLine,
  type GalaxyReferenceGridSpec,
} from '../galaxy-grid';
import {
  catalogueDensitySceneLayer,
  type CatalogueDensitySceneLayer,
} from '../galaxy-density';
import {
  COMMANDER_HISTORY_LAYER_ID,
  type CommanderHistoryPayload,
  type CommanderVisitPoint,
} from '../commander-history';
import {
  GALAXY_NEBULAE_LAYER_ID,
  type GalaxyNebulaePayload,
} from '../galaxy-nebulae';
import { createCatalogueDensityMesh } from './catalogue-density';
import {
  buildGalaxyRegionFillGeometry,
  findGalaxyRegionAt,
  galaxyRegionsSceneLayer,
  type GalaxyRegionMapSource,
  type GalaxyRegionsSceneLayer,
} from '../galaxy-regions';
import {
  createManagedSpatialRuntime,
  type SpatialBackendSession,
  type SpatialBackendResourceListener,
} from '../lifecycle';
import {
  stellarPresentation,
  type StellarPresentation,
} from '../stellar-presentation';
import { systemBodyLayout, type SystemBodyLayout } from '../system-scene';

const disposeEngine = (engine: AbstractEngine): void => {
  try {
    engine.dispose();
  } catch {
    // Partially initialized engines still need a bounded fallback path.
  }
};

const BABYLON_SCENE_WARMUP_FRAMES = 3;
// Region fills stay subordinate to factual stellar density, but interaction
// must remain unmistakable at whole-Galaxy scale. The previous 0.14 hover
// alpha was technically different yet visually disappeared behind the atlas
// rails on real displays.
const REGION_BASE_ALPHA = 0.065;
const REGION_SELECTED_ALPHA = 0.34;
const REGION_HOVERED_ALPHA = 0.28;

export function galaxyStarMarkerSizeLy(distanceLy: number): number {
  if (!Number.isFinite(distanceLy) || distanceLy <= 0) {
    throw new RangeError('Galaxy star marker distance must be positive');
  }
  // Roughly four screen pixels at ordinary desktop heights. The position stays
  // in exact light years; only the non-factual presentation radius is scaled.
  return Math.max(0.008, distanceLy * 0.0038);
}

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

export type BabylonGalaxyProduct = Readonly<{
  scene: Scene;
  camera: FreeCamera;
  cameraState: CameraState;
  points: readonly GalaxySystemPoint[];
  starMesh: ReturnType<typeof CreateSphere>;
  starVertexPositions: Float32Array;
  starInstanceMatrices: Float32Array;
  starInstanceColours: Float32Array;
  stellarPresentations: readonly StellarPresentation[];
  stellarAccentMeshes: readonly Mesh[];
  densityMesh: Mesh | null;
  commanderHistoryMesh: ReturnType<typeof CreateSphere> | null;
  nebulaMesh: ReturnType<typeof CreateSphere> | null;
  regionBoundaryMesh: ReturnType<typeof CreateLineSystem> | null;
  regionFillMeshes: readonly GalaxyRegionFillMesh[];
  regionLookup: GalaxyRegionMapSource | null;
  referenceGrid: BabylonGalaxyReferenceGrid;
  visualGlow: GlowLayer;
  selectedMarker: ReturnType<typeof CreateTorus> | null;
  selectedSystemId64: string | null;
  selectedRegionId: number | null;
  markerSizeLy: number;
  renderedLayers: readonly RenderedLayerReceipt[];
}>;

export type BabylonSystemBodyMesh = Readonly<{
  layout: SystemBodyLayout;
  mesh: ReturnType<typeof CreateSphere>;
  ringMeshes: readonly ReturnType<typeof CreateTorus>[];
}>;

export type BabylonSystemProduct = Readonly<{
  scene: Scene;
  camera: FreeCamera;
  cameraState: SystemCameraState;
  contract: SystemSceneContract;
  bodies: readonly BabylonSystemBodyMesh[];
  orbitMesh: ReturnType<typeof CreateLineSystem> | null;
  visualGlow: GlowLayer;
  renderedLayers: readonly RenderedLayerReceipt[];
}>;

export type BabylonGalaxyReferenceGrid = Readonly<{
  spec: GalaxyReferenceGridSpec;
  minorMesh: ReturnType<typeof CreateLineSystem> | null;
  majorMesh: ReturnType<typeof CreateLineSystem> | null;
  axisMesh: ReturnType<typeof CreateLineSystem> | null;
}>;

export type GalaxyRegionFillMesh = Readonly<{
  regionId: number;
  regionName: string;
  mesh: Mesh;
  material: StandardMaterial;
}>;

type GalaxySystemsSceneLayer = Readonly<{
  contributionId: string;
  contributionRevision: number;
  layerId: 'finder-systems' | 'catalogue-systems';
  layerVersion: number;
  representation:
    'AUTHORITATIVE' | 'DERIVED' | 'PLANNED' | 'SCHEMATIC' | 'AMBIENT';
  points: readonly GalaxySystemPoint[];
}>;

type CommanderHistorySceneLayer = Readonly<{
  contributionId: string;
  contributionRevision: number;
  layerVersion: number;
  representation: 'DERIVED';
  truncated: boolean;
  payload: CommanderHistoryPayload;
}>;

type GalaxyNebulaeSceneLayer = Readonly<{
  contributionId: string;
  contributionRevision: number;
  layerVersion: number;
  representation: 'AMBIENT';
  payload: GalaxyNebulaePayload;
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

function galaxySystemsSceneLayers(
  scene: GalaxySceneContract,
): readonly GalaxySystemsSceneLayer[] {
  const accepted: GalaxySystemsSceneLayer[] = [];
  for (const contribution of scene.contributions) {
    if (contribution.owner !== 'FINDER' && contribution.owner !== 'CATALOGUE')
      continue;
    for (const layer of contribution.layers) {
      const acceptedLayer =
        (contribution.owner === 'FINDER' && layer.id === 'finder-systems') ||
        (contribution.owner === 'CATALOGUE' &&
          layer.id === 'catalogue-systems');
      if (acceptedLayer && isGalaxySystemsPayload(layer.payload)) {
        if (layer.targetCount !== layer.payload.systems.length) {
          throw new Error(
            'Finder system targetCount must equal its accepted point count',
          );
        }
        accepted.push({
          contributionId: contribution.id,
          contributionRevision: contribution.revision,
          layerId: layer.id as 'finder-systems' | 'catalogue-systems',
          layerVersion: layer.version,
          representation: layer.representation,
          points: layer.payload.systems,
        });
      }
    }
  }
  return accepted;
}

function uniqueGalaxySystemPoints(
  layers: readonly GalaxySystemsSceneLayer[],
): readonly GalaxySystemPoint[] {
  const points = new Map<string, GalaxySystemPoint>();
  for (const layer of layers) {
    for (const point of layer.points) {
      // Finder results carry the richer summary and are intentionally ordered
      // before the viewport catalogue layer.
      if (!points.has(point.systemId64)) points.set(point.systemId64, point);
    }
  }
  return [...points.values()];
}

function isCommanderHistoryPayload(
  value: unknown,
): value is CommanderHistoryPayload {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<CommanderHistoryPayload>;
  return (
    candidate.source === 'journal-log' &&
    (candidate.mode === 'markers' || candidate.mode === 'density') &&
    Array.isArray(candidate.points) &&
    candidate.points.every((point) => {
      if (!point || typeof point !== 'object') return false;
      const visit = point as Partial<CommanderVisitPoint>;
      return (
        !!visit.positionLy &&
        [visit.positionLy.x, visit.positionLy.y, visit.positionLy.z].every(
          (coordinate) =>
            typeof coordinate === 'number' && Number.isFinite(coordinate),
        ) &&
        Number.isSafeInteger(visit.visitCount) &&
        (visit.visitCount ?? 0) > 0 &&
        typeof visit.firstVisitedAt === 'string' &&
        typeof visit.lastVisitedAt === 'string' &&
        (visit.completionState === 'complete' ||
          visit.completionState === 'partial')
      );
    })
  );
}

function commanderHistorySceneLayer(
  scene: GalaxySceneContract,
): CommanderHistorySceneLayer | null {
  for (const contribution of scene.contributions) {
    if (contribution.owner !== 'COMMANDER_HISTORY') continue;
    for (const layer of contribution.layers) {
      if (
        layer.id === COMMANDER_HISTORY_LAYER_ID &&
        layer.representation === 'DERIVED' &&
        isCommanderHistoryPayload(layer.payload)
      ) {
        if (layer.targetCount !== layer.payload.points.length) {
          throw new Error(
            'Commander history targetCount must equal its accepted point count',
          );
        }
        return {
          contributionId: contribution.id,
          contributionRevision: contribution.revision,
          layerVersion: layer.version,
          representation: 'DERIVED',
          truncated: layer.truncated,
          payload: layer.payload,
        };
      }
    }
  }
  return null;
}

function isGalaxyNebulaePayload(value: unknown): value is GalaxyNebulaePayload {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<GalaxyNebulaePayload>;
  return (
    typeof candidate.sourceUrl === 'string' &&
    typeof candidate.attribution === 'string' &&
    typeof candidate.rightsNotice === 'string' &&
    typeof candidate.usageBasis === 'string' &&
    typeof candidate.sourceByteCount === 'number' &&
    typeof candidate.sourceSha256 === 'string' &&
    Array.isArray(candidate.nebulae) &&
    candidate.nebulae.every(
      (nebula) =>
        typeof nebula.id === 'string' &&
        (nebula.kind === 'nebula' || nebula.kind === 'planetary-nebula') &&
        nebula.positionLy.representation === 'AUTHORITATIVE' &&
        [
          nebula.positionLy.value.x,
          nebula.positionLy.value.y,
          nebula.positionLy.value.z,
        ].every(Number.isFinite),
    )
  );
}

function galaxyNebulaeSceneLayer(
  scene: GalaxySceneContract,
): GalaxyNebulaeSceneLayer | null {
  for (const contribution of scene.contributions) {
    if (contribution.owner !== 'CATALOGUE') continue;
    for (const layer of contribution.layers) {
      if (
        layer.id === GALAXY_NEBULAE_LAYER_ID &&
        layer.representation === 'AMBIENT' &&
        isGalaxyNebulaePayload(layer.payload)
      ) {
        if (layer.targetCount !== layer.payload.nebulae.length) {
          throw new Error(
            'Galaxy nebula targetCount must equal its accepted landmark count',
          );
        }
        return {
          contributionId: contribution.id,
          contributionRevision: contribution.revision,
          layerVersion: layer.version,
          representation: 'AMBIENT',
          payload: layer.payload,
        };
      }
    }
  }
  return null;
}

export function applyGalaxyCamera(
  camera: FreeCamera,
  state: CameraState,
): void {
  const pose = galaxyCameraPose(state);
  const distance = state.distanceLy;
  camera.position.set(pose.positionLy.x, pose.positionLy.y, pose.positionLy.z);
  camera.upVector.set(pose.up.x, pose.up.y, pose.up.z);
  // TargetCamera.setTarget nudges an exact pole and drops roll. Construct the
  // orientation from our explicit basis to preserve top-down bearing and LY.
  const forward = new Vector3(pose.targetLy.x, pose.targetLy.y, pose.targetLy.z)
    .subtract(camera.position)
    .normalize();
  camera.rotationQuaternion = Quaternion.FromRotationMatrix(
    Matrix.LookAtLH(Vector3.Zero(), forward, camera.upVector).invert(),
  );
  camera.updateUpVectorFromRotation = true;
  camera.fov = GALAXY_CAMERA_FOV_RAD;
  camera.mode =
    state.projection === 'orthographic'
      ? Camera.ORTHOGRAPHIC_CAMERA
      : Camera.PERSPECTIVE_CAMERA;
  const engine = camera.getEngine();
  const halfHeight = distance * Math.tan(camera.fov / 2);
  const halfWidth =
    (halfHeight * engine.getRenderWidth()) /
    Math.max(1, engine.getRenderHeight());
  camera.orthoLeft = -halfWidth;
  camera.orthoRight = halfWidth;
  camera.orthoBottom = -halfHeight;
  camera.orthoTop = halfHeight;
  camera.minZ = Math.max(0.01, distance / 100_000);
  camera.maxZ = Math.max(10_000, distance * 8);
}

function createFadedGridLines(
  scene: Scene,
  name: string,
  lines: readonly GalaxyGridLine[],
  colour: Color3,
  centreAlpha: number,
): ReturnType<typeof CreateLineSystem> | null {
  if (lines.length === 0) return null;
  const edgeAlpha = centreAlpha * 0.12;
  const mesh = CreateLineSystem(
    name,
    {
      lines: lines.map((line) =>
        line.map((point) => new Vector3(point.x, point.y, point.z)),
      ),
      colors: lines.map(() => [
        new Color4(colour.r, colour.g, colour.b, edgeAlpha),
        new Color4(colour.r, colour.g, colour.b, centreAlpha),
        new Color4(colour.r, colour.g, colour.b, edgeAlpha),
      ]),
      updatable: false,
    },
    scene,
  );
  mesh.isPickable = false;
  mesh.renderingGroupId = 0;
  return mesh;
}

function createGalaxyReferenceGrid(
  scene: Scene,
  camera: CameraState,
): BabylonGalaxyReferenceGrid {
  const engine = scene.getEngine();
  const spec = galaxyReferenceGrid(camera, {
    width: Math.max(1, engine.getRenderWidth()),
    height: Math.max(1, engine.getRenderHeight()),
  });
  const minorMesh = createFadedGridLines(
    scene,
    'galaxy-reference-grid-minor',
    spec.minorLines,
    new Color3(0.045, 0.2, 0.27),
    0.12,
  );
  const majorMesh = createFadedGridLines(
    scene,
    'galaxy-reference-grid-major',
    spec.majorLines,
    new Color3(0.08, 0.37, 0.48),
    0.25,
  );
  const axisMesh = createFadedGridLines(
    scene,
    'galaxy-reference-grid-axes',
    spec.axisLines,
    new Color3(0.78, 0.45, 0.1),
    0.46,
  );
  const metadata = {
    spatialLayer: {
      id: 'galaxy-reference-grid',
      representation: 'SCHEMATIC',
      nominalPlaneY: spec.nominalPlaneY,
      renderPlaneY: spec.renderPlaneY,
      minorStepLy: spec.minorStepLy,
      majorStepLy: spec.majorStepLy,
      cameraDependentGeometry: true,
      affectsSystemPositions: false,
    },
  };
  if (minorMesh) minorMesh.metadata = metadata;
  if (majorMesh) majorMesh.metadata = metadata;
  if (axisMesh) axisMesh.metadata = metadata;
  return { spec, minorMesh, majorMesh, axisMesh };
}

function disposeGalaxyReferenceGrid(grid: BabylonGalaxyReferenceGrid): void {
  grid.minorMesh?.dispose();
  grid.majorMesh?.dispose();
  grid.axisMesh?.dispose();
}

function refreshGalaxyReferenceGrid(
  product: BabylonGalaxyProduct,
  camera: CameraState,
): BabylonGalaxyReferenceGrid {
  const candidate = galaxyReferenceGrid(camera, {
    width: Math.max(1, product.scene.getEngine().getRenderWidth()),
    height: Math.max(1, product.scene.getEngine().getRenderHeight()),
  });
  if (candidate.key === product.referenceGrid.spec.key) {
    return product.referenceGrid;
  }
  disposeGalaxyReferenceGrid(product.referenceGrid);
  return createGalaxyReferenceGrid(product.scene, camera);
}

function createGalaxyRegionBoundaryMesh(
  scene: Scene,
  regions: GalaxyRegionsSceneLayer | null,
): ReturnType<typeof CreateLineSystem> | null {
  if (!regions || regions.payload.boundaries.length === 0) return null;
  const mesh = CreateLineSystem(
    'authoritative-galaxy-region-boundaries',
    {
      lines: regions.payload.boundaries.map((boundary) => [
        new Vector3(
          boundary.sourceLy.x,
          boundary.sourceLy.y,
          boundary.sourceLy.z,
        ),
        new Vector3(
          boundary.targetLy.x,
          boundary.targetLy.y,
          boundary.targetLy.z,
        ),
      ]),
      updatable: false,
    },
    scene,
  );
  mesh.color = new Color3(0.16, 0.62, 0.88);
  mesh.alpha = 0.46;
  mesh.isPickable = false;
  mesh.renderingGroupId = 1;
  mesh.metadata = {
    spatialLayer: {
      id: 'galaxy-regions',
      representation: 'AUTHORITATIVE',
      sourceSha256: regions.payload.source.sha256,
      regionCount: regions.payload.regions.length,
      boundaryCount: regions.payload.boundaries.length,
      lookupWidth: regions.payload.source.width,
      lookupHeight: regions.payload.source.height,
      pickableRegionCount: regions.payload.regions.length,
    },
  };
  return mesh;
}

function regionBaseColor(regionId: number): Color3 {
  const tones = [
    new Color3(0.045, 0.19, 0.28),
    new Color3(0.075, 0.14, 0.28),
    new Color3(0.035, 0.22, 0.2),
    new Color3(0.11, 0.14, 0.27),
  ] as const;
  return tones[regionId % tones.length]!.clone();
}

function selectedGalaxyRegionId(contract: GalaxySceneContract): number | null {
  const target = contract.selection.find(
    (candidate) => candidate.kind === 'region',
  );
  if (!target || target.kind !== 'region') return null;
  const regionId = Number(target.id);
  return Number.isSafeInteger(regionId) && regionId >= 1 && regionId <= 42
    ? regionId
    : null;
}

function selectedGalaxySystemId64(
  contract: GalaxySceneContract,
): string | null {
  const target = contract.selection.find(
    (candidate) => candidate.kind === 'system',
  );
  return target?.kind === 'system' ? target.systemId64 : null;
}

function createGalaxyRegionFillMeshes(
  scene: Scene,
  regions: GalaxyRegionsSceneLayer | null,
  selectedRegionId: number | null,
): readonly GalaxyRegionFillMesh[] {
  if (!regions) return [];
  return buildGalaxyRegionFillGeometry(regions.payload.lookup).map(
    (geometry) => {
      const { id: regionId, name: regionName } = geometry.region;
      const mesh = new Mesh(
        `authoritative-galaxy-region-fill-${regionId}`,
        scene,
      );
      const vertexData = new VertexData();
      vertexData.positions = geometry.positions;
      vertexData.indices = geometry.indices;
      vertexData.applyToMesh(mesh, false);
      mesh.isPickable = true;
      mesh.renderingGroupId = 0;
      mesh.alphaIndex = 0;
      mesh.metadata = {
        spatialLayer: {
          id: 'galaxy-regions',
          representation: 'AUTHORITATIVE',
          regionId,
          regionName,
          rectangleCount: geometry.rectangleCount,
          sourceCellCount: geometry.sourceCellCount,
        },
      };

      const material = new StandardMaterial(
        `authoritative-galaxy-region-fill-material-${regionId}`,
        scene,
      );
      material.disableLighting = true;
      material.backFaceCulling = false;
      material.disableDepthWrite = true;
      material.diffuseColor = regionBaseColor(regionId);
      material.emissiveColor = regionBaseColor(regionId);
      material.alpha =
        selectedRegionId === regionId
          ? REGION_SELECTED_ALPHA
          : REGION_BASE_ALPHA;
      if (selectedRegionId === regionId) {
        material.diffuseColor.set(1, 0.38, 0.045);
        material.emissiveColor.set(1, 0.38, 0.045);
      }
      mesh.material = material;
      return { regionId, regionName, mesh, material };
    },
  );
}

export function updateGalaxyRegionFillAppearance(
  product: BabylonGalaxyProduct,
  hoveredRegionId: number | null,
): void {
  for (const fill of product.regionFillMeshes) {
    const selected = fill.regionId === product.selectedRegionId;
    const hovered = fill.regionId === hoveredRegionId;
    if (selected) {
      fill.material.diffuseColor.set(1, 0.38, 0.045);
      fill.material.emissiveColor.set(1, 0.38, 0.045);
      fill.material.alpha = REGION_SELECTED_ALPHA;
    } else if (hovered) {
      fill.material.diffuseColor.set(0.035, 0.56, 0.82);
      fill.material.emissiveColor.set(0.09, 0.78, 1);
      fill.material.alpha = REGION_HOVERED_ALPHA;
    } else {
      const base = regionBaseColor(fill.regionId);
      fill.material.diffuseColor.copyFrom(base);
      fill.material.emissiveColor.copyFrom(base);
      fill.material.alpha = REGION_BASE_ALPHA;
    }
  }
}

function targetKey(target: SpatialTarget | undefined): string {
  if (!target) return '';
  switch (target.kind) {
    case 'system':
      return `system:${target.systemId64}`;
    case 'body':
      return `body:${target.ref.systemId64}:${target.ref.bodyId}`;
    case 'facility':
      return `facility:${target.ref.owner}:${target.ref.facilityId}`;
    default:
      return `${target.kind}:${target.id}`;
  }
}

function sameGalaxyRenderInputs(
  current: GalaxySceneContract,
  next: GalaxySceneContract,
): boolean {
  const currentCamera = current.camera;
  const nextCamera = next.camera;
  if (
    currentCamera.revision !== nextCamera.revision ||
    currentCamera.distanceLy !== nextCamera.distanceLy ||
    currentCamera.bearingRad !== nextCamera.bearingRad ||
    currentCamera.pitchRad !== nextCamera.pitchRad ||
    currentCamera.projection !== nextCamera.projection ||
    currentCamera.focusLy.x !== nextCamera.focusLy.x ||
    currentCamera.focusLy.y !== nextCamera.focusLy.y ||
    currentCamera.focusLy.z !== nextCamera.focusLy.z ||
    current.contributions.length !== next.contributions.length
  ) {
    return false;
  }

  return current.contributions.every((contribution, contributionIndex) => {
    const nextContribution = next.contributions[contributionIndex];
    return (
      nextContribution?.id === contribution.id &&
      nextContribution.owner === contribution.owner &&
      nextContribution.revision === contribution.revision &&
      nextContribution.layers.length === contribution.layers.length &&
      contribution.layers.every((layer, layerIndex) => {
        const nextLayer = nextContribution.layers[layerIndex];
        return (
          nextLayer?.id === layer.id &&
          nextLayer.version === layer.version &&
          nextLayer.representation === layer.representation &&
          nextLayer.targetCount === layer.targetCount &&
          nextLayer.truncated === layer.truncated &&
          nextLayer.payload === layer.payload
        );
      })
    );
  });
}

function canPatchGalaxySelection(
  current: GalaxySceneContract,
  next: GalaxySceneContract,
): boolean {
  return sameGalaxyRenderInputs(current, next);
}

function createSelectedSystemMarker(
  scene: Scene,
  point: GalaxySystemPoint,
  markerSizeLy: number,
): ReturnType<typeof CreateTorus> {
  const marker = CreateTorus(
    'selected-system-marker',
    {
      diameter: markerSizeLy * 5.8,
      thickness: markerSizeLy * 0.3,
      tessellation: 32,
    },
    scene,
  );
  marker.position.set(
    point.positionLy.x,
    point.positionLy.y,
    point.positionLy.z,
  );
  marker.rotation.x = Math.PI / 2;
  const material = new StandardMaterial('selected-system-material', scene);
  material.disableLighting = true;
  material.emissiveColor = new Color3(1, 0.58, 0.08);
  marker.material = material;
  return marker;
}

function catalogueDensityReceipt(
  density: CatalogueDensitySceneLayer,
): RenderedLayerReceipt {
  return {
    contributionId: density.contributionId,
    contributionRevision: density.contributionRevision,
    layerId: 'catalogue-density',
    layerVersion: density.layerVersion,
    representation: 'DERIVED',
    acceptedTargetCount: density.payload.cells.length,
    renderedTargetCount: density.payload.cells.length,
    sourceGeneration: density.payload.generationId,
  };
}

export function commanderHistoryHeatColour(
  visitCount: number,
  maximumVisitCount: number,
): readonly [number, number, number, number] {
  if (!Number.isSafeInteger(visitCount) || visitCount <= 0)
    throw new RangeError(
      'Commander history colour requires a positive visit count',
    );
  if (!Number.isSafeInteger(maximumVisitCount) || maximumVisitCount <= 0)
    throw new RangeError(
      'Commander history colour requires a positive maximum',
    );
  const intensity = Math.min(
    1,
    Math.log1p(visitCount) / Math.log1p(maximumVisitCount),
  );
  if (intensity < 0.5) {
    const local = intensity * 2;
    return [0.08, 0.28 + local * 0.58, 1 - local * 0.18, 0.38 + local * 0.28];
  }
  const local = (intensity - 0.5) * 2;
  return [0.08 + local * 0.92, 0.86, 0.82 - local * 0.68, 0.66 + local * 0.26];
}

function createCommanderHistoryMesh(
  scene: Scene,
  history: CommanderHistorySceneLayer | null,
  markerSizeLy: number,
): ReturnType<typeof CreateSphere> | null {
  if (!history?.payload.points.length) return null;
  const mesh = CreateSphere(
    'commander-history-heatmap',
    { diameter: 2, segments: 8 },
    scene,
  );
  mesh.isPickable = false;
  mesh.thinInstanceEnablePicking = false;
  mesh.hasVertexAlpha = true;
  mesh.alphaIndex = 2;
  const material = new StandardMaterial('commander-history-material', scene);
  material.disableLighting = true;
  material.diffuseColor = Color3.White();
  material.emissiveColor = new Color3(0.68, 0.68, 0.68);
  material.specularColor = Color3.Black();
  material.alpha = 0.82;
  mesh.material = material;
  mesh.onDisposeObservable.addOnce(() => material.dispose());

  const maximumVisitCount = history.payload.points.reduce(
    (maximum, point) => Math.max(maximum, point.visitCount),
    1,
  );
  const matrices = new Float32Array(history.payload.points.length * 16);
  const colours = new Float32Array(history.payload.points.length * 4);
  history.payload.points.forEach((point, index) => {
    const radius = point.cellSizeLy
      ? Math.max(markerSizeLy, point.cellSizeLy * 0.42)
      : markerSizeLy *
        (1.5 + Math.min(1.2, Math.log1p(point.visitCount) * 0.25));
    Matrix.Compose(
      new Vector3(radius, radius, radius),
      Quaternion.Identity(),
      new Vector3(point.positionLy.x, point.positionLy.y, point.positionLy.z),
    ).copyToArray(matrices, index * 16);
    colours.set(
      commanderHistoryHeatColour(point.visitCount, maximumVisitCount),
      index * 4,
    );
  });
  mesh.thinInstanceSetBuffer('matrix', matrices, 16, true);
  mesh.thinInstanceSetBuffer('color', colours, 4, true);
  mesh.thinInstanceRefreshBoundingInfo(true);
  mesh.metadata = {
    spatialLayer: {
      id: COMMANDER_HISTORY_LAYER_ID,
      representation: 'DERIVED',
      owner: 'COMMANDER_HISTORY',
      source: 'journal-log',
      mode: history.payload.mode,
      renderedPointCount: history.payload.points.length,
      truncated: history.truncated,
      catalogueDensity: false,
    },
  };
  return mesh;
}

function commanderHistoryReceipt(
  history: CommanderHistorySceneLayer,
): RenderedLayerReceipt {
  return {
    contributionId: history.contributionId,
    contributionRevision: history.contributionRevision,
    layerId: COMMANDER_HISTORY_LAYER_ID,
    layerVersion: history.layerVersion,
    representation: history.representation,
    acceptedTargetCount: history.payload.points.length,
    renderedTargetCount: history.payload.points.length,
  };
}

export function nebulaCloudRadiusLy(
  kind: 'nebula' | 'planetary-nebula',
): number {
  // Mapcharts publishes a reference-system coordinate, not a physical boundary.
  // These bounded radii are deliberately schematic map presentation.
  return kind === 'planetary-nebula' ? 72 : 260;
}

function createGalaxyNebulaeMesh(
  scene: Scene,
  nebulae: GalaxyNebulaeSceneLayer | null,
): ReturnType<typeof CreateSphere> | null {
  if (!nebulae?.payload.nebulae.length) return null;
  const mesh = CreateSphere(
    'galaxy-nebula-landmarks',
    { diameter: 2, segments: 12 },
    scene,
  );
  mesh.isPickable = false;
  mesh.thinInstanceEnablePicking = false;
  mesh.hasVertexAlpha = true;
  mesh.alphaIndex = 0;
  const material = new StandardMaterial('galaxy-nebula-material', scene);
  material.disableLighting = true;
  material.backFaceCulling = false;
  material.disableDepthWrite = true;
  material.diffuseColor = Color3.White();
  material.emissiveColor = new Color3(0.24, 0.32, 0.44);
  material.specularColor = Color3.Black();
  material.alpha = 0.24;
  mesh.material = material;
  mesh.onDisposeObservable.addOnce(() => material.dispose());

  const matrices = new Float32Array(nebulae.payload.nebulae.length * 16);
  const colours = new Float32Array(nebulae.payload.nebulae.length * 4);
  nebulae.payload.nebulae.forEach((nebula, index) => {
    const radius = nebulaCloudRadiusLy(nebula.kind);
    const position = nebula.positionLy.value;
    Matrix.Compose(
      new Vector3(radius, radius * 0.72, radius),
      Quaternion.Identity(),
      new Vector3(position.x, position.y, position.z),
    ).copyToArray(matrices, index * 16);
    colours.set(
      nebula.kind === 'planetary-nebula'
        ? [0.26, 0.74, 1, 0.38]
        : [0.7, 0.25, 0.92, 0.3],
      index * 4,
    );
  });
  mesh.thinInstanceSetBuffer('matrix', matrices, 16, true);
  mesh.thinInstanceSetBuffer('color', colours, 4, true);
  mesh.thinInstanceRefreshBoundingInfo(true);
  mesh.metadata = {
    spatialLayer: {
      id: GALAXY_NEBULAE_LAYER_ID,
      representation: 'AMBIENT',
      owner: 'CATALOGUE',
      coordinateRepresentation: 'AUTHORITATIVE',
      radiusMeaning: 'schematic-map-presentation-not-physical-extent',
      sourceUrl: nebulae.payload.sourceUrl,
      attribution: nebulae.payload.attribution,
      rightsNotice: nebulae.payload.rightsNotice,
      usageBasis: nebulae.payload.usageBasis,
      sourceByteCount: nebulae.payload.sourceByteCount,
      sourceSha256: nebulae.payload.sourceSha256,
      renderedPointCount: nebulae.payload.nebulae.length,
    },
  };
  return mesh;
}

function galaxyNebulaeReceipt(
  nebulae: GalaxyNebulaeSceneLayer,
): RenderedLayerReceipt {
  return {
    contributionId: nebulae.contributionId,
    contributionRevision: nebulae.contributionRevision,
    layerId: GALAXY_NEBULAE_LAYER_ID,
    layerVersion: nebulae.layerVersion,
    representation: nebulae.representation,
    acceptedTargetCount: nebulae.payload.nebulae.length,
    renderedTargetCount: nebulae.payload.nebulae.length,
    sourceGeneration: nebulae.payload.sourceLastModified ?? undefined,
  };
}

function replacesCatalogueDensity(
  current: CatalogueDensitySceneLayer | null,
  contribution: SpatialContribution,
): boolean {
  if (contribution.owner !== 'CATALOGUE') return false;
  if (
    contribution.layers.length > 1 ||
    contribution.layers.some((layer) => layer.id !== 'catalogue-density')
  ) {
    return false;
  }
  return current
    ? current.contributionId === contribution.id
    : contribution.layers.length === 1;
}

function createGalaxyVisualFinish(
  scene: Scene,
  glowMeshes: readonly Mesh[],
): GlowLayer {
  const image = scene.imageProcessingConfiguration;
  image.toneMappingEnabled = true;
  image.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  image.exposure = 1.16;
  image.contrast = 1.18;
  image.vignetteEnabled = true;
  image.vignetteBlendMode = ImageProcessingConfiguration.VIGNETTEMODE_MULTIPLY;
  image.vignetteColor = new Color4(0.006, 0.01, 0.02, 1);
  image.vignetteWeight = 1.35;
  image.vignetteStretch = 0.18;
  image.ditheringEnabled = true;
  image.ditheringIntensity = 0.012;

  const glow = new GlowLayer('galaxy-emissive-glow', scene, {
    mainTextureSamples: Math.max(
      1,
      Math.min(4, scene.getEngine().getCaps().maxMSAASamples),
    ),
  });
  glow.blurKernelSize = 32;
  glow.intensity = 0.42;
  for (const mesh of glowMeshes) glow.addIncludedOnlyMesh(mesh);
  return glow;
}

function pickGalaxyTarget(
  engine: AbstractEngine,
  product: BabylonGalaxyProduct,
  screenX: number,
  screenY: number,
): SpatialTarget | undefined {
  const canvas = engine.getRenderingCanvas();
  const scaleX = canvas?.clientWidth
    ? engine.getRenderWidth() / canvas.clientWidth
    : 1;
  const scaleY = canvas?.clientHeight
    ? engine.getRenderHeight() / canvas.clientHeight
    : 1;
  // Translucent region planes must not intercept a visible system target.
  const systemHit = product.scene.pick(
    screenX * scaleX,
    screenY * scaleY,
    (mesh) => mesh === product.starMesh || mesh === product.selectedMarker,
  );
  const hit = systemHit?.hit
    ? systemHit
    : product.scene.pick(screenX * scaleX, screenY * scaleY, (mesh) =>
        product.regionFillMeshes.some((fill) => fill.mesh === mesh),
      );
  if (hit?.pickedMesh === product.selectedMarker) {
    const selected = product.points.find((point) =>
      product.selectedMarker?.position.equalsWithEpsilon(
        new Vector3(point.positionLy.x, point.positionLy.y, point.positionLy.z),
      ),
    );
    return selected
      ? { kind: 'system', systemId64: selected.systemId64 }
      : undefined;
  }
  if (
    hit?.pickedMesh === product.starMesh &&
    typeof hit.thinInstanceIndex === 'number' &&
    hit.thinInstanceIndex >= 0
  ) {
    const point = product.points[hit.thinInstanceIndex];
    return point ? { kind: 'system', systemId64: point.systemId64 } : undefined;
  }
  const fill = product.regionFillMeshes.find(
    (candidate) => candidate.mesh === hit?.pickedMesh,
  );
  if (!fill || !hit?.pickedPoint || !product.regionLookup) return undefined;
  const identity = findGalaxyRegionAt(product.regionLookup, {
    x: hit.pickedPoint.x,
    z: hit.pickedPoint.z,
  });
  return identity?.id === fill.regionId
    ? { kind: 'region', id: String(identity.id) }
    : undefined;
}

export const createBabylonGalaxyScene = (
  engine: AbstractEngine,
  contract: GalaxySceneContract,
): BabylonGalaxyProduct => {
  const scene = new Scene(engine);
  // Svelte owns input and dispatches explicit picks/camera commands. Babylon's
  // default handlers duplicate picking and focus the hidden canvas on release.
  scene.detachControl();
  scene.clearColor = new Color4(0.008, 0.014, 0.028, 1);
  const systemLayers = galaxySystemsSceneLayers(contract);
  const points = uniqueGalaxySystemPoints(systemLayers);
  const density = catalogueDensitySceneLayer(contract);
  const commanderHistory = commanderHistorySceneLayer(contract);
  const nebulae = galaxyNebulaeSceneLayer(contract);
  const regions = galaxyRegionsSceneLayer(contract);
  const selectedRegionId = selectedGalaxyRegionId(contract);
  const cameraState = normalizeGalaxyCamera(contract.camera);
  const camera = new FreeCamera('galaxy-camera', Vector3.Zero(), scene);
  applyGalaxyCamera(camera, cameraState);
  scene.activeCamera = camera;

  const light = new HemisphericLight(
    'galaxy-fill',
    new Vector3(-0.2, 1, -0.3),
    scene,
  );
  light.intensity = 0.35;

  const referenceGrid = createGalaxyReferenceGrid(scene, cameraState);
  const densityMesh = createCatalogueDensityMesh(scene, density);
  const markerSizeLy = galaxyStarMarkerSizeLy(cameraState.distanceLy);
  const commanderHistoryMesh = createCommanderHistoryMesh(
    scene,
    commanderHistory,
    markerSizeLy,
  );
  const nebulaMesh = createGalaxyNebulaeMesh(scene, nebulae);
  const regionFillMeshes = createGalaxyRegionFillMeshes(
    scene,
    regions,
    selectedRegionId,
  );
  const regionBoundaryMesh = createGalaxyRegionBoundaryMesh(scene, regions);

  const starMesh = CreateSphere(
    'finder-system-instances',
    { diameter: markerSizeLy * 1.25, segments: 8, updatable: true },
    scene,
  );
  const starMaterial = new StandardMaterial('finder-system-material', scene);
  starMaterial.disableLighting = true;
  starMaterial.emissiveColor = new Color3(0.72, 0.72, 0.72);
  starMaterial.diffuseColor = Color3.White();
  starMaterial.specularColor = Color3.Black();
  starMesh.material = starMaterial;
  starMesh.hasVertexAlpha = true;
  starMesh.thinInstanceEnablePicking = true;
  const stellarPresentations = points.map((point) =>
    stellarPresentation(point.primaryStar),
  );
  const matrices = new Float32Array(points.length * 16);
  const colours = new Float32Array(points.length * 4);
  points.forEach((point, index) => {
    const presentation = stellarPresentations[index]!;
    Matrix.Compose(
      new Vector3(
        presentation.relativeScale,
        presentation.relativeScale,
        presentation.relativeScale,
      ),
      Quaternion.Identity(),
      new Vector3(point.positionLy.x, point.positionLy.y, point.positionLy.z),
    ).copyToArray(matrices, index * 16);
    colours.set([...presentation.coreRgb, 1], index * 4);
  });
  starMesh.thinInstanceSetBuffer('matrix', matrices, 16, true);
  starMesh.thinInstanceSetBuffer('color', colours, 4, true);
  starMesh.thinInstanceRefreshBoundingInfo(true);
  starMesh.setEnabled(points.length > 0);
  const starVertexPositions = Float32Array.from(
    starMesh.getVerticesData('position') ?? [],
  );

  const selectedSystemId64 = selectedGalaxySystemId64(contract);
  const selectedPoint = points.find(
    (point) => point.systemId64 === selectedSystemId64,
  );
  const selectedMarker = selectedPoint
    ? createSelectedSystemMarker(scene, selectedPoint, markerSizeLy)
    : null;

  const stellarAccentMeshes = points.flatMap((point, index) => {
    const presentation = stellarPresentations[index]!;
    if (!presentation.ring) return [];
    const ring = CreateTorus(
      `stellar-icon-ring-${point.systemId64}`,
      {
        diameter: markerSizeLy * presentation.relativeScale * 2.25,
        thickness: markerSizeLy * 0.18,
        tessellation: 28,
      },
      scene,
    );
    ring.position.set(
      point.positionLy.x,
      point.positionLy.y,
      point.positionLy.z,
    );
    ring.rotation.x = Math.PI / 2;
    ring.isPickable = false;
    const material = new StandardMaterial(
      `stellar-icon-ring-material-${point.systemId64}`,
      scene,
    );
    material.disableLighting = true;
    material.emissiveColor = Color3.FromArray(presentation.haloRgb);
    material.diffuseColor = Color3.Black();
    material.specularColor = Color3.Black();
    ring.material = material;
    ring.onDisposeObservable.addOnce(() => material.dispose());
    ring.metadata = {
      spatialLayer: {
        id: 'finder-systems',
        systemId64: point.systemId64,
        stellarGlyph: presentation.glyph,
        presentationOnly: true,
      },
    };
    return [ring];
  });

  const visualGlow = createGalaxyVisualFinish(
    scene,
    [
      densityMesh,
      nebulaMesh,
      commanderHistoryMesh,
      starMesh,
      selectedMarker,
      ...stellarAccentMeshes,
    ].filter((mesh): mesh is Mesh => mesh !== null),
  );

  const renderedLayers: RenderedLayerReceipt[] = [];
  if (density) {
    renderedLayers.push(catalogueDensityReceipt(density));
  }
  if (regions) {
    renderedLayers.push({
      contributionId: regions.contributionId,
      contributionRevision: regions.contributionRevision,
      layerId: 'galaxy-regions',
      layerVersion: regions.layerVersion,
      representation: 'AUTHORITATIVE',
      acceptedTargetCount: regions.payload.regions.length,
      renderedTargetCount: regions.payload.regions.length,
      sourceGeneration: regions.payload.source.sha256,
    });
  }
  for (const systemLayer of systemLayers) {
    renderedLayers.push({
      contributionId: systemLayer.contributionId,
      contributionRevision: systemLayer.contributionRevision,
      layerId: systemLayer.layerId,
      layerVersion: systemLayer.layerVersion,
      representation: systemLayer.representation,
      acceptedTargetCount: systemLayer.points.length,
      renderedTargetCount: systemLayer.points.length,
    });
  }
  if (commanderHistory)
    renderedLayers.push(commanderHistoryReceipt(commanderHistory));
  if (nebulae) renderedLayers.push(galaxyNebulaeReceipt(nebulae));
  scene.metadata = {
    spatialScene: {
      kind: contract.kind,
      revision: contract.revision,
      renderedLayers,
      visualProfile: {
        toneMapping: 'ACES',
        emissiveGlow: true,
        adaptiveReferenceGrid: true,
        stellarIconFamilies: true,
        systemPositions: 'canonical-light-years',
        ambientDensitySubstitute: false,
        nebulaCoordinates: 'authoritative-reference-systems',
        nebulaCloudExtents: 'schematic',
      },
    },
  };

  return {
    scene,
    camera,
    cameraState,
    points,
    starMesh,
    starVertexPositions,
    starInstanceMatrices: matrices,
    starInstanceColours: colours,
    stellarPresentations,
    stellarAccentMeshes,
    densityMesh,
    commanderHistoryMesh,
    nebulaMesh,
    regionBoundaryMesh,
    regionFillMeshes,
    regionLookup: regions?.payload.lookup ?? null,
    referenceGrid,
    visualGlow,
    selectedMarker,
    selectedSystemId64,
    selectedRegionId,
    markerSizeLy,
    renderedLayers,
  };
};

function systemBodyColour(
  body: BodyVisualDescriptor,
): Readonly<{ diffuse: Color3; emissive: Color3; darkCore: boolean }> {
  const identity =
    `${body.class?.value ?? ''} ${body.subtype?.value ?? ''}`.toLowerCase();
  if (identity.includes('star') || identity.includes('black hole')) {
    const star = stellarPresentation({
      type: body.class?.value,
      subtype: body.subtype?.value,
    });
    return {
      diffuse: Color3.FromArray(star.coreRgb),
      emissive: Color3.FromArray(star.haloRgb),
      darkCore: star.darkCore,
    };
  }
  if (identity.includes('earth-like') || identity.includes('water world')) {
    return {
      diffuse: new Color3(0.18, 0.56, 0.8),
      emissive: new Color3(0.02, 0.08, 0.12),
      darkCore: false,
    };
  }
  if (identity.includes('ammonia')) {
    return {
      diffuse: new Color3(0.58, 0.62, 0.28),
      emissive: new Color3(0.04, 0.05, 0.01),
      darkCore: false,
    };
  }
  if (identity.includes('gas giant')) {
    return {
      diffuse: new Color3(0.76, 0.52, 0.3),
      emissive: new Color3(0.05, 0.025, 0.01),
      darkCore: false,
    };
  }
  if (identity.includes('ice') || identity.includes('icy')) {
    return {
      diffuse: new Color3(0.62, 0.78, 0.86),
      emissive: new Color3(0.03, 0.05, 0.07),
      darkCore: false,
    };
  }
  if (identity.includes('belt')) {
    return {
      diffuse: new Color3(0.46, 0.42, 0.38),
      emissive: Color3.Black(),
      darkCore: false,
    };
  }
  return {
    diffuse: new Color3(0.48, 0.48, 0.52),
    emissive: new Color3(0.025, 0.025, 0.035),
    darkCore: false,
  };
}

function systemCameraTarget(
  camera: SystemCameraState,
  bodies: readonly BabylonSystemBodyMesh[],
): Vector3 {
  if (camera.focus.kind === 'body') {
    const focusedBodyId = camera.focus.ref.bodyId;
    const selected = bodies.find(
      (body) => body.layout.body.ref.bodyId === focusedBodyId,
    );
    if (selected) return selected.mesh.position.clone();
  }
  return Vector3.Zero();
}

export function applySystemCamera(
  camera: FreeCamera,
  state: SystemCameraState,
  bodies: readonly BabylonSystemBodyMesh[],
): void {
  const target = systemCameraTarget(state, bodies);
  const distance = Math.max(6, Math.min(120, state.semanticDistance));
  const pitch = Math.max(0.08, Math.min(1.42, state.pitchRad));
  const horizontal = Math.cos(pitch) * distance;
  camera.position.set(
    target.x + Math.sin(state.bearingRad) * horizontal,
    target.y + Math.sin(pitch) * distance,
    target.z - Math.cos(state.bearingRad) * horizontal,
  );
  camera.upVector.set(0, 1, 0);
  camera.setTarget(target);
}

function createSystemOrbitMesh(
  scene: Scene,
  layouts: readonly SystemBodyLayout[],
): ReturnType<typeof CreateLineSystem> | null {
  const radii = [
    ...new Set(
      layouts
        .map((layout) => Number(layout.orbitRadius.toFixed(4)))
        .filter((radius) => radius > 0),
    ),
  ];
  if (radii.length === 0) return null;
  const lines = radii.map((radius) =>
    Array.from({ length: 97 }, (_, index) => {
      const angle = (index / 96) * Math.PI * 2;
      return new Vector3(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
    }),
  );
  const orbitMesh = CreateLineSystem(
    'system-semantic-orbits',
    { lines, updatable: false },
    scene,
  );
  orbitMesh.color = new Color3(0.16, 0.34, 0.46);
  orbitMesh.alpha = 0.42;
  orbitMesh.isPickable = false;
  orbitMesh.metadata = {
    spatialLayer: {
      id: 'system-semantic-orbits',
      representation: 'SCHEMATIC',
      meaning: 'ordered-distance-layout-not-observed-orbital-elements',
    },
  };
  return orbitMesh;
}

export const createBabylonSystemScene = (
  engine: AbstractEngine,
  contract: SystemSceneContract,
): BabylonSystemProduct => {
  const scene = new Scene(engine);
  scene.detachControl();
  scene.clearColor = new Color4(0.004, 0.008, 0.016, 1);
  const camera = new FreeCamera('system-camera', Vector3.Zero(), scene);
  scene.activeCamera = camera;
  const light = new HemisphericLight(
    'system-fill',
    new Vector3(-0.3, 0.85, -0.45),
    scene,
  );
  light.intensity = 1.25;

  const layouts = systemBodyLayout(contract.bodies);
  const bodies = layouts.map((layout): BabylonSystemBodyMesh => {
    const body = layout.body;
    const visual = systemBodyColour(body);
    const mesh = CreateSphere(
      `system-body-${body.ref.bodyId}`,
      { diameter: body.displayRadius * 2, segments: 24 },
      scene,
    );
    mesh.position.set(layout.position.x, layout.position.y, layout.position.z);
    mesh.metadata = {
      spatialTarget: {
        kind: 'body',
        ref: body.ref,
      },
      bodyName: body.name,
      representation: {
        position: 'SCHEMATIC',
        bodyFacts: 'AUTHORITATIVE',
      },
    };
    const material = new StandardMaterial(
      `system-body-material-${body.ref.bodyId}`,
      scene,
    );
    material.diffuseColor = visual.darkCore ? Color3.Black() : visual.diffuse;
    material.emissiveColor = visual.darkCore
      ? new Color3(0.005, 0.005, 0.008)
      : visual.emissive;
    material.specularColor = visual.darkCore
      ? new Color3(0.08, 0.08, 0.1)
      : new Color3(0.24, 0.24, 0.26);
    material.specularPower = 48;
    mesh.material = material;
    mesh.onDisposeObservable.addOnce(() => material.dispose());

    const ringMeshes =
      body.rings?.state === 'PRESENT'
        ? [
            CreateTorus(
              `system-body-ring-${body.ref.bodyId}`,
              {
                diameter: body.displayRadius * 3.2,
                thickness: Math.max(0.06, body.displayRadius * 0.18),
                tessellation: 64,
              },
              scene,
            ),
          ]
        : [];
    for (const ring of ringMeshes) {
      ring.position.copyFrom(mesh.position);
      ring.rotation.x = Math.PI / 2;
      ring.isPickable = false;
      const ringMaterial = new StandardMaterial(
        `system-body-ring-material-${body.ref.bodyId}`,
        scene,
      );
      ringMaterial.disableLighting = true;
      ringMaterial.emissiveColor = new Color3(0.48, 0.56, 0.62);
      ringMaterial.diffuseColor = new Color3(0.2, 0.22, 0.24);
      ringMaterial.alpha = 0.72;
      ring.material = ringMaterial;
      ring.onDisposeObservable.addOnce(() => ringMaterial.dispose());
    }
    return { layout, mesh, ringMeshes };
  });
  const orbitMesh = createSystemOrbitMesh(scene, layouts);
  applySystemCamera(camera, contract.camera, bodies);
  const glowMeshes = bodies
    .filter((body) => {
      const identity = `${body.layout.body.class?.value ?? ''} ${body.layout.body.subtype?.value ?? ''}`;
      return /star|black hole/i.test(identity);
    })
    .map((body) => body.mesh);
  const visualGlow = createGalaxyVisualFinish(scene, glowMeshes);
  visualGlow.name = 'system-emissive-glow';
  visualGlow.intensity = 0.58;
  const renderedLayers: readonly RenderedLayerReceipt[] = [];
  scene.metadata = {
    spatialScene: {
      kind: 'system',
      revision: contract.revision,
      fidelity: contract.fidelity,
      bodyCount: bodies.length,
      renderedLayers,
      visualProfile: {
        threeDimensional: true,
        bodyFacts: 'authoritative-when-present',
        placement: 'deterministic-schematic',
        physicalScale: false,
      },
    },
  };
  return {
    scene,
    camera,
    cameraState: contract.camera,
    contract,
    bodies,
    orbitMesh,
    visualGlow,
    renderedLayers,
  };
};

function pickSystemTarget(
  engine: AbstractEngine,
  product: BabylonSystemProduct,
  screenX: number,
  screenY: number,
): SpatialTarget | undefined {
  const canvas = engine.getRenderingCanvas();
  const scaleX = canvas?.clientWidth
    ? engine.getRenderWidth() / canvas.clientWidth
    : 1;
  const scaleY = canvas?.clientHeight
    ? engine.getRenderHeight() / canvas.clientHeight
    : 1;
  const hit = product.scene.pick(screenX * scaleX, screenY * scaleY, (mesh) =>
    product.bodies.some((body) => body.mesh === mesh),
  );
  const body = product.bodies.find(
    (candidate) => candidate.mesh === hit?.pickedMesh,
  );
  return body ? { kind: 'body', ref: body.layout.body.ref } : undefined;
}

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

export const createBabylonSession = (
  engine: AbstractEngine,
  backend: SpatialRendererBackend,
  now: () => number = () => performance.now(),
): SpatialBackendSession => {
  let scene: Scene | null = null;
  let product: BabylonGalaxyProduct | null = null;
  let productContract: GalaxySceneContract | null = null;
  let systemProduct: BabylonSystemProduct | null = null;
  let warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
  let readinessAttemptsRemaining = 120;
  let hoveredTargetKey = '';
  let transition: {
    from: CameraState;
    to: CameraState;
    startedAt: number;
    durationMs: number;
    target?: SpatialTarget;
    emit: (event: RuntimeEvent) => void;
  } | null = null;

  const applyCameraState = (
    camera: CameraState,
    emit: (event: RuntimeEvent) => void,
  ): void => {
    if (!product) return;
    applyGalaxyCamera(product.camera, camera);
    const scale =
      galaxyStarMarkerSizeLy(camera.distanceLy) / product.markerSizeLy;
    product.starMesh.updateVerticesData(
      'position',
      product.starVertexPositions.map((value) => value * scale),
      true,
    );
    product.starMesh.thinInstanceRefreshBoundingInfo(true);
    product.selectedMarker?.scaling.setAll(scale);
    for (const accent of product.stellarAccentMeshes)
      accent.scaling.setAll(scale);
    const referenceGrid = refreshGalaxyReferenceGrid(product, camera);
    product = { ...product, cameraState: camera, referenceGrid };
    if (productContract) productContract = { ...productContract, camera };
    emit({ type: 'CAMERA_CHANGED', camera });
  };

  const moveCamera = (
    camera: CameraState,
    emit: (event: RuntimeEvent) => void,
    durationMs = 0,
    target?: SpatialTarget,
  ): void => {
    if (!product) return;
    transition = null;
    warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
    readinessAttemptsRemaining = 120;
    if (durationMs > 0) {
      transition = {
        from: product.cameraState,
        to: camera,
        startedAt: now(),
        durationMs: Math.min(2_000, durationMs),
        target,
        emit,
      };
    } else {
      applyCameraState(camera, emit);
      if (target) emit({ type: 'TRANSITION_FINISHED', target });
    }
  };
  const applySystemCameraState = (
    camera: SystemCameraState,
    emit: (event: RuntimeEvent) => void,
  ): void => {
    if (!systemProduct) return;
    applySystemCamera(systemProduct.camera, camera, systemProduct.bodies);
    systemProduct = {
      ...systemProduct,
      cameraState: camera,
      contract: { ...systemProduct.contract, camera },
    };
    emit({ type: 'CAMERA_CHANGED', camera });
  };
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
      if (product) {
        applyGalaxyCamera(product.camera, product.cameraState);
        const referenceGrid = refreshGalaxyReferenceGrid(
          product,
          product.cameraState,
        );
        product = { ...product, referenceGrid };
      } else if (systemProduct) {
        applySystemCamera(
          systemProduct.camera,
          systemProduct.cameraState,
          systemProduct.bodies,
        );
      }
    },
    execute(
      command: Exclude<RuntimeCommand, { type: 'RESIZE' }>,
      emit: (event: RuntimeEvent) => void,
    ): RuntimeCommandDispatchResult {
      if (command.type === 'LOAD_SCENE') {
        if (command.scene.kind === 'system') {
          transition = null;
          const replacement = createBabylonSystemScene(engine, command.scene);
          const previous = scene;
          scene = replacement.scene;
          systemProduct = replacement;
          product = null;
          productContract = null;
          emit({ type: 'CAMERA_CHANGED', camera: replacement.cameraState });
          hoveredTargetKey = '';
          warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
          readinessAttemptsRemaining = 120;
          previous?.dispose();
          emit({
            type: 'SCENE_APPLIED',
            sceneRevision: command.scene.revision,
            renderedLayers: replacement.renderedLayers,
          });
          return { status: 'executed' };
        }
        if (
          product &&
          productContract &&
          canPatchGalaxySelection(productContract, command.scene)
        ) {
          const selectedSystemId64 = selectedGalaxySystemId64(command.scene);
          const selectedPoint = product.points.find(
            (point) => point.systemId64 === selectedSystemId64,
          );
          let selectedMarker = product.selectedMarker;
          if (!selectedPoint && selectedMarker) {
            product.visualGlow.removeIncludedOnlyMesh(selectedMarker);
            selectedMarker.dispose(false, true);
            selectedMarker = null;
          } else if (selectedPoint && selectedMarker) {
            selectedMarker.position.set(
              selectedPoint.positionLy.x,
              selectedPoint.positionLy.y,
              selectedPoint.positionLy.z,
            );
          } else if (selectedPoint) {
            selectedMarker = createSelectedSystemMarker(
              product.scene,
              selectedPoint,
              product.markerSizeLy,
            );
            selectedMarker.scaling.setAll(
              galaxyStarMarkerSizeLy(product.cameraState.distanceLy) /
                product.markerSizeLy,
            );
            product.visualGlow.addIncludedOnlyMesh(selectedMarker);
          }
          product = {
            ...product,
            selectedMarker,
            selectedSystemId64,
            selectedRegionId: selectedGalaxyRegionId(command.scene),
          };
          productContract = command.scene;
          updateGalaxyRegionFillAppearance(product, null);
          const spatialScene = product.scene.metadata?.spatialScene as
            { revision?: number } | undefined;
          if (spatialScene) spatialScene.revision = command.scene.revision;
          hoveredTargetKey = '';
          warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
          readinessAttemptsRemaining = 120;
          emit({
            type: 'SCENE_APPLIED',
            sceneRevision: command.scene.revision,
            renderedLayers: product.renderedLayers,
          });
          return { status: 'executed' };
        }
        transition = null;
        const replacement = createBabylonGalaxyScene(engine, command.scene);
        const previous = scene;
        scene = replacement.scene;
        product = replacement;
        productContract = command.scene;
        systemProduct = null;
        emit({ type: 'CAMERA_CHANGED', camera: replacement.cameraState });
        hoveredTargetKey = '';
        warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
        readinessAttemptsRemaining = 120;
        previous?.dispose();
        emit({
          type: 'SCENE_APPLIED',
          sceneRevision: command.scene.revision,
          renderedLayers: replacement.renderedLayers,
        });
        return { status: 'executed' };
      }
      if (command.type === 'PATCH_CONTRIBUTION') {
        if (!product || !productContract) {
          return { status: 'unsupported', command: command.type };
        }
        const currentDensity = catalogueDensitySceneLayer(productContract);
        const currentContribution = productContract.contributions.find(
          (contribution) => contribution.id === command.contribution.id,
        );
        if (
          (currentContribution && currentContribution.owner !== 'CATALOGUE') ||
          !replacesCatalogueDensity(currentDensity, command.contribution)
        ) {
          return { status: 'unsupported', command: command.type };
        }
        if (
          currentContribution &&
          command.contribution.revision <= currentContribution.revision
        ) {
          return { status: 'ignored', reason: 'stale' };
        }

        const nextContract: GalaxySceneContract = {
          ...productContract,
          contributions: currentContribution
            ? productContract.contributions.map((contribution) =>
                contribution.id === command.contribution.id
                  ? command.contribution
                  : contribution,
              )
            : [...productContract.contributions, command.contribution],
        };
        const nextDensity = catalogueDensitySceneLayer(nextContract);
        const previousDensityMesh = product.densityMesh;
        if (previousDensityMesh) {
          product.visualGlow.removeIncludedOnlyMesh(previousDensityMesh);
          previousDensityMesh.dispose();
        }
        const densityMesh = createCatalogueDensityMesh(
          product.scene,
          nextDensity,
        );
        if (densityMesh) product.visualGlow.addIncludedOnlyMesh(densityMesh);
        const renderedLayers = [
          ...product.renderedLayers.filter(
            (receipt) => receipt.layerId !== 'catalogue-density',
          ),
          ...(nextDensity ? [catalogueDensityReceipt(nextDensity)] : []),
        ];
        const spatialScene = product.scene.metadata?.spatialScene as
          { renderedLayers?: readonly RenderedLayerReceipt[] } | undefined;
        if (spatialScene) spatialScene.renderedLayers = renderedLayers;
        product = { ...product, densityMesh, renderedLayers };
        productContract = nextContract;
        warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
        readinessAttemptsRemaining = 120;
        emit({
          type: 'CONTRIBUTION_APPLIED',
          contributionId: command.contribution.id,
          contributionRevision: command.contribution.revision,
          renderedLayers,
        });
        return { status: 'executed' };
      }
      if (command.type === 'SET_CAMERA') {
        if ('focusLy' in command.camera) {
          if (!product) {
            return { status: 'unsupported', command: command.type };
          }
          const camera = normalizeGalaxyCamera(command.camera);
          const durationMs =
            command.transition && !command.transition.reducedMotion
              ? command.transition.durationMs
              : 0;
          if (!Number.isFinite(durationMs) || durationMs < 0) {
            return { status: 'unsupported', command: command.type };
          }
          moveCamera(camera, emit, durationMs);
          return { status: 'executed' };
        }
        if (
          !systemProduct ||
          command.camera.systemId64 !== systemProduct.contract.systemId64
        ) {
          return { status: 'unsupported', command: command.type };
        }
        applySystemCameraState(command.camera, emit);
        return { status: 'executed' };
      }
      if (command.type === 'FLY_TO') {
        if (command.target.kind === 'body' && systemProduct) {
          const focusedBodyId = command.target.ref.bodyId;
          if (
            !systemProduct.bodies.some(
              (body) => body.layout.body.ref.bodyId === focusedBodyId,
            )
          ) {
            return { status: 'unsupported', command: command.type };
          }
          applySystemCameraState(
            {
              ...systemProduct.cameraState,
              focus: command.target,
              semanticDistance: Math.max(
                6,
                Math.min(18, systemProduct.cameraState.semanticDistance),
              ),
              revision: systemProduct.cameraState.revision + 1,
            },
            emit,
          );
          emit({ type: 'TRANSITION_FINISHED', target: command.target });
          return { status: 'executed' };
        }
        if (command.target.kind !== 'system' || !product) {
          return { status: 'unsupported', command: command.type };
        }
        const targetId = command.target.systemId64;
        const point = product.points.find(
          (candidate) => candidate.systemId64 === targetId,
        );
        if (!point) return { status: 'unsupported', command: command.type };
        const distance = Math.max(
          12,
          Math.min(product.cameraState.distanceLy, product.markerSizeLy * 24),
        );
        moveCamera(
          focusGalaxyCamera(product.cameraState, point.positionLy, distance),
          emit,
          command.reducedMotion ? 0 : 700,
          command.target,
        );
        return { status: 'executed' };
      }
      if (command.type === 'HOVER') {
        if (systemProduct) {
          const target = pickSystemTarget(
            engine,
            systemProduct,
            command.screenX,
            command.screenY,
          );
          const nextKey = targetKey(target);
          if (nextKey !== hoveredTargetKey) {
            hoveredTargetKey = nextKey;
            emit({ type: 'TARGET_HOVERED', target });
          }
          return { status: 'executed' };
        }
        if (!product) return { status: 'unsupported', command: command.type };
        const target = pickGalaxyTarget(
          engine,
          product,
          command.screenX,
          command.screenY,
        );
        const nextKey = targetKey(target);
        warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
        readinessAttemptsRemaining = 120;
        updateGalaxyRegionFillAppearance(
          product,
          target?.kind === 'region' ? Number(target.id) : null,
        );
        if (nextKey !== hoveredTargetKey) {
          hoveredTargetKey = nextKey;
          emit({ type: 'TARGET_HOVERED', target });
        }
        return { status: 'executed' };
      }
      if (command.type === 'CLEAR_HOVER') {
        if (systemProduct) {
          if (hoveredTargetKey) {
            hoveredTargetKey = '';
            emit({ type: 'TARGET_HOVERED' });
          }
          return { status: 'executed' };
        }
        if (!product) return { status: 'unsupported', command: command.type };
        warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
        readinessAttemptsRemaining = 120;
        updateGalaxyRegionFillAppearance(product, null);
        if (hoveredTargetKey) {
          hoveredTargetKey = '';
          emit({ type: 'TARGET_HOVERED' });
        }
        return { status: 'executed' };
      }
      if (command.type === 'PICK') {
        if (systemProduct) {
          emit({
            type: 'TARGET_PICKED',
            target: pickSystemTarget(
              engine,
              systemProduct,
              command.screenX,
              command.screenY,
            ),
          });
          return { status: 'executed' };
        }
        if (!product) return { status: 'unsupported', command: command.type };
        const target = pickGalaxyTarget(
          engine,
          product,
          command.screenX,
          command.screenY,
        );
        emit({
          type: 'TARGET_PICKED',
          target,
        });
        return { status: 'executed' };
      }
      return { status: 'unsupported', command: command.type };
    },
    render() {
      const activeScene = scene;
      if (!activeScene) return false;
      if (transition) {
        const activeTransition = transition;
        const progress = Math.min(
          1,
          Math.max(
            0,
            (now() - activeTransition.startedAt) / activeTransition.durationMs,
          ),
        );
        applyCameraState(
          interpolateGalaxyCamera(
            activeTransition.from,
            activeTransition.to,
            progress,
          ),
          activeTransition.emit,
        );
        if (progress >= 1) {
          transition = null;
          activeTransition.emit(
            activeTransition.target
              ? {
                  type: 'TRANSITION_FINISHED',
                  target: activeTransition.target,
                }
              : { type: 'TRANSITION_FINISHED' },
          );
        }
      }
      // A demand-rendered WebGPU frame still needs the engine frame boundary:
      // endFrame submits Babylon's queued GPU commands. WebGL can appear to
      // work without it, which previously hid a black WebGPU canvas.
      engine.beginFrame();
      try {
        activeScene.render();
      } finally {
        engine.endFrame();
      }
      const ready = activeScene.isReady(true);
      readinessAttemptsRemaining = Math.max(0, readinessAttemptsRemaining - 1);
      if (!ready) {
        warmupFramesRemaining = BABYLON_SCENE_WARMUP_FRAMES;
        return readinessAttemptsRemaining > 0 || transition !== null;
      }
      warmupFramesRemaining = Math.max(0, warmupFramesRemaining - 1);
      return warmupFramesRemaining > 0 || transition !== null;
    },
    dispose() {
      const currentScene = scene;
      scene = null;
      product = null;
      productContract = null;
      systemProduct = null;
      transition = null;
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
    canvasTabIndex: -1,
    powerPreference: 'high-performance',
  });
  try {
    await engine.initAsync();
    return createBabylonSession(engine, 'WEBGPU');
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
    { ...options, audioEngine: false, canvasTabIndex: -1 },
    false,
  );
  if (engine.webGLVersion !== 2) {
    disposeEngine(engine);
    return null;
  }
  return createBabylonSession(engine, 'WEBGL2');
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
