import { describe, expect, it } from 'vitest';
import {
  classifyDensityError,
  densityContributionFrom,
  heatmapVoxelSizeForDistance,
  mapHeatmapToDensityPayload,
  type GalaxyDensityResult,
} from './galaxy-density-source';
import { ApiError, type MapHeatmapPyramidResponse } from '$lib/api/client';

const pyramid: MapHeatmapPyramidResponse = {
  source: 'pyramid',
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
  max_cells: 40_000,
  truncated: false,
};

function readyResult(value: unknown) {
  const result = mapHeatmapToDensityPayload(value);
  expect(result.kind).toBe('ready');
  if (result.kind !== 'ready') throw new Error('Expected valid density');
  return result;
}

describe('mapHeatmapToDensityPayload', () => {
  it('maps a pyramid response into an explicitly ready validated payload', () => {
    const result = readyResult(pyramid);
    expect(result.area).toBe('complete');
    expect(result.payload.generationId).toBe('g1');
    expect(result.payload.cellSizeLy).toBe(100);
    expect(result.payload.coveredSystemCount).toBe(3);
    expect(result.payload.complete).toBe(true);
    expect(result.payload.cells).toHaveLength(2);
    expect(result.payload.cells[1].index).toEqual({ x: 1, y: 0, z: 0 });
  });

  it('reports no published pyramid when the endpoint returns its fallback', () => {
    expect(
      mapHeatmapToDensityPayload({ source: 'legacy-fallback', cells: [] }),
    ).toEqual({ kind: 'none' });
  });

  it('never accepts a legacy non-pyramid response even when it has cells', () => {
    expect(
      mapHeatmapToDensityPayload({ ...pyramid, source: 'legacy-fallback' }),
    ).toEqual({ kind: 'none' });
  });

  it.each([
    ['null response', null],
    ['missing source', {}],
    ['unrecognized source', { source: 'unknown', cells: [] }],
    ['zero cell size', { ...pyramid, cell_size_ly: 0 }],
    ['missing bounds', { ...pyramid, bounds: undefined }],
    ['missing cells', { ...pyramid, cells: undefined }],
    ['malformed cells', { ...pyramid, cells: 'not-an-array' }],
    ['missing truncation', { ...pyramid, truncated: undefined }],
    ['mismatched cell count', { ...pyramid, count: 0 }],
  ])('reports invalid without throwing for %s', (_label, value) => {
    expect(() => mapHeatmapToDensityPayload(value)).not.toThrow();
    expect(mapHeatmapToDensityPayload(value)).toMatchObject({
      kind: 'invalid',
      reason: expect.any(String),
    });
  });

  it('infers null maximum bounds from all cells while retaining validation', () => {
    const result = readyResult({
      ...pyramid,
      bounds: {
        min_x: 0,
        max_x: null,
        min_y: 0,
        max_y: null,
        min_z: 0,
        max_z: null,
      },
    });
    const payload = result.payload;
    expect(payload.boundsLy.max).toEqual({ x: 200, y: 100, z: 100 });
    for (const cell of payload.cells) {
      expect(cell.centroidLy.x).toBeLessThanOrEqual(payload.boundsLy.max.x);
      expect(cell.centroidLy.y).toBeLessThanOrEqual(payload.boundsLy.max.y);
      expect(cell.centroidLy.z).toBeLessThanOrEqual(payload.boundsLy.max.z);
    }
  });

  it('reports a valid empty published area separately from no pyramid', () => {
    const result = readyResult({
      ...pyramid,
      cells: [],
      count: 0,
      source_system_count: 0,
    });
    expect(result.area).toBe('empty');
    expect(result.payload.cells).toEqual([]);
    expect(result.payload.coveredSystemCount).toBe(0);
    expect(result.payload.complete).toBe(true);
  });

  it('accepts an empty published pyramid with null bounds as zero extent', () => {
    const result = readyResult({
      ...pyramid,
      cells: [],
      count: 0,
      source_system_count: 0,
      bounds: {
        min_x: null,
        max_x: null,
        min_y: null,
        max_y: null,
        min_z: null,
        max_z: null,
      },
    });
    expect(result.area).toBe('empty');
    expect(result.payload.boundsLy).toEqual({
      min: { x: 0, y: 0, z: 0 },
      max: { x: 0, y: 0, z: 0 },
    });
  });

  it.each([
    ['unreconciled source count', { source_system_count: 3 }],
    ['invalid metadata', { generation_id: '' }],
    ['invalid bounds', { bounds: {} }],
  ])('still rejects empty payloads with %s', (_label, invalidField) => {
    expect(
      mapHeatmapToDensityPayload({
        ...pyramid,
        cells: [],
        count: 0,
        source_system_count: 0,
        ...invalidField,
      }).kind,
    ).toBe('invalid');
  });

  it('reports a valid truncated area without pretending coverage is complete', () => {
    const result = readyResult({
      ...pyramid,
      cells: pyramid.cells.slice(0, 1),
      count: 1,
      truncated: true,
    });
    expect(result.area).toBe('truncated');
    expect(result.payload.complete).toBe(false);
    expect(result.payload.coveredSystemCount).toBe(2);
    expect(result.payload.sourceSystemCount).toBe(3);
  });
});

describe('classifyDensityError', () => {
  it('reports HTTP 503 as unavailable', () => {
    expect(
      classifyDensityError(new ApiError(503, '/api/map/heatmap', {})),
    ).toEqual({ kind: 'unavailable', reason: 'http-503' });
  });

  it.each([
    new TypeError('Failed to fetch'),
    new ApiError(0, '/api/map/heatmap', new TypeError('Failed to fetch')),
  ])('reports network failures as unavailable', (error) => {
    expect(classifyDensityError(error)).toEqual({
      kind: 'unavailable',
      reason: 'network',
    });
  });

  it.each([
    new SyntaxError('Unexpected token'),
    new ApiError(200, '/api/map/heatmap', new SyntaxError('Unexpected token')),
  ])('reports malformed JSON as invalid', (error) => {
    expect(classifyDensityError(error)).toEqual({
      kind: 'invalid',
      reason: 'malformed-json',
    });
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
  it.each<GalaxyDensityResult>([
    { kind: 'none' },
    { kind: 'unavailable', reason: 'http-503' },
    { kind: 'invalid', reason: 'Invalid bounds' },
  ])(
    'retains the explicit $kind result without making a contribution',
    (result) => {
      expect(densityContributionFrom(result, 1)).toEqual(result);
    },
  );

  it('returns a ready contribution for a validated pyramid', () => {
    const result = densityContributionFrom(readyResult(pyramid), 1);
    expect(result.kind).toBe('ready');
    if (result.kind !== 'ready')
      throw new Error('Expected density contribution');
    expect(result.contribution.owner).toBe('CATALOGUE');
    expect(result.contribution.revision).toBe(1);
    expect(result.contribution.layers[0]?.id).toBe('catalogue-density');
  });
});
