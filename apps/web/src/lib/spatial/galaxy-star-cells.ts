import type { CatalogueViewportRequest } from '$lib/api/client';
import type { Vec3Ly } from './contracts';
import {
  GALAXY_STAR_API_CUBE_BOUND_LY,
  LOCAL_STAR_BUDGET_BANDS,
} from './galaxy-detail-policy';
import { GALAXY_CATALOGUE_BOUNDS } from './galaxy-star-footprint';
import type { GalaxyStarViewport } from './galaxy-star-stream';

export const GALAXY_STAR_CELL_CACHE_LIMIT = 64;
export const MAX_GALAXY_STAR_ACTIVE_CELLS = 16;
const CELL_HALO_FRACTION = 0.15;
const Y_QUANTUM_LY = 250;
const MAX_CELL_SIZE_LY = 10_000;
const BOUNDS_EPSILON_LY = 1e-6;

export type GalaxyStarCell = Readonly<{
  key: string;
  request: CatalogueViewportRequest;
  centre: Vec3Ly;
  cellSizeLy: number;
}>;

function baseCellSize(viewport: GalaxyStarViewport): number {
  if (
    viewport.wide ||
    viewport.cameraDistanceLy > LOCAL_STAR_BUDGET_BANDS[0].aboveDistanceLy
  ) {
    return 2_500;
  }
  return viewport.cameraDistanceLy > LOCAL_STAR_BUDGET_BANDS[2].aboveDistanceLy
    ? 1_000
    : 250;
}

/**
 * Quantize requests, never catalogue positions. A small halo permits reuse
 * across grid boundaries; subsequent views reuse the prior complete rectangle
 * until they leave its coverage. Each request retains the detail-band limit.
 */
export function planGalaxyStarCells(
  viewport: GalaxyStarViewport,
  previous: readonly GalaxyStarCell[] = [],
): readonly GalaxyStarCell[] {
  const width = viewport.maxX - viewport.minX;
  const depth = viewport.maxZ - viewport.minZ;
  if (width <= 0 || depth <= 0) return [];
  if (
    ![
      viewport.minX,
      viewport.maxX,
      viewport.minY,
      viewport.maxY,
      viewport.minZ,
      viewport.maxZ,
    ].every(Number.isFinite) ||
    width > GALAXY_STAR_API_CUBE_BOUND_LY + BOUNDS_EPSILON_LY ||
    depth > GALAXY_STAR_API_CUBE_BOUND_LY + BOUNDS_EPSILON_LY ||
    viewport.maxY <= viewport.minY ||
    viewport.maxY - viewport.minY >
      GALAXY_STAR_API_CUBE_BOUND_LY - 2 * Y_QUANTUM_LY
  ) {
    throw new RangeError('Cell viewport must fit the bounded catalogue cube');
  }

  const paddedWidth = width * (1 + CELL_HALO_FRACTION * 2);
  const paddedDepth = depth * (1 + CELL_HALO_FRACTION * 2);
  let cellSizeLy = baseCellSize(viewport);
  // Account for the extra boundary cell at any grid alignment, so tiny pans
  // cannot change resolution simply by crossing a grid line.
  while (
    (Math.ceil(paddedWidth / cellSizeLy) + 1) *
      (Math.ceil(paddedDepth / cellSizeLy) + 1) >
    MAX_GALAXY_STAR_ACTIVE_CELLS
  ) {
    cellSizeLy = Math.min(cellSizeLy * 2, MAX_CELL_SIZE_LY);
  }

  if (
    previous.length &&
    previous.every(
      (cell) =>
        cell.cellSizeLy === cellSizeLy &&
        cell.request.limit === viewport.limit &&
        cell.request.minY <= viewport.minY &&
        cell.request.maxY >= viewport.maxY,
    ) &&
    Math.min(...previous.map((cell) => cell.request.minX)) <= viewport.minX &&
    Math.max(...previous.map((cell) => cell.request.maxX)) >= viewport.maxX &&
    Math.min(...previous.map((cell) => cell.request.minZ)) <= viewport.minZ &&
    Math.max(...previous.map((cell) => cell.request.maxZ)) >= viewport.maxZ
  ) {
    return previous;
  }

  const minX = Math.max(
    GALAXY_CATALOGUE_BOUNDS.minX,
    viewport.minX - width * CELL_HALO_FRACTION,
  );
  const maxX = Math.min(
    GALAXY_CATALOGUE_BOUNDS.maxX,
    viewport.maxX + width * CELL_HALO_FRACTION,
  );
  const minZ = Math.max(
    GALAXY_CATALOGUE_BOUNDS.minZ,
    viewport.minZ - depth * CELL_HALO_FRACTION,
  );
  const maxZ = Math.min(
    GALAXY_CATALOGUE_BOUNDS.maxZ,
    viewport.maxZ + depth * CELL_HALO_FRACTION,
  );
  const minY = Math.floor(viewport.minY / Y_QUANTUM_LY) * Y_QUANTUM_LY;
  const maxY = Math.ceil(viewport.maxY / Y_QUANTUM_LY) * Y_QUANTUM_LY;
  const cells: GalaxyStarCell[] = [];
  for (
    let xIndex = Math.floor(minX / cellSizeLy);
    xIndex < Math.ceil(maxX / cellSizeLy);
    xIndex++
  ) {
    for (
      let zIndex = Math.floor(minZ / cellSizeLy);
      zIndex < Math.ceil(maxZ / cellSizeLy);
      zIndex++
    ) {
      const request = {
        minX: Math.max(xIndex * cellSizeLy, GALAXY_CATALOGUE_BOUNDS.minX),
        maxX: Math.min((xIndex + 1) * cellSizeLy, GALAXY_CATALOGUE_BOUNDS.maxX),
        minY,
        maxY,
        minZ: Math.max(zIndex * cellSizeLy, GALAXY_CATALOGUE_BOUNDS.minZ),
        maxZ: Math.min((zIndex + 1) * cellSizeLy, GALAXY_CATALOGUE_BOUNDS.maxZ),
        limit: viewport.limit,
      };
      cells.push({
        key: `${cellSizeLy}:${xIndex}:${zIndex}:${minY}:${maxY}:${viewport.limit}`,
        cellSizeLy,
        request,
        centre: {
          x: (request.minX + request.maxX) / 2,
          y: (request.minY + request.maxY) / 2,
          z: (request.minZ + request.maxZ) / 2,
        },
      });
    }
  }
  return cells;
}

