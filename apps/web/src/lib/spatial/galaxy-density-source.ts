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

export function mapHeatmapToDensityPayload(
  res: MapHeatmapResponse,
): CatalogueDensityPayload | null {
  if (res.source !== 'pyramid') return null;
  const cells = res.cells ?? [];
  if (!cells.length) return null;
  const originX = res.bounds?.min_x ?? minBy(cells, 'origin_x_ly');
  const originY = res.bounds?.min_y ?? minBy(cells, 'origin_y_ly');
  const originZ = res.bounds?.min_z ?? minBy(cells, 'origin_z_ly');
  try {
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
          x: res.bounds.max_x ?? originX + res.cell_size_ly,
          y: res.bounds.max_y ?? originY + res.cell_size_ly,
          z: res.bounds.max_z ?? originZ + res.cell_size_ly,
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

export async function loadGalaxyDensityContribution(
  query: { voxel_size?: number; min_systems?: number; max_cells?: number },
  revision: number,
  signal?: AbortSignal,
): Promise<SpatialContribution | null> {
  const data = await getMapHeatmap(query, signal);
  return densityContributionFrom(data, revision);
}
