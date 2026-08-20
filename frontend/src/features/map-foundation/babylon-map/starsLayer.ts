import * as BABYLON from 'babylonjs';
import type { MapViewportSystem } from '@/lib/api';
import { coordinateSystem } from './coordinateSystem';
import { galaxyDensity } from './galaxyDensity';
import { spectralStarColor } from './spectralStarColor';

export interface StarsLayerOptions {
  pointSize?: number;
  maxStars?: number;
  /** Weight star color by galactic density (dimmer in sparse regions). */
  densityWeighting?: boolean;
  /** Light-years per pixel; forwarded to galaxyDensity for LOD culling. */
  zoomLy?: number;
}

const DEFAULT_POINT_SIZE = 2;
const DEFAULT_MAX_STARS = 100_000;

interface StarBuffers {
  positions: Float32Array;
  colors: Float32Array;
}

/**
 * Build the flat position/color buffers for a batch of viewport systems.
 * Positions are transformed via `coordinateSystem.gameTobabylon`; colors
 * come from `spectralStarColor` per `main_star_class`, optionally weighted
 * by `galaxyDensity.computeDensity` so real stars visually agree with the
 * density-sampled galaxy backdrop (Task 3).
 *
 * Babylon's `VertexData.colors` buffer is RGBA (4 floats/vertex), not RGB --
 * alpha is always written as 1 here since the star layer doesn't use
 * per-star transparency.
 */
function buildStarBuffers(
  systems: MapViewportSystem[],
  worldScale: number,
  options: StarsLayerOptions,
): StarBuffers {
  const { maxStars = DEFAULT_MAX_STARS, densityWeighting = true, zoomLy } = options;

  const bounded = systems.slice(0, maxStars);
  const positions = new Float32Array(bounded.length * 3);
  const colors = new Float32Array(bounded.length * 4);

  bounded.forEach((system, i) => {
    const gamePos = { x: system.x, y: system.y, z: system.z };
    const babylonPos = coordinateSystem.gameTobabylon(gamePos, worldScale);
    positions[i * 3] = babylonPos.x;
    positions[i * 3 + 1] = babylonPos.y;
    positions[i * 3 + 2] = babylonPos.z;

    const base = spectralStarColor(system.main_star_class);
    let r = base.r;
    let g = base.g;
    let b = base.b;

    if (densityWeighting) {
      const density = galaxyDensity.computeDensity(gamePos, zoomLy);
      // Stars in sparse regions are dimmed toward half-brightness; stars in
      // dense regions (density -> 1) render at full spectral color.
      const weight = 0.5 + 0.5 * density;
      r *= weight;
      g *= weight;
      b *= weight;
    }

    colors[i * 4] = r;
    colors[i * 4 + 1] = g;
    colors[i * 4 + 2] = b;
    colors[i * 4 + 3] = 1;
  });

  return { positions, colors };
}

function applyGlowMaterial(scene: BABYLON.Scene, mesh: BABYLON.Mesh, pointSize: number): void {
  const material = new BABYLON.StandardMaterial('starsMaterial', scene);
  material.emissiveColor = new BABYLON.Color3(1, 1, 1);
  material.specularColor = new BABYLON.Color3(0, 0, 0);
  material.disableLighting = true;
  material.pointsCloud = true;
  material.pointSize = pointSize;
  // Additive blending for a glow effect where stars overlap/cluster.
  material.alphaMode = BABYLON.Engine.ALPHA_ADD;

  mesh.material = material;
  mesh.hasVertexAlpha = true;
  mesh.renderingGroupId = 1; // after background/galaxy particles, before UI overlays
}

/**
 * Create the real-star point-cloud mesh for the current viewport batch.
 */
export function createStarsLayer(
  scene: BABYLON.Scene,
  systems: MapViewportSystem[],
  worldScale: number,
  options: StarsLayerOptions = {},
): BABYLON.Mesh {
  const { pointSize = DEFAULT_POINT_SIZE } = options;
  const { positions, colors } = buildStarBuffers(systems, worldScale, options);

  const mesh = new BABYLON.Mesh('realStarsPointCloud', scene);
  const vertexData = new BABYLON.VertexData();
  vertexData.positions = positions;
  vertexData.colors = colors;
  vertexData.applyToMesh(mesh, true);

  applyGlowMaterial(scene, mesh, pointSize);

  return mesh;
}

/**
 * Replace an existing star layer's geometry in place (new viewport batch,
 * or a zoom-driven LOD/density re-weight of the same batch).
 */
export function updateStarsLayer(
  layer: BABYLON.Mesh,
  systems: MapViewportSystem[],
  worldScale: number,
  options: StarsLayerOptions = {},
): void {
  const { positions, colors } = buildStarBuffers(systems, worldScale, options);

  const vertexData = new BABYLON.VertexData();
  vertexData.positions = positions;
  vertexData.colors = colors;
  vertexData.applyToMesh(layer, true);

  if (options.pointSize !== undefined && layer.material instanceof BABYLON.StandardMaterial) {
    layer.material.pointSize = options.pointSize;
  }
}