type CellEntry = { cell: GalaxyStarCell; lastUsed: number };

/**
 * Tracks query-cache identities without retaining a second copy of responses.
 * Active cells are pinned. Evict distant inactive cells first, using LRU for
 * equal distances, and return their descriptors so the caller removes queries.
 */
export class GalaxyStarCellCache {
  private readonly entries = new Map<string, CellEntry>();
  private clock = 0;

  constructor(readonly capacity = GALAXY_STAR_CELL_CACHE_LIMIT) {
    if (!Number.isSafeInteger(capacity) || capacity < 1) {
      throw new RangeError('Cell cache capacity must be a positive integer');
    }
  }

  get size(): number {
    return this.entries.size;
  }

  get(key: string): GalaxyStarCell | undefined {
    const entry = this.entries.get(key);
    if (entry) entry.lastUsed = ++this.clock;
    return entry?.cell;
  }

  retain(
    active: readonly GalaxyStarCell[],
    focusLy: Vec3Ly,
  ): readonly GalaxyStarCell[] {
    const activeKeys = new Set(active.map((cell) => cell.key));
    if (activeKeys.size > this.capacity) {
      throw new RangeError('Active cells exceed the cache capacity');
    }
    const lastUsed = ++this.clock;
    for (const cell of active) this.entries.set(cell.key, { cell, lastUsed });
    const distance = ({ cell }: CellEntry): number =>
      (cell.centre.x - focusLy.x) ** 2 +
      (cell.centre.y - focusLy.y) ** 2 +
      (cell.centre.z - focusLy.z) ** 2;
    const candidates = [...this.entries.values()]
      .filter(({ cell }) => !activeKeys.has(cell.key))
      .sort(
        (a, b) =>
          distance(b) - distance(a) ||
          a.lastUsed - b.lastUsed ||
          a.cell.key.localeCompare(b.cell.key),
      );
    const evicted: GalaxyStarCell[] = [];
    for (const { cell } of candidates) {
      if (this.entries.size <= this.capacity) break;
      this.entries.delete(cell.key);
      evicted.push(cell);
    }
    return evicted;
  }
}
