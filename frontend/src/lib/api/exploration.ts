import type {
  ExplorationFactsResponse,
  ExplorationImportReceipt,
  ExplorationImportRequest,
} from '@/types/api';
import { jsonFetch } from './core';

export interface ExplorationTrailPoint {
  sequence: number;
  fact_id: number;
  system_id64: number;
  system_name: string | null;
  visited_at: string;
  x: number | null;
  y: number | null;
  z: number | null;
  galaxy_region_id: number | null;
  from_system_id64: number | null;
  distance_ly: number | null;
}

export interface ExplorationTrailResponse {
  sync_key: string;
  points: ExplorationTrailPoint[];
  count: number;
  truncated: boolean;
  next_cursor: number | null;
}

export interface ExplorationViewportVisit {
  kind: 'marker' | 'density';
  system_id64: number | null;
  system_name: string | null;
  x: number;
  y: number;
  z: number;
  galaxy_region_id: number | null;
  visit_count: number;
  first_visited_at: string;
  last_visited_at: string;
  completion_state: 'complete' | 'partial';
  cell_size: number | null;
}

export interface ExplorationViewportVisitsResponse {
  sync_key: string;
  mode: 'markers' | 'density';
  visits: ExplorationViewportVisit[];
  count: number;
  truncated: boolean;
  cell_size: number | null;
}

export interface ExplorationSystemSummaryResponse {
  sync_key: string;
  system_id64: number;
  system_name: string | null;
  galaxy_region_id: number | null;
  visits: { visit_count: number; first_visited_at: string | null; last_visited_at: string | null };
  bodies: {
    expected: number | null; observed: number; scanned: number; mapped: number;
    fss_complete: boolean; dss_complete: boolean; map_progress: number;
  };
  organics: { organisms: number; logged: number; sampled: number; analysed: number; sold: number; sale_value: number };
  codex: { observed: number; pending: number; sold: number };
}

export interface ExplorationCodexByRegionResponse {
  sync_key: string;
  regions: Array<{
    region: string; region_id: number | null; global_entries: number;
    personal_entries: number; sold_entries: number; completion_percent: number | null;
    categories: Record<string, number>;
  }>;
  global_entries: number;
  personal_entries: number;
  completion_percent: number | null;
}

export function importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt> {
  return jsonFetch('/exploration/import', {
    method: 'POST',
    body:   JSON.stringify(request),
  });
}

export function getExplorationFacts(syncKey: string, opts?: {
  limit?: number; cursor?: string; event_type?: string[]; system_id64?: number;
  from_at?: string; to_at?: string;
}): Promise<ExplorationFactsResponse> {
  const params = new URLSearchParams();
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit));
  if (opts?.cursor) params.set('cursor', opts.cursor);
  opts?.event_type?.forEach((value) => params.append('event_type', value));
  if (opts?.system_id64 !== undefined) params.set('system_id64', String(opts.system_id64));
  if (opts?.from_at) params.set('from_at', opts.from_at);
  if (opts?.to_at) params.set('to_at', opts.to_at);
  const qs = params.toString();
  return jsonFetch(`/exploration/facts/${encodeURIComponent(syncKey)}${qs ? `?${qs}` : ''}`);
}

export function getExplorationTrail(syncKey: string, opts?: {
  limit?: number; cursor?: number; from_at?: string; to_at?: string;
}): Promise<ExplorationTrailResponse> {
  const params = new URLSearchParams({ sync_key: syncKey });
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit));
  if (opts?.cursor !== undefined) params.set('cursor', String(opts.cursor));
  if (opts?.from_at) params.set('from_at', opts.from_at);
  if (opts?.to_at) params.set('to_at', opts.to_at);
  return jsonFetch(`/exploration/trail?${params.toString()}`);
}

export function getExplorationViewportVisits(syncKey: string, box: {
  min_x: number; max_x: number; min_y: number; max_y: number;
  min_z: number; max_z: number;
}, zoom: number, limit?: number): Promise<ExplorationViewportVisitsResponse> {
  const params = new URLSearchParams({
    sync_key: syncKey, zoom: String(zoom),
    min_x: String(box.min_x), max_x: String(box.max_x),
    min_y: String(box.min_y), max_y: String(box.max_y),
    min_z: String(box.min_z), max_z: String(box.max_z),
  });
  if (limit !== undefined) params.set('limit', String(limit));
  return jsonFetch(`/exploration/viewport-visits?${params.toString()}`);
}

export function getExplorationSummary(syncKey: string, systemId64: number): Promise<ExplorationSystemSummaryResponse> {
  const params = new URLSearchParams({ sync_key: syncKey, system_id64: String(systemId64) });
  return jsonFetch(`/exploration/summary?${params.toString()}`);
}

export function getExplorationCodexByRegion(syncKey: string): Promise<ExplorationCodexByRegionResponse> {
  const params = new URLSearchParams({ sync_key: syncKey });
  return jsonFetch(`/exploration/codex-by-region?${params.toString()}`);
}
