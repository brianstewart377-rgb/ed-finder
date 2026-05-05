import { useCallback, useEffect, useState } from 'react';

/**
 * Colony Tracker = a localStorage-backed list of systems the CMDR has
 * claimed for colonisation, each tagged with a phase.
 *
 * Storage: `ed_colony_v2`. Schema is intentionally close to the legacy
 * vanilla key (`ed_colony_tracker_v3`) but with an extra version field so
 * we can migrate forward without a hot fix release. We don't need backend
 * persistence for the v2 cutover — multi-device sync is a P2 nice-to-have
 * the legacy app didn't have either.
 */
export const PHASES = ['planning', 'building', 'active', 'complete'] as const;
export type Phase = (typeof PHASES)[number];

export const PHASE_META: Record<Phase, { icon: string; label: string; colour: string }> = {
  planning: { icon: '📋', label: 'Planning', colour: '#60a5fa' },
  building: { icon: '🔨', label: 'Building', colour: '#facc15' },
  active:   { icon: '✅', label: 'Active',   colour: '#10b981' },
  complete: { icon: '🏆', label: 'Complete', colour: '#a78bfa' },
};

export interface ColonyEntry {
  id:                string;     // generated, distinct from id64 (we may not know id64)
  name:              string;
  phase:             Phase;
  target_population: number | null;
  notes:             string;
  /** Optional — present if the user added from a known system (Finder, modal). */
  id64:              number | null;
  x:                 number | null;
  y:                 number | null;
  z:                 number | null;
  current_population: number | null;
  /** ISO timestamps. */
  claimed_at:        string;
  updated_at:        string;
}

const STORAGE_KEY = 'ed_colony_v2';

function readStorage(): ColonyEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ColonyEntry[]) : [];
  } catch { return []; }
}

function writeStorage(entries: ColonyEntry[]): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(entries)); }
  catch { /* quota / private mode — degrade silently */ }
}

function uid(): string {
  return `col-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export interface UseColony {
  entries: ColonyEntry[];
  /** Counts by phase, plus `total`. Computed from entries on every render
   *  but cheap (<1ms for any realistic list size). */
  counts:  Record<Phase | 'total', number>;
  add:     (input: Omit<ColonyEntry, 'id' | 'claimed_at' | 'updated_at'>) => ColonyEntry;
  update:  (id: string, patch: Partial<Omit<ColonyEntry, 'id' | 'claimed_at'>>) => void;
  remove:  (id: string) => void;
  clear:   () => void;
  exportCsv: () => void;
}

export function useColony(): UseColony {
  const [entries, setEntries] = useState<ColonyEntry[]>(readStorage);

  // Cross-tab sync (same pattern as usePinned / useCompare).
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setEntries(readStorage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const persist = useCallback((next: ColonyEntry[]) => {
    writeStorage(next);
    setEntries(next);
  }, []);

  const counts: UseColony['counts'] = {
    total:    entries.length,
    planning: entries.filter((e) => e.phase === 'planning').length,
    building: entries.filter((e) => e.phase === 'building').length,
    active:   entries.filter((e) => e.phase === 'active').length,
    complete: entries.filter((e) => e.phase === 'complete').length,
  };

  const add = useCallback<UseColony['add']>((input) => {
    const now = new Date().toISOString();
    const entry: ColonyEntry = { ...input, id: uid(), claimed_at: now, updated_at: now };
    persist([entry, ...entries]);
    return entry;
  }, [entries, persist]);

  const update = useCallback<UseColony['update']>((id, patch) => {
    persist(entries.map((e) =>
      e.id === id
        ? { ...e, ...patch, updated_at: new Date().toISOString() }
        : e
    ));
  }, [entries, persist]);

  const remove = useCallback((id: string) => {
    persist(entries.filter((e) => e.id !== id));
  }, [entries, persist]);

  const clear = useCallback(() => persist([]), [persist]);

  const exportCsv = useCallback(() => {
    const snapshot = readStorage();
    if (snapshot.length === 0) return;
    const q = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['Name', 'Phase', 'Target population', 'Current population',
                    'X', 'Y', 'Z', 'Claimed at', 'Updated at', 'Notes'];
    const rows = snapshot.map((e) => [
      e.name, e.phase,
      e.target_population ?? '',
      e.current_population ?? '',
      e.x ?? '', e.y ?? '', e.z ?? '',
      e.claimed_at, e.updated_at,
      e.notes,
    ]);
    const csv = [header.map(q).join(','), ...rows.map((r) => r.map(q).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ed-colony-tracker-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  return { entries, counts, add, update, remove, clear, exportCsv };
}
