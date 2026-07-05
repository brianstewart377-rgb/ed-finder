/**
 * Search state: filters → request → results.
 *
 * Single source of truth for the v2 search form. Powers the FinderView's
 * filter rail (incl. the 18 body-type dual-range sliders) and the result
 * list.
 */
import { useCallback, useState } from 'react';
import { api, type LocalSearchBody } from '@/lib/api';
import type { SearchResponse, SystemResult } from '@/types/api';

export type SortBy = 'development' | 'distance' | 'population';

/** Tri-state body filter for the legacy quick-pill section (kept for
 *  feature parity — the new dual-range sliders are the recommended path). */
export type FilterTri = 'off' | 'required' | 'excluded';

export const BODY_FILTER_KEYS = [
  'elw', 'ww', 'ammonia', 'terra', 'bio', 'geo',
] as const;
export type BodyFilterKey = typeof BODY_FILTER_KEYS[number];

export const BODY_FILTER_LABELS: Record<BodyFilterKey, string> = {
  elw:     'Earth-like',
  ww:      'Water world',
  ammonia: 'Ammonia',
  terra:   'Terraformable',
  bio:     'Bio signals',
  geo:     'Geo signals',
};

/** ── Per-body-type dual-range filter (matches `_redesign/FilterRail`) ── */
export interface BodyRange { min: number; max: number; }

/** Body-type sliders backed by real columns on the `ratings` table. All
 *  18 originally-defined slider keys are now wired through to a real
 *  column — `walkable_count`, `ring_count`, `other_star_count` were
 *  added in sql/008_body_filter_aggregates.sql. */
export const BODY_SLIDERS = [
  { key: 'landable',   label: 'Landable',           color: '#94a3b8', max: 60 },
  { key: 'walkable',   label: 'Walkable',           color: '#38bdf8', max: 60 },
  { key: 'blackHole',  label: 'Black Holes',        color: '#e2e8f0', max: 3  },
  { key: 'neutron',    label: 'Neutron Stars',      color: '#cbd5e1', max: 3  },
  { key: 'whiteDwarf', label: 'White Dwarves',      color: '#dbeafe', max: 3  },
  { key: 'otherStar',  label: 'Other Stars',        color: '#bef264', max: 30 },
  { key: 'elw',        label: 'Earth-like',         color: '#4ade80', max: 3  },
  { key: 'ww',         label: 'Water Worlds',       color: '#60a5fa', max: 20 },
  { key: 'ammonia',    label: 'Ammonia Worlds',     color: '#fb923c', max: 10 },
  { key: 'gasGiant',   label: 'Gas Giants',         color: '#fbbf24', max: 30 },
  { key: 'hmc',        label: 'High Metal',         color: '#a78bfa', max: 30 },
  { key: 'metalRich',  label: 'Metal Rich',         color: '#f87171', max: 10 },
  { key: 'rockyIce',   label: 'Rocky Ice',          color: '#7dd3fc', max: 25 },
  { key: 'rocky',      label: 'Rocky',              color: '#94a3b8', max: 50 },
  { key: 'icy',        label: 'Icy',                color: '#e0e7ff', max: 60 },
  { key: 'rings',      label: 'Rings',              color: '#bef264', max: 30 },
  { key: 'geoSignals', label: 'Geo Signals',        color: '#d97706', max: 30 },
  { key: 'bioSignals', label: 'Bio Signals',        color: '#22c55e', max: 25 },
] as const;

export type BodySliderKey = (typeof BODY_SLIDERS)[number]['key'];

const DEFAULT_BODY_RANGES: Record<BodySliderKey, BodyRange> = Object.fromEntries(
  BODY_SLIDERS.map((b) => [b.key, { min: 0, max: b.max }]),
) as Record<BodySliderKey, BodyRange>;

/** Map our slider keys to the backend `body_filters` field names. The
 *  backend's `local_search.py` accepts these directly. */
