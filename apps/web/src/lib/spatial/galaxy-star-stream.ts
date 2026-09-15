import type { Id64 } from '$lib/domain/id64';
import type {
  CameraState,
  GalaxySystemPoint,
  SpatialContribution,
} from './contracts';

export type GalaxyStarViewport = Readonly<{
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
  limit: number;
  cameraDistanceLy: number;
  wide: boolean;
}>;

export type CatalogueViewportSystem = Readonly<{
  id64: Id64;
  name: string;
  x: number;
  y: number;
  z: number;
  mainStarClass?: string | null;
  populated: boolean;
}>;

/**
 * Exact-star detail is bounded to a 15,000 LY API cube. The deliberately
 * descending budget keeps the medium view rich while close inspection sheds
 * clutter. Wide Galaxy structure remains the aggregate catalogue layer.
 */
export function galaxyStarViewport(
  camera: CameraState | null,
): GalaxyStarViewport | null {
  if (!camera) return null;
  if (camera.distanceLy > 7_000) {
    // Wide view: use the authoritative region-plane extent, but keep Y
    // constrained to the galactic disk so the sample reads as a galaxy rather
    // than a full rectangular point cloud. This is a real-system sample lane,
    // not a procedural star field.
    return {
      minX: -50_000,
      maxX: 52_000,
      minY: -2_400,
      maxY: 2_400,
      minZ: -25_000,
      maxZ: 78_000,
      limit: 8_000,
      cameraDistanceLy: camera.distanceLy,
      wide: true,
    };
  }
  const horizontalRadius = Math.max(
    24,
    Math.min(7_400, camera.distanceLy * 0.82),
  );
  const verticalRadius = Math.max(
    24,
    Math.min(3_000, camera.distanceLy * 0.34),
  );
  const limit =
    camera.distanceLy > 3_500
      ? 40_000
      : camera.distanceLy > 1_400
        ? 24_000
        : camera.distanceLy > 450
          ? 12_000
          : camera.distanceLy > 140
            ? 5_000
            : 1_800;
  return {
    minX: camera.focusLy.x - horizontalRadius,
    maxX: camera.focusLy.x + horizontalRadius,
    minY: camera.focusLy.y - verticalRadius,
    maxY: camera.focusLy.y + verticalRadius,
    minZ: camera.focusLy.z - horizontalRadius,
    maxZ: camera.focusLy.z + horizontalRadius,
    limit,
    cameraDistanceLy: camera.distanceLy,
    wide: false,
  };
}

export function createCatalogueStarsContribution(
  systems: readonly CatalogueViewportSystem[],
  revision: number,
  truncated: boolean,
): SpatialContribution {
  const points: GalaxySystemPoint[] = systems.map((system) => ({
    systemId64: system.id64,
    name: system.name,
    positionLy: { x: system.x, y: system.y, z: system.z },
    ...(system.mainStarClass && {
      primaryStar: { type: system.mainStarClass },
    }),
  }));
  return {
    id: 'catalogue-viewport-stars',
    owner: 'CATALOGUE',
    revision,
    layers: [
      {
        id: 'catalogue-systems',
        version: 1,
        representation: 'AUTHORITATIVE',
        payload: { systems: points },
        targetCount: points.length,
        truncated,
      },
    ],
  };
}
