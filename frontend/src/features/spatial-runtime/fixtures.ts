import type { GalaxySceneContract, SpatialObject, SpatialTarget } from './contracts';

export const FIXTURE_TIERS = [20_000, 40_000, 100_000, 500_000, 1_000_000] as const;
export type FixtureTier = typeof FIXTURE_TIERS[number];

function random01(index: number, axis: number): number {
  let value = (index + 1) * 0x9e3779b1 ^ (axis + 11) * 0x85ebca6b;
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
  return ((value ^ (value >>> 16)) >>> 0) / 0xffffffff;
}
export function fixtureSystemTarget(index: number): SpatialTarget { return { kind: 'system', systemId64: String(10_000_000_000_000 + index) }; }

export function createSpatialFixture(count: FixtureTier): GalaxySceneContract {
  const objects: SpatialObject[] = Array.from({ length: count }, (_, index) => ({
    id: `star-${index}`, target: fixtureSystemTarget(index), representation: 'AUTHORITATIVE',
    positionLy: { x: (random01(index, 0) - .5) * 120_000, y: (random01(index, 1) - .5) * 4_000, z: (random01(index, 2) - .5) * 120_000 },
    color: [0.65 + random01(index, 3) * .35, 0.75, 1, 1], importance: index < 3 ? 1 : random01(index, 4),
  }));
  return {
    kind: 'galaxy', revision: 1,
    camera: { focusLy: { x: 0, y: 0, z: 0 }, distanceLy: 40_000, bearingRad: 0, pitchRad: Math.PI / 2, projection: 'orthographic', revision: 1 },
    selection: [fixtureSystemTarget(0)],
    contributions: [{ id: 'deterministic-galaxy', owner: 'FINDER', revision: 1, layers: [{ id: 'synthetic-stars', version: 1, representation: 'AUTHORITATIVE', payload: objects, targetCount: count, truncated: false }] }],
  };
}