const BODY_BACKEND_KEY: Record<BodySliderKey, string> = {
  landable:   'landable',
  walkable:   'walkable',
  blackHole:  'black_hole',
  neutron:    'neutron',
  whiteDwarf: 'white_dwarf',
  otherStar:  'other_star',
  elw:        'elw',
  ww:         'ww',
  ammonia:    'ammonia',
  gasGiant:   'gas_giant',
  hmc:        'hmc',
  metalRich:  'metal_rich',
  rockyIce:   'rocky_ice',
  rocky:      'rocky',
  icy:        'icy',
  rings:      'rings',
  geoSignals: 'geo',
  bioSignals: 'bio',
};

/** Quick-preset definitions — each one applies a focused filter set to
 *  surface a specific kind of system (e.g. "find me a tourism hub"). The
 *  presets are intentionally opinionated: they nudge the user toward
 *  high-rated hits in seconds without forcing them to learn the 18
 *  body-type sliders. */
export const PRESETS = [
  {
    id:    'farm',
    icon:  '🌾',
    label: 'Farm Colony',
    hint:  'High-yield Earth-like + Water worlds, agriculture',
    filters: {
      economy:   'Agriculture',
      minDevelopmentScore: 60,
      bodyRanges: { elw: { min: 1, max: 10 }, ww: { min: 1, max: 20 } },
    },
  },
  {
    id:    'refinery',
    icon:  '🏭',
    label: 'Refinery',
    hint:  'High Metal Content + Metal Rich + Rings',
    filters: {
      economy:   'Refinery',
      minDevelopmentScore: 55,
      bodyRanges: { hmc: { min: 3, max: 30 }, metalRich: { min: 1, max: 10 }, rings: { min: 1, max: 30 } },
    },
  },
  {
    id:    'tourism',
    icon:  '🛰️',
    label: 'Tourism Hub',
    hint:  'Earth-like, Ammonia, Black Holes — anything rare',
    filters: {
      economy:   'Tourism',
      minDevelopmentScore: 50,
      bodyRanges: { elw: { min: 1, max: 10 }, ammonia: { min: 1, max: 10 } },
    },
  },
  {
    id:    'hightech',
    icon:  '🔬',
    label: 'High-Tech R&D',
    hint:  'Populated, high-rating, science-heavy',
    filters: {
      // Wire value matches the PG `economy_type` enum literal `HighTech`
      // (no space). The dropdown label still reads 'High Tech'.
      economy:   'HighTech',
      minDevelopmentScore: 70,
      populated: 'populated' as const,
    },
  },
  {
    id:    'military',
    icon:  '🛡️',
    label: 'Military',
    hint:  'Empire / Federation systems, high security',
    filters: {
      economy:   'Military',
      minDevelopmentScore: 50,
      populated: 'populated' as const,
    },
  },
  {
    id:    'exobio',
    icon:  '🧬',
    label: 'Exobiology',
    hint:  'Lots of bio + geo signals, landable bodies',
    filters: {
      minDevelopmentScore: 30,
      bodyRanges: {
        bioSignals: { min: 5, max: 25 },
        geoSignals: { min: 1, max: 30 },
        landable:   { min: 4, max: 60 },
      },
    },
  },
] as const;

export type PresetId = (typeof PRESETS)[number]['id'];

/** Apply a preset on top of `DEFAULT_FILTERS` (so picking another preset
 *  doesn't accumulate state from the previous one — each is a fresh
 *  search profile). The reference system is preserved. */
export function applyPreset(currentFilters: SearchFilters, id: PresetId): SearchFilters {
  const preset = PRESETS.find((p) => p.id === id);
  if (!preset) return currentFilters;
  const next: SearchFilters = {
    ...DEFAULT_FILTERS,
    refName:   currentFilters.refName,
    refCoords: currentFilters.refCoords,
    galaxyWide: currentFilters.galaxyWide,
    sortBy:    'development',
  };
  if ('economy'   in preset.filters) next.economy   = preset.filters.economy   as string;
  if ('minDevelopmentScore' in preset.filters) next.minDevelopmentScore = preset.filters.minDevelopmentScore as number;
  if ('populated' in preset.filters) next.populated = preset.filters.populated as SearchFilters['populated'];
  if ('bodyRanges' in preset.filters && preset.filters.bodyRanges) {
    next.bodyRanges = {
      ...DEFAULT_BODY_RANGES,
      ...(preset.filters.bodyRanges as Partial<Record<BodySliderKey, BodyRange>>),
    } as Record<BodySliderKey, BodyRange>;
  }
  return next;
}

