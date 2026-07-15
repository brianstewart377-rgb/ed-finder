import { useState, useCallback } from 'react';

// ── Request types ────────────────────────────────────────────────────────
export interface SlotRequirement {
  economies:      string[];
  archetype_key?: string;
  min_score?:     number;
  label?:         string;
}

export interface ClusterSearchFilters {
  slots:     SlotRequirement[];
  refName:   string;
  refCoords: { x: number; y: number; z: number };
  limit:     number;
}

// ── Response types ───────────────────────────────────────────────────────
export interface SlotMatch {
  system_id64:             number;
  system_name:             string;
  scores:                  Record<string, number>;
  distance_from_anchor_ly: number;
}

export interface SlotResult {
  slot_index: number;
  label:      string;
  economies:  string[];
  matches:    SlotMatch[];
}

export interface ClusterResult {
  anchor_id64:        number;
  anchor_name:        string;
  anchor_coords:      { x: number; y: number; z: number } | null;
  galaxy_region:      string | null;
  coverage_score:     number;
  economy_diversity:  number;
  total_viable:       number;
  agriculture_count:  number;
  agriculture_best:   number;
  refinery_count:     number;
  refinery_best:      number;
  industrial_count:   number;
  industrial_best:    number;
  hightech_count:     number;
  hightech_best:      number;
  military_count:     number;
  military_best:      number;
  tourism_count:      number;
  tourism_best:       number;
  distance_ly:        number | null;
  cluster_radius_ly:  number;
  // New slot-based detail
  slots?:             SlotResult[];
}

// ── Predefined archetype profiles ────────────────────────────────────────
export const ARCHETYPE_PROFILES: { label: string; archetype_key: string; economies: string[] }[] = [
  { label: 'Refinery + Industrial',  archetype_key: 'refinery_industrial',       economies: ['Refinery', 'Industrial'] },
  { label: 'Extraction + Refinery',  archetype_key: 'extraction_refinery',       economies: ['Refinery'] },
  { label: 'Agriculture',             archetype_key: 'agriculture_terraforming', economies: ['Agriculture'] },
  { label: 'HighTech + Tourism',     archetype_key: 'hitech_tourism',            economies: ['HighTech', 'Tourism'] },
  { label: 'Military + Industrial',  archetype_key: 'military_industrial',       economies: ['Military', 'Industrial'] },
];

export const ALL_ECONOMIES = ['Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism'] as const;

type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'err'; message: string }
  | { kind: 'ok'; data: { count: number; query_ms: number }; queriedAt: number };

const SOL_COORDS = { x: 0, y: 0, z: 0 };

const DEFAULT_FILTERS: ClusterSearchFilters = {
  slots: [{ archetype_key: 'refinery_industrial', label: 'Refinery + Industrial', economies: [] }],
  refName:   'Sol',
  refCoords: SOL_COORDS,
  limit:     50,
};

export function useClusterSearch() {
  const [filters, setFiltersRaw] = useState<ClusterSearchFilters>(DEFAULT_FILTERS);
  const [state, setState] = useState<SearchState>({ kind: 'idle' });
  const [results, setResults] = useState<ClusterResult[]>([]);

  const setFilters = useCallback((patch: Partial<ClusterSearchFilters>) => {
    setFiltersRaw(prev => ({ ...prev, ...patch }));
  }, []);

  const addSlot = useCallback(() => {
    setFiltersRaw(prev => {
      if (prev.slots.length >= 5) return prev;
      const usedArchetypes = new Set(prev.slots.map(s => s.archetype_key).filter(Boolean));
      const nextProfile = ARCHETYPE_PROFILES.find(p => !usedArchetypes.has(p.archetype_key));
      const newSlot: SlotRequirement = nextProfile
        ? { archetype_key: nextProfile.archetype_key, label: nextProfile.label, economies: [] }
        : { economies: ['Agriculture'], label: 'Agriculture' };
      return { ...prev, slots: [...prev.slots, newSlot] };
    });
  }, []);

  const removeSlot = useCallback((index: number) => {
    setFiltersRaw(prev => ({
      ...prev,
      slots: prev.slots.filter((_, i) => i !== index),
    }));
  }, []);

  const updateSlot = useCallback((index: number, patch: Partial<SlotRequirement>) => {
    setFiltersRaw(prev => ({
      ...prev,
      slots: prev.slots.map((s, i) => i === index ? { ...s, ...patch } : s),
    }));
  }, []);

  const run = useCallback(async () => {
    if (filters.slots.length === 0) return;
    setState({ kind: 'loading' });
    try {
      const body = {
        slots: filters.slots.map(s => ({
          economies: s.economies,
          archetype_key: s.archetype_key || undefined,
          label: s.label || undefined,
          min_score: s.min_score || undefined,
        })),
        limit: filters.limit,
        reference_coords: filters.refCoords,
      };
      const res = await fetch('/api/search/cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setResults(data.clusters ?? []);
      setState({
        kind: 'ok',
        data: { count: data.count ?? 0, query_ms: data.query_ms ?? 0 },
        queriedAt: Date.now(),
      });
    } catch (e: any) {
      setState({ kind: 'err', message: e.message ?? String(e) });
      setResults([]);
    }
  }, [filters]);

  const reset = useCallback(() => {
    setFiltersRaw(DEFAULT_FILTERS);
    setState({ kind: 'idle' });
    setResults([]);
  }, []);

  return {
    filters, setFilters, addSlot, removeSlot,
    updateSlot, run, reset, state, results,
  };
}
