import { describe, expect, it } from 'vitest';
import type { MapViewportSystem } from '$lib/api/generated/types.gen';
import { parseId64 } from '$lib/domain/id64';

import type { GalaxySystemsPayload } from './contracts';
import {
  type CatalogueViewportSystem,
  createCatalogueStarsContribution,
  galaxyStarViewport,
  galaxyDiskNormalizedRadius,
  withinGalaxyDisk,
  GALACTIC_CENTRE_LY,
  GALACTIC_DISK_RADIUS_LY,
} from './galaxy-star-stream';
import { stellarPresentation } from './stellar-presentation';

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

  it('renders raw catalogue subclasses as distinct families while preserving the source class', () => {
    const mainStarClasses = [
      'G2',
      'K5',
      'B5',
      'M3',
      'DA6',
      'N0',
      'H0',
      'WC8',
      '',
      'X9',
    ];
    const apiSystems: MapViewportSystem[] = mainStarClasses.map(
      (main_star_class, index) => ({
        id64: 100 + index,
        name: `Catalogue system ${index}`,
        x: index,
        y: -index,
        z: index * 2,
        main_star_class,
        populated: false,
      }),
    );
    // The API facade renames this single field; it does not derive a subtype.
    const systems: CatalogueViewportSystem[] = apiSystems.map((system) => ({
      id64: parseId64(String(system.id64)),
      name: system.name,
      x: system.x,
      y: system.y,
      z: system.z,
      mainStarClass: system.main_star_class,
      populated: system.populated,
    }));
    const contribution = createCatalogueStarsContribution(systems, 1, false);
    const payload = contribution.layers[0]!.payload as GalaxySystemsPayload;
    // This is the same descriptor input consumed by the Babylon star renderer.
    const glyphs = payload.systems.map(
      (point) => stellarPresentation(point.primaryStar).glyph,
    );

    expect(glyphs).toEqual([
      'main-sequence-g',
      'main-sequence-k',
      'main-sequence-b',
      'main-sequence-m',
      'white-dwarf',
      'neutron',
      'black-hole',
      'wolf-rayet',
      'unknown',
      'unknown',
    ]);
    expect(new Set(glyphs.slice(0, 8)).size).toBe(8);
    expect(glyphs.slice(0, 8)).not.toContain('unknown');
    expect(
      payload.systems.map((point) => point.primaryStar?.type ?? ''),
    ).toEqual(mainStarClasses);
    expect(payload.systems.every((point) => !point.primaryStar?.subtype)).toBe(
      true,
    );
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