export interface SearchFilters {
  refName:        string;
  refCoords:      { x: number; y: number; z: number };
  minDistance:    number;
  maxDistance:    number;
  size:           number;
  populated:      'any' | 'populated' | 'uninhabited';
  economy:        string;
  minDevelopmentScore: number;
  galaxyWide:     boolean;
  sortBy:         SortBy;
  bodyFilters:    Record<BodyFilterKey, FilterTri>;
  bodyRanges:     Record<BodySliderKey, BodyRange>;
}

const ZERO_BODY_FILTERS: Record<BodyFilterKey, FilterTri> = {
  elw: 'off', ww: 'off', ammonia: 'off',
  terra: 'off', bio: 'off', geo: 'off',
};

export const DEFAULT_FILTERS: SearchFilters = {
  refName:     'Sol',
  refCoords:   { x: 0, y: 0, z: 0 },
  minDistance: 0,
  maxDistance: 200,
  size:        50,
  populated:   'any',
  economy:     'any',
  minDevelopmentScore: 0,
  galaxyWide:  false,
  sortBy:      'development',
  bodyFilters: { ...ZERO_BODY_FILTERS },
  bodyRanges:  { ...DEFAULT_BODY_RANGES },
};

export type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: SearchResponse; queriedAt: number }
  | { kind: 'err'; message: string };

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
    min_development_score:  f.minDevelopmentScore,
  };
  if (f.populated === 'uninhabited') {
    body.filters!.population = { comparison: 'equal', value: 0 };
  } else if (f.populated === 'populated') {
    body.filters!.population = { comparison: '>', value: 0 };
  }
  if (f.economy && f.economy !== 'any') {
    body.filters!.economy = f.economy;
  }
  // Quick-pill body filters (legacy)
  const bf = f.bodyFilters;
  if (bf.bio   === 'required') body.require_bio   = true;
  if (bf.geo   === 'required') body.require_geo   = true;
  if (bf.terra === 'required') body.require_terra = true;

  // Per-body dual-range sliders → body_filters{ <key>: { min, max } }
  const bodyFilters: Record<string, { min?: number; max?: number }> = {};
  for (const b of BODY_SLIDERS) {
    const r = f.bodyRanges[b.key];
    if (!r) continue;
    // Only send filters that diverge from the full range — saves bytes
    // and avoids needless WHEREs.
    const apiKey = BODY_BACKEND_KEY[b.key];
    if (r.min > 0) bodyFilters[apiKey] = { ...(bodyFilters[apiKey] ?? {}), min: r.min };
    if (r.max < b.max) bodyFilters[apiKey] = { ...(bodyFilters[apiKey] ?? {}), max: r.max };
  }
  // Quick pills can stack a min:1 if user clicked them
  if (bf.elw     === 'required') bodyFilters.elw     = { ...(bodyFilters.elw     ?? {}), min: Math.max(1, bodyFilters.elw?.min     ?? 0) };
  if (bf.ww      === 'required') bodyFilters.ww      = { ...(bodyFilters.ww      ?? {}), min: Math.max(1, bodyFilters.ww?.min      ?? 0) };
  if (bf.ammonia === 'required') bodyFilters.ammonia = { ...(bodyFilters.ammonia ?? {}), min: Math.max(1, bodyFilters.ammonia?.min ?? 0) };

  if (Object.keys(bodyFilters).length) body.body_filters = bodyFilters;
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

  const results: SystemResult[] = state.kind === 'ok' ? state.data.results : [];

  return { filters, setFilters, reset, run, state, results };
}
