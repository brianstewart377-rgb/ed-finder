import type { ExploreSystem } from '$lib/api/client';
import type { Id64 } from '$lib/domain/id64';
import type {
  GalaxySceneContract,
  GalaxySystemPoint,
  GalaxySystemsPayload,
  Vec3Ly,
} from './contracts';

const finiteCoordinate = (value: number | null | undefined): value is number =>
  typeof value === 'number' && Number.isFinite(value);

export function mapExploreSystemPoint(
  system: ExploreSystem,
): GalaxySystemPoint | null {
  const coords = system.coords;
  if (
    !coords ||
    !finiteCoordinate(coords.x) ||
    !finiteCoordinate(coords.y) ||
    !finiteCoordinate(coords.z)
  ) {
    return null;
  }
  return {
    systemId64: system.id64,
    name: system.name?.trim() || `System ${system.id64}`,
    positionLy: { x: coords.x, y: coords.y, z: coords.z },
  };
}

function sceneCamera(points: readonly GalaxySystemPoint[]): {
  focusLy: Vec3Ly;
  distanceLy: number;
} {
  if (!points.length) {
    return { focusLy: { x: 0, y: 0, z: 0 }, distanceLy: 80 };
  }
  const focusLy = points.reduce(
    (sum, point) => ({
      x: sum.x + point.positionLy.x / points.length,
      y: sum.y + point.positionLy.y / points.length,
      z: sum.z + point.positionLy.z / points.length,
    }),
    { x: 0, y: 0, z: 0 },
  );
  const radius = points.reduce(
    (largest, point) =>
      Math.max(
        largest,
        Math.hypot(
          point.positionLy.x - focusLy.x,
          point.positionLy.y - focusLy.y,
          point.positionLy.z - focusLy.z,
        ),
      ),
    0,
  );
  return { focusLy, distanceLy: Math.max(30, radius * 2.4) };
}

/** Map typed API truth into the renderer-neutral Finder contribution. */
export function buildExploreGalaxyScene(
  systems: readonly ExploreSystem[],
  selectedSystemId64: Id64 | null,
  revision: number,
): GalaxySceneContract {
  const points = systems.flatMap((system) => {
    const point = mapExploreSystemPoint(system);
    return point ? [point] : [];
  });
  const camera = sceneCamera(points);
  const payload: GalaxySystemsPayload = { systems: points };
  return {
    kind: 'galaxy',
    revision,
    camera: {
      ...camera,
      bearingRad: 0,
      pitchRad: 0.55,
      projection: 'perspective',
      revision,
    },
    selection: selectedSystemId64
      ? [{ kind: 'system', systemId64: selectedSystemId64 }]
      : [],
    contributions: [
      {
        id: 'finder-results',
        owner: 'FINDER',
        revision,
        layers: [
          {
            id: 'finder-systems',
            version: 1,
            representation: 'AUTHORITATIVE',
            payload,
            targetCount: points.length,
            truncated: false,
          },
        ],
      },
    ],
  };
}
