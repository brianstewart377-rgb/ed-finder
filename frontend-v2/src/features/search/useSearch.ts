/**
 * Search state: filters → request → results.
 *
 * Single source of truth for the v2 search form. Everything the form needs
 * to display + everything the result list needs to render is in here.
 *
 * Why a hand-rolled hook instead of Zustand / Redux / Jotai?
 *   • One screen, one form, no cross-feature sharing yet.
 *   • Hooks compose cleanly with React Suspense / RSC if we go there.
 *   • One less dependency to upgrade. Add a store when we have ≥2 features
 *     that genuinely need to share writeable state.
 */
import { useCallback, useState } from 'react';
import { api, type LocalSearchBody } from '@/lib/api';
import type { SearchResponse, SystemResult } from '@/types/api';

export type SortBy = 'rating' | 'distance';

export interface SearchFilters {
  refName:        string;                       // reference system display name
  refCoords:      { x: number; y: number; z: number };
  minDistance:    number;
  maxDistance:    number;
  size:           number;                       // results per page
  populated:      'any' | 'populated' | 'uninhabited';
  economy:        string;                       // 'any' | 'Agriculture' | …
  minRating:      number;                       // 0-100
  galaxyWide:     boolean;
  sortBy:         SortBy;
}

export const DEFAULT_FILTERS: SearchFilters = {
  refName:     'Sol',
  refCoords:   { x: 0, y: 0, z: 0 },
  minDistance: 0,
  maxDistance: 50,
  size:        50,
  populated:   'any',
  economy:     'any',
  minRating:   0,
  galaxyWide:  false,
  sortBy:      'rating',
};

export type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: SearchResponse; queriedAt: number }
  | { kind: 'err'; message: string };

/** Convert UI filters → API request body. */
function toRequestBody(f: SearchFilters): LocalSearchBody {
  const body: LocalSearchBody = {
    reference_coords: f.refCoords,
    filters: {
      distance: { min: f.minDistance, max: f.maxDistance },
    },
    size:        f.size,
    from:        0,
    sort_by:     f.sortBy,
    galaxy_wide: f.galaxyWide,
    min_rating:  f.minRating,
  };
  if (f.populated === 'uninhabited') {
    body.filters!.population = { comparison: 'equal', value: 0 };
  } else if (f.populated === 'populated') {
    body.filters!.population = { comparison: '>', value: 0 };
  }
  if (f.economy && f.economy !== 'any') {
    body.filters!.economy = f.economy;
  }
  return body;
}

export function useSearch() {
  const [filters, setFiltersState] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [state,   setState]        = useState<SearchState>({ kind: 'idle' });

  const setFilters = useCallback((patch: Partial<SearchFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...patch }));
  }, []);

  const reset = useCallback(() => {
    setFiltersState(DEFAULT_FILTERS);
    setState({ kind: 'idle' });
  }, []);

  const run = useCallback(
    async (override?: Partial<SearchFilters>) => {
      const effective = { ...filters, ...override };
      if (override) setFiltersState(effective);

      setState({ kind: 'loading' });
      try {
        const data = await api.localSearch(toRequestBody(effective));
        setState({ kind: 'ok', data, queriedAt: Date.now() });
      } catch (err) {
        setState({
          kind: 'err',
          message: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [filters],
  );

  // Convenience getter — the result list is the only thing components
  // care about; everything else is just for UX (loading, error, count).
  const results: SystemResult[] = state.kind === 'ok' ? state.data.results : [];

  return { filters, setFilters, reset, run, state, results };
}
