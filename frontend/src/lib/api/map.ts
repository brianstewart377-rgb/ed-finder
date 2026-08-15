import { jsonFetch } from './core';

// ── Map layer types (backend returns `unknown` in generated OpenAPI) ────
export interface MapRegion {
  id: number;
  name: string;
  x: number | null;
  y: number | null;
  z: number | null;
  system_count: number | null;
}
export interface MapRegionsResponse {
  regions: MapRegion[];
  total_regions: number;
}

export interface MapClusterHull {
  anchor_id64: number;
  anchor_name: string;
  x: number | null;
  y: number | null;
  z: number | null;
  radius_ly: number;
  system_count: number;
  top_economy: string | null;
  top_score: number | null;
}
export interface MapClusterHullsResponse {
  clusters: MapClusterHull[];
  count: number;
  cached: boolean;
}

export interface MapHeatmapCell {
  cx: number;
  cy: number;
  cz: number;
  n: number;
  avg_score: number | null;
  max_score: number | null;
}
export interface MapHeatmapResponse {
  voxel_size: number;
  voxel_bucket: number;
  economy: string | null;
  cells: MapHeatmapCell[];
  count: number;
  max_cells: number;
  truncated: boolean;
}

export interface MapTimelinePoint {
  date: string | null;
  count: number;
}
export interface MapTimelineResponse {
  bucket: string;
  points: MapTimelinePoint[];
  total: number;
}

// ── Map layers ────────────────────────────────────────────────────────
export function mapRegions(): Promise<MapRegionsResponse> {
  return jsonFetch('/map/regions');
}

export function mapClusterHulls(opts?: { min_count?: number; max_hulls?: number }): Promise<MapClusterHullsResponse> {
  const params = new URLSearchParams();
  if (opts?.min_count !== undefined) params.set('min_count', String(opts.min_count));
  if (opts?.max_hulls !== undefined) params.set('max_hulls', String(opts.max_hulls));
  const qs = params.toString();
  return jsonFetch(`/map/clusters/hulls${qs ? `?${qs}` : ''}`);
}

export function mapHeatmap(opts?: { voxel_size?: number; min_systems?: number; max_cells?: number; economy?: string | null }): Promise<MapHeatmapResponse> {
  const params = new URLSearchParams();
  if (opts?.voxel_size !== undefined) params.set('voxel_size', String(opts.voxel_size));
  if (opts?.min_systems !== undefined) params.set('min_systems', String(opts.min_systems));
  if (opts?.max_cells !== undefined) params.set('max_cells', String(opts.max_cells));
  if (opts?.economy != null) params.set('economy', opts.economy);
  const qs = params.toString();
  return jsonFetch(`/map/heatmap${qs ? `?${qs}` : ''}`);
}

export function mapTimeline(opts?: { bucket?: 'day' | 'week' | 'month' | 'quarter' | 'year' }): Promise<MapTimelineResponse> {
  const params = new URLSearchParams();
  if (opts?.bucket) params.set('bucket', opts.bucket);
  const qs = params.toString();
  return jsonFetch(`/map/timeline${qs ? `?${qs}` : ''}`);
}

// ── Real-star viewport lane (zoom-in detail) ────────────────────────────
export interface MapViewportSystem {
  id64: number;
  name: string;
  x: number;
  y: number;
  z: number;
  /** main_star_class — the spectral letter (O/B/A/…) or null. */
  main_star_class: string | null;
  populated: boolean;
}
export interface MapViewportResponse {
  systems: MapViewportSystem[];
  truncated: boolean;
}
export interface MapViewportBox {
  min_x: number; max_x: number;
  min_y: number; max_y: number;
  min_z: number; max_z: number;
}

export function mapSystems(box: MapViewportBox, limit?: number): Promise<MapViewportResponse> {
  const params = new URLSearchParams({
    min_x: String(box.min_x), max_x: String(box.max_x),
    min_y: String(box.min_y), max_y: String(box.max_y),
    min_z: String(box.min_z), max_z: String(box.max_z),
  });
  if (limit !== undefined) params.set('limit', String(limit));
  return jsonFetch(`/map/systems?${params.toString()}`);
}
