import { describe, expect, it } from 'vitest';
import { parseId64 } from '$lib/domain/id64';

import {
  GALAXY_STAR_API_CUBE_BOUND_LY,
  GALAXY_WIDE_STAR_LIMIT,
  LOCAL_STAR_BUDGET_BANDS,
  LOCAL_STAR_ENTER_LY,
  LOCAL_STAR_EXIT_LY,
  type GalaxyDetailMode,
} from './galaxy-detail-policy';
import {
  createCatalogueStarsContribution,
  galaxyStarViewport,
  galaxyDiskNormalizedRadius,
  withinGalaxyDisk,
  GALACTIC_CENTRE_LY,
  GALACTIC_DISK_RADIUS_LY,
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
    expect(galaxyStarViewport(camera(LOCAL_STAR_ENTER_LY))?.limit).toBe(40_000);
    expect(
      galaxyStarViewport(camera(LOCAL_STAR_BUDGET_BANDS[0].aboveDistanceLy))
        ?.limit,
    ).toBe(24_000);
    expect(
      galaxyStarViewport(camera(LOCAL_STAR_BUDGET_BANDS[1].aboveDistanceLy))
        ?.limit,
    ).toBe(12_000);
    expect(
      galaxyStarViewport(camera(LOCAL_STAR_BUDGET_BANDS[2].aboveDistanceLy))
        ?.limit,
    ).toBe(5_000);
    expect(
      galaxyStarViewport(camera(LOCAL_STAR_BUDGET_BANDS[3].aboveDistanceLy))
        ?.limit,
    ).toBe(1_800);
    expect(galaxyStarViewport(camera(LOCAL_STAR_ENTER_LY + 1))).toMatchObject({
      limit: GALAXY_WIDE_STAR_LIMIT,
      wide: true,
    });
  });

  it('never exceeds the server 15,000 LY per-axis guard', () => {
    for (const distanceLy of [LOCAL_STAR_ENTER_LY, LOCAL_STAR_EXIT_LY]) {
      const viewport = galaxyStarViewport(camera(distanceLy), 'local')!;
      expect(viewport.wide).toBe(false);
      expect(viewport.maxX - viewport.minX).toBeLessThanOrEqual(
        GALAXY_STAR_API_CUBE_BOUND_LY,
      );
      expect(viewport.maxY - viewport.minY).toBeLessThanOrEqual(
        GALAXY_STAR_API_CUBE_BOUND_LY,
      );
      expect(viewport.maxZ - viewport.minZ).toBeLessThanOrEqual(
        GALAXY_STAR_API_CUBE_BOUND_LY,
      );
    }
  });

  it('uses the previous viewport mode through the hand-off hysteresis band', () => {
    let previousMode: GalaxyDetailMode = 'wide';
    const modes = [9_300, 8_900, 9_200, 9_600, 8_800].map((distanceLy) => {
      const viewport = galaxyStarViewport(camera(distanceLy), previousMode)!;
      previousMode = viewport.wide ? 'wide' : 'local';
      return previousMode;
    });
    expect(modes).toEqual(['wide', 'local', 'local', 'wide', 'local']);
  });

  it('waits for a camera before selecting a viewport', () => {
    expect(galaxyStarViewport(null)).toBeNull();
  });

  it('uses a bounded real-system sample lane at galaxy scale', () => {
    const viewport = galaxyStarViewport(camera(120_000))!;
    expect(viewport.wide).toBe(true);
    expect(viewport.limit).toBe(GALAXY_WIDE_STAR_LIMIT);
    expect(viewport.maxY - viewport.minY).toBeLessThan(
      GALAXY_STAR_API_CUBE_BOUND_LY,
    );
    expect(viewport.maxX - viewport.minX).toBeGreaterThan(
      GALAXY_STAR_API_CUBE_BOUND_LY,
    );
    expect(viewport.maxZ - viewport.minZ).toBeGreaterThan(
      GALAXY_STAR_API_CUBE_BOUND_LY,
    );
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

describe('wide galaxy-scale disk shaping', () => {
  it('keeps the solar neighbourhood and the galactic core', () => {
    expect(withinGalaxyDisk(0, 0)).toBe(true);
    expect(withinGalaxyDisk(GALACTIC_CENTRE_LY.x, GALACTIC_CENTRE_LY.z)).toBe(
      true,
    );
    expect(withinGalaxyDisk(1_000, 1_000)).toBe(true);
  });

  it('drops the rectangular sample corners so nothing clips square', () => {
    expect(withinGalaxyDisk(-50_000, 78_000)).toBe(false);
    expect(withinGalaxyDisk(52_000, -25_000)).toBe(false);
    expect(withinGalaxyDisk(0, 90_000)).toBe(false);
  });

  it('measures normalised radius from the galactic centre', () => {
    expect(
      galaxyDiskNormalizedRadius(GALACTIC_CENTRE_LY.x, GALACTIC_CENTRE_LY.z),
    ).toBe(0);
    expect(
      galaxyDiskNormalizedRadius(
        GALACTIC_CENTRE_LY.x + GALACTIC_DISK_RADIUS_LY,
        GALACTIC_CENTRE_LY.z,
      ),
    ).toBeCloseTo(1);
  });

  it('is deterministic for a given position', () => {
    expect(withinGalaxyDisk(30_000, 60_000)).toBe(
      withinGalaxyDisk(30_000, 60_000),
    );
  });
});
