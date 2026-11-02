import type { SpatialContribution } from './contracts';
import {
  CATALOGUE_DENSITY_SCHEMA_VERSION,
  createCatalogueDensityContribution,
  validateCatalogueDensityPayload,
  type CatalogueDensityPayload,
} from './galaxy-density';
import { ApiError, type MapHeatmapPyramidResponse } from '$lib/api/client';

export type GalaxyDensityResult =
  | {
      kind: 'ready';
      payload: CatalogueDensityPayload;
      area: 'complete' | 'empty' | 'truncated';
    }
  | { kind: 'unavailable'; reason: string }
  | { kind: 'invalid'; reason: string }
  | { kind: 'none' };

/** Transport failures are distinct from a valid, empty published pyramid. */
export function classifyDensityError(
  error: unknown,
): Extract<GalaxyDensityResult, { kind: 'unavailable' | 'invalid' }> {
  if (
    error instanceof SyntaxError ||
    (error instanceof ApiError && error.body instanceof SyntaxError)
  ) {
    return { kind: 'invalid', reason: 'malformed-json' };
  }
  return {
    kind: 'unavailable',
    reason:
      error instanceof ApiError && error.status > 0
        ? `http-${error.status}`
        : 'network',
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function minBy(
  cells: MapHeatmapPyramidResponse['cells'],
  k: 'origin_x_ly' | 'origin_y_ly' | 'origin_z_ly',
) {
  return cells.reduce((m, c) => Math.min(m, c[k]), Number.POSITIVE_INFINITY);
}

function maxBy(
  cells: MapHeatmapPyramidResponse['cells'],
  k: 'origin_x_ly' | 'origin_y_ly' | 'origin_z_ly',
) {
  return cells.reduce((m, c) => Math.max(m, c[k]), Number.NEGATIVE_INFINITY);
}

export function mapHeatmapToDensityPayload(
  value: unknown,
): GalaxyDensityResult {
  // This endpoint uses the legacy lane when no published pyramid is available.
  // It must never be accepted as the catalogue's canonical density layer.
  if (isRecord(value) && value.source === 'legacy-fallback') {
    return { kind: 'none' };
  }
  // The facade casts external JSON to `MapHeatmapResponse`, so a malformed
  // `source: 'pyramid'` body (missing/malformed `bounds` or `cells`) is still
  // possible. Keep every response-shape dereference inside the guarded block
  // so a bad payload fails closed to `invalid` rather than throwing out of the
  // synchronous `$derived` evaluation that maps it.
  try {
    if (!isRecord(value) || value.source !== 'pyramid') {
      throw new Error('Density response must identify its pyramid source');
    }
    if (!isRecord(value.bounds) || !Array.isArray(value.cells)) {
      throw new Error('Density response must include bounds and a cells array');
    }
    for (const bound of [
      'min_x',
      'min_y',
      'min_z',
      'max_x',
      'max_y',
      'max_z',
    ]) {
      const coordinate = value.bounds[bound];
      if (coordinate !== null && !Number.isFinite(coordinate)) {
        throw new Error(
          'Density bounds must contain finite or null coordinates',
        );
      }
    }
    if (typeof value.truncated !== 'boolean') {
      throw new Error('Density response truncated must be boolean');
    }
    if (value.count !== value.cells.length) {
      throw new Error('Density response count must match its cells');
    }
    const res = value as unknown as MapHeatmapPyramidResponse;
    const cells = res.cells;
    // An empty published pyramid still passes the full metadata/count
    // validation. With no occupied cells, null bounds have zero extent.
    const originX =
      res.bounds.min_x ?? (cells.length ? minBy(cells, 'origin_x_ly') : 0);
    const originY =
      res.bounds.min_y ?? (cells.length ? minBy(cells, 'origin_y_ly') : 0);
    const originZ =
      res.bounds.min_z ?? (cells.length ? minBy(cells, 'origin_z_ly') : 0);
    const payload = validateCatalogueDensityPayload({
      schemaVersion: CATALOGUE_DENSITY_SCHEMA_VERSION,
      generationId: res.generation_id,
      pyramidVersion: res.spatial_pyramid_version,
      level: res.level,
      cellSizeLy: res.cell_size_ly,
      cellOriginLy: { x: originX, y: originY, z: originZ },
      boundsLy: {
        min: {
          x: res.bounds.min_x ?? originX,
          y: res.bounds.min_y ?? originY,
          z: res.bounds.min_z ?? originZ,
        },
        max: {
          x:
            res.bounds.max_x ??
            (cells.length
              ? maxBy(cells, 'origin_x_ly') + res.cell_size_ly
              : originX),
          y:
            res.bounds.max_y ??
            (cells.length
              ? maxBy(cells, 'origin_y_ly') + res.cell_size_ly
              : originY),
          z:
            res.bounds.max_z ??
            (cells.length
              ? maxBy(cells, 'origin_z_ly') + res.cell_size_ly
              : originZ),
        },
      },
      sourceSystemCount: res.source_system_count,
      coveredSystemCount: cells.reduce((n, c) => n + c.system_count, 0),
      coverageAsOf: res.coverage_at ?? new Date(0).toISOString(),
      complete: !res.truncated,
      cells: cells.map((c) => ({
        index: {
          x: Math.round((c.origin_x_ly - originX) / res.cell_size_ly),
          y: Math.round((c.origin_y_ly - originY) / res.cell_size_ly),
          z: Math.round((c.origin_z_ly - originZ) / res.cell_size_ly),
        },
        centroidLy: {
          x: c.centroid_x_ly,
          y: c.centroid_y_ly,
          z: c.centroid_z_ly,
        },
        systemCount: c.system_count,
      })),
    });
    return {
      kind: 'ready',
      payload,
      area: res.truncated ? 'truncated' : cells.length ? 'complete' : 'empty',
    };
  } catch (error) {
    return {
      kind: 'invalid',
      reason:
        error instanceof Error ? error.message : 'Invalid density payload',
    };
  }
}

export function densityContributionFrom(
  result: GalaxyDensityResult,
  revision: number,
):
  | (Extract<GalaxyDensityResult, { kind: 'ready' }> & {
      contribution: SpatialContribution;
    })
  | Exclude<GalaxyDensityResult, { kind: 'ready' }> {
  return result.kind === 'ready'
    ? {
        ...result,
        contribution: createCatalogueDensityContribution(
          result.payload,
          revision,
        ),
      }
    : result;
}

/**
 * Normalize a raw camera distance into the discrete `voxel_size` requested
 * from `/api/map/heatmap`. Keying the heatmap query by this normalized size
 * (rather than the raw floating-point distance) lets several nearby zoom stops
 * collapse onto one cache entry, so the query's `staleTime` can reuse a result
 * instead of minting a fresh request — and hitting the route's rate limit — on
 * every debounced zoom settle.
 */
export function heatmapVoxelSizeForDistance(distanceLy: number): number {
  return Math.max(200, Math.round(distanceLy / 200));
}
