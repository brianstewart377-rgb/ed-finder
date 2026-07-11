import { useCallback, useEffect, useState } from 'react';
import type { SystemResult } from '@/types/api';
import { formatArchetypeLabel, getDevelopmentScore } from '@/lib/archetypes';
import { readJsonStorage, writeJsonStorage } from '@/lib/browserStorage';
import { formatPopulationForSystem, systemStatusLabel } from '@/lib/format';

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
  const parsed = readJsonStorage<unknown>(STORAGE_KEY, []);
  return Array.isArray(parsed) ? (parsed as SystemResult[]) : [];
}

function writeStorage(entries: SystemResult[]): void {
  writeJsonStorage(STORAGE_KEY, entries);
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
      ['Development score',    snapshot.map((s) => getDevelopmentScore(s) ?? '')],
      ['Primary archetype',    snapshot.map((s) => s.primary_archetype ? formatArchetypeLabel(s.primary_archetype) : '')],
      ['Secondary archetype',  snapshot.map((s) => s.secondary_archetype ? formatArchetypeLabel(s.secondary_archetype) : '')],
      ['Archetype confidence', snapshot.map((s) => s.archetype_confidence != null ? Math.round(s.archetype_confidence * 100) : '')],
      ['Buildability',         snapshot.map((s) => s.buildability_score ?? '')],
      ['Purity',               snapshot.map((s) => s.purity_score ?? '')],
      ['Estimated slots',      snapshot.map((s) => s.est_total_slots ?? '')],
      ['Primary economy',      snapshot.map((s) => s.primaryEconomy ?? '')],
      ['Distance from ref LY', snapshot.map((s) => s.distance ?? '')],
      ['Population',           snapshot.map((s) => formatPopulationForSystem(s))],
      ['Status',               snapshot.map((s) => systemStatusLabel(s))],
      ['Main star',            snapshot.map((s) => s.main_star_subtype ?? s.main_star_type ?? '')],
      ['Security',             snapshot.map((s) => s.security ?? '')],
      ['Allegiance',           snapshot.map((s) => s.allegiance ?? '')],
      ['ELW',                  snapshot.map((s) => s.elw_count ?? 0)],
      ['WW',                   snapshot.map((s) => s.ww_count ?? 0)],
      ['Ammonia',              snapshot.map((s) => s.ammonia_count ?? 0)],
      ['Terraformable',        snapshot.map((s) => s.terraformable_count ?? 0)],
      ['Landable',             snapshot.map((s) => s.landable_count ?? 0)],
      ['Bio signals',          snapshot.map((s) => s.bio_signal_total ?? 0)],
      ['Geo signals',          snapshot.map((s) => s.geo_signal_total ?? 0)],
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
