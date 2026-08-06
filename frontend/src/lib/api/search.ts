import type {
  AutocompleteResponse,
  SearchResponse,
} from '@/types/api';
import { jsonFetch } from './core';

export type LocalSearchBody = {
  reference_coords?: { x: number; y: number; z: number };
  filters?: {
    distance?:   { min?: number; max?: number };
    population?: Record<string, unknown>;
    economy?:    string;
  };
  size?:       number;
  from?:       number;
  sort_by?:    'distance' | 'development' | 'population' | string;
  galaxy_wide?: boolean;
  min_development_score?: number;
  /** Per-body-type min/max counts (server-side filter). */
  body_filters?: Record<string, { min?: number; max?: number }>;
  /** Top-level boolean toggles understood by local_search.py. */
  require_bio?:   boolean;
  require_geo?:   boolean;
  require_terra?: boolean;
};

export interface ClusterSearchRequestBody {
  slots: Array<{
    economies: string[];
    archetype_key?: string;
    label?: string;
    min_score?: number;
  }>;
  limit: number;
  reference_coords: { x: number; y: number; z: number };
  galaxy_region_id?: number;
}

export interface ClusterSearchApiResponse<TCluster> {
  clusters?: TCluster[];
  count?: number | null;
  query_ms?: number | null;
  error?: string | null;
}

export interface EddnEvent {
  system_name: string;
  id64:        number;
  type:        string;
  timestamp:   string | null;
}

export interface RecentEventsResponse {
  events: EddnEvent[];
  jobs:   Record<string, unknown>;
}

export interface EliteNewsItem {
  title: string;
  url: string;
  source: 'news' | 'galnet' | string;
}

export interface EliteNewsResponse {
  items: EliteNewsItem[];
  source_url: string;
  fetched_at: string;
  stale: boolean;
}

/** Shape of one row from the scoped Watchlist API. */
export interface WatchlistEntry {
  system_id64:        number;
  name:               string;
  x:                  number | null;
  y:                  number | null;
  z:                  number | null;
  population:         number | null;
  is_colonised:       boolean;
  added_at:           string;
  /** Latest development snapshot joined server-side. */
  score?:             number | null;
  economy_suggestion?: string | null;
  archetype_score?:   number | null;
  primary_archetype?: string | null;
  secondary_archetype?: string | null;
  buildability_score?: number | null;
  purity_score?:      number | null;
  alert_min_development_score?: number | null;
  alert_min_score?:   number | null;
  alert_economy?:     string | null;
}

export function health(): Promise<{ status: string; database: string; version: string }> {
  return jsonFetch('/api/health');
}

export function autocomplete(q: string, limit = 10): Promise<AutocompleteResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return jsonFetch(`/local/autocomplete?${params.toString()}`);
}

export function localSearch(body: LocalSearchBody): Promise<SearchResponse> {
  return jsonFetch<SearchResponse>('/local/search', {
    method: 'POST',
    body:   JSON.stringify(body),
  });
}

export function clusterSearch<TCluster>(body: ClusterSearchRequestBody): Promise<ClusterSearchApiResponse<TCluster>> {
  return jsonFetch('/search/cluster', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ── Watchlist ───────────────────────────────────────────────────────
export function watchlist(syncKey: string): Promise<{ sync_key?: string; watchlist: WatchlistEntry[] }> {
  return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}`);
}

export function watchAdd(syncKey: string, id64: number): Promise<{ ok: boolean; sync_key?: string }> {
  return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, { method: 'POST' });
}

export function watchRemove(syncKey: string, id64: number): Promise<{ ok: boolean; sync_key?: string }> {
  return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, { method: 'DELETE' });
}

export function recentEvents(limit = 20): Promise<RecentEventsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return jsonFetch(`/events/recent?${params.toString()}`, { cache: 'no-store' });
}

export function eliteNewsLatest(limit = 8): Promise<EliteNewsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return jsonFetch(`/news/latest?${params.toString()}`, { cache: 'no-store' });
}
