import type { Id64 } from '$lib/domain/id64';
import type {
  CameraState,
  GalaxySystemPoint,
  SpatialContribution,
} from './contracts';
import {
  galaxyDetailMode,
  galaxyLocalStarLimit,
  GALAXY_WIDE_STAR_LIMIT,
  LOCAL_STAR_MIN_RADIUS_LY,
  LOCAL_STAR_MAX_HORIZONTAL_RADIUS_LY,
  LOCAL_STAR_MAX_VERTICAL_RADIUS_LY,
  type GalaxyDetailMode,
} from './galaxy-detail-policy';

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

// ---------------------------------------------------------------------------
// Galactic-disk shaping for the wide sample lane.
//
// The API returns a real-system sample bounded by an axis-aligned box. Drawn
// verbatim that reads as a rectangular slab of points with hard square edges.
// The Milky Way is a disk, so at galaxy scale we keep only the sample that
// falls inside the canonical galactic disk and feather the rim so the edge
// dissolves instead of clipping to a square (or a hard circle). Positions are
// never moved — this is a visibility mask over real coordinates.
// ---------------------------------------------------------------------------

/** Sagittarius A* sits ~25,900 LY galactic-north of Sol along +Z. */
export const GALACTIC_CENTRE_LY = { x: 0, z: 25_900 } as const;
/** Canonical playable-disk radius in light years. */
export const GALACTIC_DISK_RADIUS_LY = 46_000;
const DISK_CORE_FRACTION = 0.86;
const DISK_RIM_FRACTION = 1.08;

/** Deterministic 0..1 hash of a light-year XZ position (stable per render). */
function galaxyPositionHash(x: number, z: number): number {
  const seed = Math.sin(x * 12.9898 + z * 78.233) * 43_758.5453;
  return seed - Math.floor(seed);
}

/** Normalised distance from the galactic centre in the disk plane (1 == rim). */
export function galaxyDiskNormalizedRadius(x: number, z: number): number {
  const dx = (x - GALACTIC_CENTRE_LY.x) / GALACTIC_DISK_RADIUS_LY;
  const dz = (z - GALACTIC_CENTRE_LY.z) / GALACTIC_DISK_RADIUS_LY;
  return Math.hypot(dx, dz);
}

/**
 * True when a wide-sample star should remain visible. Everything inside the
 * core radius is kept; the rim is probabilistically feathered with a
 * position-stable hash so the disk edge softens rather than clipping.
 */
export function withinGalaxyDisk(x: number, z: number): boolean {
  const radius = galaxyDiskNormalizedRadius(x, z);
  if (radius <= DISK_CORE_FRACTION) return true;
  if (radius >= DISK_RIM_FRACTION) return false;
  const keepProbability =
    (DISK_RIM_FRACTION - radius) / (DISK_RIM_FRACTION - DISK_CORE_FRACTION);
  return galaxyPositionHash(x, z) < keepProbability;
}

/**
 * Exact-star detail is bounded to a 15,000 LY API cube. The deliberately
 * descending budget keeps the medium view rich while close inspection sheds
 * clutter. Wide Galaxy structure remains the aggregate catalogue layer.
 */
export function galaxyStarViewport(
  camera: CameraState | null,
  previousMode: GalaxyDetailMode = 'wide',
): GalaxyStarViewport | null {
  if (!camera) return null;
  if (galaxyDetailMode(camera.distanceLy, previousMode) === 'wide') {
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
      limit: GALAXY_WIDE_STAR_LIMIT,
      cameraDistanceLy: camera.distanceLy,
      wide: true,
    };
  }
  const horizontalRadius = Math.max(
    LOCAL_STAR_MIN_RADIUS_LY,
    Math.min(LOCAL_STAR_MAX_HORIZONTAL_RADIUS_LY, camera.distanceLy * 0.82),
  );
  const verticalRadius = Math.max(
    LOCAL_STAR_MIN_RADIUS_LY,
    Math.min(LOCAL_STAR_MAX_VERTICAL_RADIUS_LY, camera.distanceLy * 0.34),
  );
  const limit = galaxyLocalStarLimit(camera.distanceLy);
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
