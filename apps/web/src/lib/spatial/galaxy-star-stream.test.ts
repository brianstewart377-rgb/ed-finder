import { describe, expect, it } from 'vitest';
import { parseId64 } from '$lib/domain/id64';

import {
  createCatalogueStarsContribution,
  galaxyStarViewport,
} from './galaxy-star-stream';

const camera = (distanceLy: number) => ({
  focusLy: { x: 100, y: -20, z: 300 },
  distanceLy,
  bearingRad: 0,
  pitchRad: 0.6,
  projection: 'perspective' as const,
  revision: 1,
});

describe('real catalogue star streaming policy', () => {
  it('uses more exact-star capacity at medium range and less on close inspection', () => {
    expect(galaxyStarViewport(camera(5_000))?.limit).toBe(40_000);
    expect(galaxyStarViewport(camera(1_000))?.limit).toBe(12_000);
    expect(galaxyStarViewport(camera(80))?.limit).toBe(1_800);
    expect(galaxyStarViewport(camera(7_001))).toMatchObject({
      limit: 8_000,
      wide: true,
    });
  });

  it('never exceeds the server 15,000 LY per-axis guard', () => {
    const viewport = galaxyStarViewport(camera(7_000))!;
    expect(viewport.maxX - viewport.minX).toBeLessThanOrEqual(15_000);
    expect(viewport.maxY - viewport.minY).toBeLessThanOrEqual(15_000);
    expect(viewport.maxZ - viewport.minZ).toBeLessThanOrEqual(15_000);
  });

  it('uses a bounded real-system sample lane at galaxy scale', () => {
    const viewport = galaxyStarViewport(camera(120_000))!;
    expect(viewport.wide).toBe(true);
    expect(viewport.limit).toBe(8_000);
    expect(viewport.maxY - viewport.minY).toBeLessThan(15_000);
    expect(viewport.maxX - viewport.minX).toBeGreaterThan(15_000);
    expect(viewport.maxZ - viewport.minZ).toBeGreaterThan(15_000);
  });

  it('maps only returned catalogue positions and preserves truncation', () => {
    const contribution = createCatalogueStarsContribution(
      [
        {
          id64: parseId64('9007199254740993'),
          name: 'Exact Reach',
          x: 1.25,
          y: -9,
          z: 72.5,
          mainStarClass: 'A',
          populated: false,
        },
      ],
      8,
      true,
    );
    expect(contribution.owner).toBe('CATALOGUE');
    expect(contribution.layers[0]).toMatchObject({
      id: 'catalogue-systems',
      targetCount: 1,
      truncated: true,
      payload: {
        systems: [
          {
            systemId64: '9007199254740993',
            positionLy: { x: 1.25, y: -9, z: 72.5 },
            primaryStar: { type: 'A' },
          },
        ],
      },
    });
  });
});
