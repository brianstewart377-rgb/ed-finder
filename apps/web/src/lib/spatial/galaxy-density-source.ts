import type { SpatialContribution } from './contracts';
import {
  CATALOGUE_DENSITY_SCHEMA_VERSION,
  createCatalogueDensityContribution,
  validateCatalogueDensityPayload,
  type CatalogueDensityPayload,
} from './galaxy-density';
import {
  getMapHeatmap,
  type MapHeatmapResponse,
  type MapHeatmapPyramidResponse,
} from '$lib/api/client';

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
  res: MapHeatmapResponse,
): CatalogueDensityPayload | null {
  if (res.source !== 'pyramid') return null;
  // The facade casts external JSON to `MapHeatmapResponse`, so a malformed
  // `source: 'pyramid'` body (missing/malformed `bounds` or `cells`) is still
  // possible. Keep every response-shape dereference inside the guarded block
  // so a bad payload fails closed to `null` rather than throwing out of the
  // synchronous `$derived` evaluation that maps it.
  try {
    const cells = res.cells ?? [];
    if (!cells.length) return null;
    const originX = res.bounds.min_x ?? minBy(cells, 'origin_x_ly');
    const originY = res.bounds.min_y ?? minBy(cells, 'origin_y_ly');
    const originZ = res.bounds.min_z ?? minBy(cells, 'origin_z_ly');
    return validateCatalogueDensityPayload({
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
          x: res.bounds.max_x ?? maxBy(cells, 'origin_x_ly') + res.cell_size_ly,
          y: res.bounds.max_y ?? maxBy(cells, 'origin_y_ly') + res.cell_size_ly,
          z: res.bounds.max_z ?? maxBy(cells, 'origin_z_ly') + res.cell_size_ly,
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
  } catch {
    return null;
  }
}

export function densityContributionFrom(
  data: MapHeatmapResponse | undefined,
  revision: number,
): SpatialContribution | null {
  if (!data) return null;
  const payload = mapHeatmapToDensityPayload(data);
  return payload ? createCatalogueDensityContribution(payload, revision) : null;
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

export async function loadGalaxyDensityContribution(
  query: { voxel_size?: number; min_systems?: number; max_cells?: number },
  revision: number,
  signal?: AbortSignal,
): Promise<SpatialContribution | null> {
  const data = await getMapHeatmap(query, signal);
  return densityContributionFrom(data, revision);
}
