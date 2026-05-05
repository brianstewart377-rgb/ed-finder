/**
 * Tiny fetch wrapper for the ed-finder API.
 *
 * Resolves the base URL in this order:
 *   1. import.meta.env.VITE_API_BASE  (set per environment in .env / .env.production)
 *   2. /api  — same-origin fallback when the bundle is served from the same
 *      host as the API (the production deploy via nginx).
 *
 * The wrapper is intentionally minimal — no axios, no react-query yet. We add
 * those only when we hit a real need (cancellation, retries, dedup, suspense).
 * Premature abstraction has bitten this codebase before; let's not.
 */
import type {
  AutocompleteResponse,
  SearchResponse,
  SystemResult,
} from '@/types/api';

type LocalSearchBody = {
  reference_coords?: { x: number; y: number; z: number };
  filters?: {
    distance?:   { min?: number; max?: number };
    population?: Record<string, unknown>;
    economy?:    string;
  };
  size?:       number;
  from?:       number;
  sort_by?:    'distance' | 'rating' | 'population' | string;
  galaxy_wide?: boolean;
  min_rating?: number;
  /** Per-body-type min/max counts (server-side filter). */
  body_filters?: Record<string, { min?: number; max?: number }>;
  /** Top-level boolean toggles understood by local_search.py. */
  require_bio?:   boolean;
  require_geo?:   boolean;
  require_terra?: boolean;
};

const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, '') ??
  '/api'
);

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept:         'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    // Surface the FastAPI Problem-Details body so the caller can show a
    // useful error. The vanilla app drops the body here, which makes
    // debugging deploys painful.
    let body = '';
    try {
      body = await res.text();
    } catch { /* ignore */ }
    throw new Error(`API ${res.status} on ${path}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ── Endpoints we actually use in the POC ───────────────────────────────────
export const api = {
  health(): Promise<{ status: string; database: string; version: string }> {
    return jsonFetch('/health');
  },

  autocomplete(q: string, limit = 10): Promise<AutocompleteResponse> {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return jsonFetch(`/local/autocomplete?${params.toString()}`);
  },

  localSearch(body: LocalSearchBody): Promise<SearchResponse> {
    return jsonFetch<SearchResponse>('/local/search', {
      method: 'POST',
      body:   JSON.stringify(body),
    });
  },

  /** Re-rank a list of system ids with custom dimensional weights. */
  rerank(
    id64s: number[],
    weights?: Record<string, number>,
    economy?: string,
  ): Promise<{
    results: Array<{
      id64: number;
      reranked_score: number;
      original_score: number;
      rationale: string;
    }>;
    weights_applied: Record<string, number>;
  }> {
    return jsonFetch('/ratings/rerank', {
      method: 'POST',
      body:   JSON.stringify({ id64s, weights, economy }),
    });
  },

  // ── Watchlist ─────────────────────────────────────────────────────────
  watchlist(): Promise<{ watchlist: WatchlistEntry[] }> {
    return jsonFetch('/watchlist');
  },
  watchAdd(id64: number): Promise<{ ok: boolean }> {
    return jsonFetch(`/watchlist/${id64}`, { method: 'POST' });
  },
  watchRemove(id64: number): Promise<{ ok: boolean }> {
    return jsonFetch(`/watchlist/${id64}`, { method: 'DELETE' });
  },
};

/** Shape of one row from /api/watchlist. */
export interface WatchlistEntry {
  system_id64:        number;
  name:               string;
  x:                  number;
  y:                  number;
  z:                  number;
  population:         number;
  is_colonised:       boolean;
  added_at:           string;
  /** Latest rating (joined server-side). */
  score?:             number | null;
  economy_suggestion?: string | null;
  alert_min_score?:   number | null;
  alert_economy?:     string | null;
}

export type { LocalSearchBody, SystemResult };
