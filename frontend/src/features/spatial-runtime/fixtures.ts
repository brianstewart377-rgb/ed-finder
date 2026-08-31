import type { SpatialSceneContract, SpatialTargetId } from './contracts';

export const FIXTURE_TIERS = [20_000, 40_000, 100_000, 500_000, 1_000_000] as const;
export type FixtureTier = typeof FIXTURE_TIERS[number];

function random01(index: number, axis: number): number {
  let value = (index + 1) * 0x9e3779b1 ^ (axis + 11) * 0x85ebca6b;
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d);
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b);
  return ((value ^ (value >>> 16)) >>> 0) / 0xffffffff;
}

export function createSpatialFixture(count: FixtureTier): SpatialSceneContract {
  const selectedTargetId: SpatialTargetId = 'system:fixture-0';
  return {
    revision: 1,
    camera: { centerLy: [0, 0, 0], distanceLy: 40_000, yawRadians: 0, pitchRadians: Math.PI / 2, mode: 'top-down' },
    selectedTargetId,
    highlightedTargetIds: ['system:fixture-1'],
    referenceTargetIds: ['system:fixture-2'],
    contributions: [{
      id: 'deterministic-galaxy', revision: 1,
      objects: Array.from({ length: count }, (_, index) => ({
        id: `star-${index}`,
        targetId: `system:fixture-${index}` as SpatialTargetId,
        kind: 'system' as const,
        truthClass: 'factual' as const,
        positionLy: [(random01(index, 0) - .5) * 120_000, (random01(index, 1) - .5) * 4_000, (random01(index, 2) - .5) * 120_000] as const,
        color: [0.65 + random01(index, 3) * .35, 0.75, 1, 1] as const,
        importance: index < 3 ? 1 : random01(index, 4),
      })),
    }],
  };
}
