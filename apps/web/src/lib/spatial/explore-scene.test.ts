import { describe, expect, it } from 'vitest';
import type { ExploreSystem } from '$lib/api/client';
import { parseId64 } from '$lib/domain/id64';
import { buildExploreGalaxyScene } from './explore-scene';

describe('Explore Galaxy scene mapper', () => {
  it('maps canonical light-year coordinates and unsafe id64 strings losslessly', () => {
    const id64 = parseId64('9007199254740993');
    const scene = buildExploreGalaxyScene(
      [
        {
          id64,
          name: 'Lossless Reach',
          coords: { x: 12.5, y: -4, z: 80.25 },
        },
      ] as ExploreSystem[],
      id64,
      7,
    );

    expect(scene.selection).toEqual([{ kind: 'system', systemId64: id64 }]);
    expect(scene.contributions[0]?.layers[0]?.payload).toEqual({
      systems: [
        {
          systemId64: '9007199254740993',
          name: 'Lossless Reach',
          positionLy: { x: 12.5, y: -4, z: 80.25 },
        },
      ],
    });
  });

  it('omits incomplete and non-finite coordinates instead of inventing them', () => {
    const systems = [
      { id64: parseId64('1'), name: 'Unknown', coords: null },
      {
        id64: parseId64('2'),
        name: 'Partial',
        coords: { x: 1, y: null, z: 3 },
      },
      {
        id64: parseId64('3'),
        name: 'Invalid',
        coords: { x: Infinity, y: 2, z: 3 },
      },
    ] as ExploreSystem[];

    const scene = buildExploreGalaxyScene(systems, null, 1);
    expect(scene.contributions[0]?.layers[0]?.targetCount).toBe(0);
    expect(scene.contributions[0]?.layers[0]?.payload).toEqual({ systems: [] });
  });
});
