import { useState, useCallback } from 'react';

export interface ClusterRequirement {
  economy: string;
  min_count: number;
}

export interface ClusterSearchFilters {
  requirements: ClusterRequirement[];
  refName:   string;
  refCoords: { x: number; y: number; z: number };
  limit:     number;
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
}

type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'err'; message: string }
  | { kind: 'ok'; data: { count: number; query_ms: number }; queriedAt: number };

const SOL_COORDS = { x: 0, y: 0, z: 0 };

export function useClusterSearch() {
  const [filters, setFiltersRaw] = useState<ClusterSearchFilters>({
    requirements: [{ economy: 'Agriculture', min_count: 1 }],
    refName:   'Sol',
    refCoords: SOL_COORDS,
    limit:     50,
  });
  const [state, setState] = useState<SearchState>({ kind: 'idle' });
  const [results, setResults] = useState<ClusterResult[]>([]);

  const setFilters = useCallback((patch: Partial<ClusterSearchFilters>) => {
    setFiltersRaw(prev => ({ ...prev, ...patch }));
  }, []);

  const addRequirement = useCallback(() => {
    setFiltersRaw(prev => {
      if (prev.requirements.length >= 6) return prev;
      const used = new Set(prev.requirements.map(r => r.economy));
      const ECONOMIES = ['Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism'];
      const next = ECONOMIES.find(e => !used.has(e)) ?? 'Agriculture';
      return { ...prev, requirements: [...prev.requirements, { economy: next, min_count: 1 }] };
    });
  }, []);

  const removeRequirement = useCallback((index: number) => {
    setFiltersRaw(prev => ({
      ...prev,
      requirements: prev.requirements.filter((_, i) => i !== index),
    }));
  }, []);

  const updateRequirement = useCallback((index: number, patch: Partial<ClusterRequirement>) => {
    setFiltersRaw(prev => ({
      ...prev,
      requirements: prev.requirements.map((r, i) => i === index ? { ...r, ...patch } : r),
    }));
  }, []);

  const run = useCallback(async () => {
    if (filters.requirements.length === 0) return;
    setState({ kind: 'loading' });
    try {
      const body = {
        requirements: filters.requirements,
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
    setFiltersRaw({
      requirements: [{ economy: 'Agriculture', min_count: 1 }],
      refName: 'Sol',
      refCoords: SOL_COORDS,
      limit: 50,
    });
    setState({ kind: 'idle' });
    setResults([]);
  }, []);

  return {
    filters, setFilters, addRequirement, removeRequirement,
    updateRequirement, run, reset, state, results,
  };
}
