import { useCallback, useEffect, useState } from 'react';
import type { SystemResult } from '@/types/api';

/**
 * Compare state. Client-only, persisted to localStorage as full snapshots.
 *
 * The legacy vanilla app stored only IDs under 'ed_compare_ids' and tried to
 * re-match against the current search results on reload — that silently
 * dropped entries whenever the user's search changed between sessions.
 * v2 stores the full SystemResult so the comparison survives any reload.
 *
 * Separate key ('ed_compare_v2') so we don't clash with the legacy shape.
 * When v2 flips to root we can optionally migrate the old IDs once.
 */
export const COMPARE_MAX = 6;
const STORAGE_KEY = 'ed_compare_v2';

function readStorage(): SystemResult[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SystemResult[]) : [];
  } catch {
    return [];
  }
}

function writeStorage(entries: SystemResult[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch { /* quota / private-mode — degrade silently */ }
}

export interface UseCompare {
  entries: SystemResult[];
  has:     (id64: number) => boolean;
  /** Toggle: adds if absent (respecting COMPARE_MAX), removes if present.
   *  Returns true if the system is now in the comparison, false otherwise. */
  toggle:  (sys: SystemResult) => boolean;
  remove:  (id64: number) => void;
  clear:   () => void;
  /** Serialises the current comparison as CSV and triggers a download. */
  exportCsv: () => void;
  /** UI affordance: the toggle returned false due to hitting the cap. */
  lastError: string | null;
  clearError: () => void;
}

export function useCompare(): UseCompare {
  const [entries, setEntries]   = useState<SystemResult[]>(readStorage);
  const [lastError, setError]   = useState<string | null>(null);

  // Cross-tab sync — same pattern as usePinned.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setEntries(readStorage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const persist = useCallback((next: SystemResult[]) => {
    writeStorage(next);
    setEntries(next);
  }, []);

  const has = useCallback(
    (id64: number) => entries.some((e) => e.id64 === id64),
    [entries],
  );

  const toggle = useCallback((sys: SystemResult): boolean => {
    if (entries.some((e) => e.id64 === sys.id64)) {
      persist(entries.filter((e) => e.id64 !== sys.id64));
      return false;
    }
    if (entries.length >= COMPARE_MAX) {
      setError(`Comparison is full (max ${COMPARE_MAX}). Remove one first.`);
      return false;
    }
    persist([...entries, sys]);
    setError(null);
    return true;
  }, [entries, persist]);

  const remove = useCallback((id64: number) => {
    persist(entries.filter((e) => e.id64 !== id64));
  }, [entries, persist]);

  const clear = useCallback(() => {
    persist([]);
    setError(null);
  }, [persist]);

  const exportCsv = useCallback(() => {
    const snapshot = readStorage();
    if (snapshot.length === 0) return;

    // Same metric set as the on-screen matrix, kept in sync with CompareTab.
    // Keep this light — the goal is a spreadsheet-friendly export, not a
    // full data dump. Wrap every value in quotes and escape embedded quotes.
    const q = (v: unknown): string =>
      `"${String(v ?? '').replace(/"/g, '""')}"`;

    const names = snapshot.map((s) => s.name);
    const header = ['Metric', ...names].map(q).join(',');

    const rows: Array<[string, Array<string | number | null | undefined>]> = [
      ['Score (overall)',      snapshot.map((s) => s._rating?.score ?? '')],
      ['Confidence',           snapshot.map((s) => s._rating?.confidence ?? '')],
      ['Rationale',            snapshot.map((s) => s._rating?.rationale ?? '')],
      ['Primary economy',      snapshot.map((s) => s.primaryEconomy ?? '')],
      ['Suggested economy',    snapshot.map((s) => s._rating?.economySuggestion ?? '')],
      ['Distance from ref LY', snapshot.map((s) => s.distance ?? '')],
      ['Population',           snapshot.map((s) => s.population)],
      ['Colonised',            snapshot.map((s) => (s.is_colonised ? 'Yes' : 'No'))],
      ['Main star',            snapshot.map((s) => s.main_star_subtype ?? s.main_star_type ?? '')],
      ['Security',             snapshot.map((s) => s.security ?? '')],
      ['Allegiance',           snapshot.map((s) => s.allegiance ?? '')],
      ['Terraforming potential', snapshot.map((s) => s._rating?.terraformingPotential ?? '')],
      ['Body diversity',       snapshot.map((s) => s._rating?.bodyDiversity ?? '')],
      ['ELW',                  snapshot.map((s) => s.elw_count ?? 0)],
      ['WW',                   snapshot.map((s) => s.ww_count ?? 0)],
      ['Ammonia',              snapshot.map((s) => s.ammonia_count ?? 0)],
      ['Terraformable',        snapshot.map((s) => s.terraformable_count ?? 0)],
      ['Landable',             snapshot.map((s) => s.landable_count ?? 0)],
      ['Bio signals',          snapshot.map((s) => s.bio_signal_total ?? 0)],
      ['Geo signals',          snapshot.map((s) => s.geo_signal_total ?? 0)],
      ['Score: Agriculture',   snapshot.map((s) => s._rating?.scoreAgriculture ?? '')],
      ['Score: Refinery',      snapshot.map((s) => s._rating?.scoreRefinery ?? '')],
      ['Score: Industrial',    snapshot.map((s) => s._rating?.scoreIndustrial ?? '')],
      ['Score: High Tech',     snapshot.map((s) => s._rating?.scoreHightech ?? '')],
      ['Score: Military',      snapshot.map((s) => s._rating?.scoreMilitary ?? '')],
      ['Score: Tourism',       snapshot.map((s) => s._rating?.scoreTourism ?? '')],
      ['Score: Extraction',    snapshot.map((s) => s._rating?.scoreExtraction ?? '')],
    ];

    const csv = [header, ...rows.map(([label, vals]) => [label, ...vals].map(q).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ed-compare-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { entries, has, toggle, remove, clear, exportCsv, lastError, clearError };
}
