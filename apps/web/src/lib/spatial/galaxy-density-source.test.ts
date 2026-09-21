import { describe, expect, it } from 'vitest';
import {
  densityContributionFrom,
  heatmapVoxelSizeForDistance,
  mapHeatmapToDensityPayload,
} from './galaxy-density-source';
import type { MapHeatmapResponse } from '$lib/api/client';

const pyramid = {
  source: 'pyramid' as const,
  generation_id: 'g1',
  spatial_generation_id: 's1',
  spatial_pyramid_version: 'v1',
  source_system_count: 3,
  coverage_at: '2026-09-19T00:00:00Z',
  level: 3,
  cell_size_ly: 100,
  voxel_size: 100,
  bounds: {
    min_x: 0,
    max_x: 200,
    min_y: 0,
    max_y: 100,
    min_z: 0,
    max_z: 100,
  },
  cells: [
    {
      origin_x_ly: 0,
      origin_y_ly: 0,
      origin_z_ly: 0,
      centroid_x_ly: 50,
      centroid_y_ly: 50,
      centroid_z_ly: 50,
      system_count: 2,
    },
    {
      origin_x_ly: 100,
      origin_y_ly: 0,
      origin_z_ly: 0,
      centroid_x_ly: 150,
      centroid_y_ly: 50,
      centroid_z_ly: 50,
      system_count: 1,
    },
  ],
  count: 2,
  max_cells: 40000,
  truncated: false,
};

describe('mapHeatmapToDensityPayload', () => {
  it('maps a pyramid response into a validated payload', () => {
    const p = mapHeatmapToDensityPayload(pyramid)!;
    expect(p.generationId).toBe('g1');
    expect(p.cellSizeLy).toBe(100);
    expect(p.coveredSystemCount).toBe(3);
    expect(p.complete).toBe(true);
    expect(p.cells).toHaveLength(2);
    expect(p.cells[1].index).toEqual({ x: 1, y: 0, z: 0 });
  });

  it('returns null on legacy-fallback', () => {
    expect(
      mapHeatmapToDensityPayload({ source: 'legacy-fallback', cells: [] }),
    ).toBeNull();
  });

  it('returns null (fail-closed) on a malformed pyramid payload', () => {
    expect(
      mapHeatmapToDensityPayload({ ...pyramid, cell_size_ly: 0 }),
    ).toBeNull();
  });

  it('maps a multi-cell pyramid with null bounds.max_* to a non-null payload whose boundsLy.max covers all cell centroids', () => {
    const nullMaxBounds: MapHeatmapResponse = {
      ...pyramid,
      bounds: {
        min_x: 0,
        max_x: null,
        min_y: 0,
        max_y: null,
        min_z: 0,
        max_z: null,
      },
    };
    const p = mapHeatmapToDensityPayload(nullMaxBounds);
    expect(p).not.toBeNull();
    // max origin (100) + cell_size_ly (100) = 200 on x; y/z stay at origin + cell size (100)
    expect(p!.boundsLy.max).toEqual({ x: 200, y: 100, z: 100 });
    for (const cell of p!.cells) {
      expect(cell.centroidLy.x).toBeLessThanOrEqual(p!.boundsLy.max.x);
      expect(cell.centroidLy.y).toBeLessThanOrEqual(p!.boundsLy.max.y);
      expect(cell.centroidLy.z).toBeLessThanOrEqual(p!.boundsLy.max.z);
    }
  });

  it('returns null for an empty cells pyramid response', () => {
    const empty: MapHeatmapResponse = { ...pyramid, cells: [] };
    expect(mapHeatmapToDensityPayload(empty)).toBeNull();
  });

  it('fails closed (null, no throw) when a pyramid response is missing bounds', () => {
    const malformed = {
      ...pyramid,
      bounds: undefined,
    } as unknown as MapHeatmapResponse;
    expect(() => mapHeatmapToDensityPayload(malformed)).not.toThrow();
    expect(mapHeatmapToDensityPayload(malformed)).toBeNull();
  });

  it('fails closed (null, no throw) when a pyramid response has malformed cells', () => {
    const malformed = {
      ...pyramid,
      cells: 'not-an-array',
    } as unknown as MapHeatmapResponse;
    expect(() => mapHeatmapToDensityPayload(malformed)).not.toThrow();
    expect(mapHeatmapToDensityPayload(malformed)).toBeNull();
  });
});

describe('heatmapVoxelSizeForDistance', () => {
  it('collapses nearby camera distances onto one voxel size so the query can reuse a cached result', () => {
    expect(heatmapVoxelSizeForDistance(118_000)).toBe(590);
    expect(heatmapVoxelSizeForDistance(118_050)).toBe(590);
    expect(heatmapVoxelSizeForDistance(118_000)).toBe(
      heatmapVoxelSizeForDistance(118_050),
    );
  });

  it('floors at the endpoint minimum voxel size', () => {
    expect(heatmapVoxelSizeForDistance(100)).toBe(200);
    expect(heatmapVoxelSizeForDistance(0)).toBe(200);
  });
});

describe('densityContributionFrom', () => {
  it('returns null when data is undefined', () => {
    expect(densityContributionFrom(undefined, 1)).toBeNull();
  });

  it('returns null when the response maps to null (legacy-fallback)', () => {
    const legacy: MapHeatmapResponse = { source: 'legacy-fallback', cells: [] };
    expect(densityContributionFrom(legacy, 1)).toBeNull();
  });

  it('returns a non-null contribution for a valid pyramid response', () => {
    const contribution = densityContributionFrom(pyramid, 1);
    expect(contribution).not.toBeNull();
    expect(contribution?.owner).toBe('CATALOGUE');
    expect(contribution?.revision).toBe(1);
    expect(contribution?.layers[0]?.id).toBe('catalogue-density');
  });
});
