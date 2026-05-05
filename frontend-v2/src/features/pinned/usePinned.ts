import { useCallback, useEffect, useState } from 'react';

/**
 * A pinned system is entirely client-side state. The legacy vanilla app
 * stores these in `localStorage` under `ed_pinned` with this exact schema;
 * we match the schema so users keep their pins when we flip root → v2.
 *
 * Do NOT rename fields. Migrating existing users off an old key is harder
 * than living with snake_case.
 */
export interface PinnedEntry {
  id64:          number;
  name:          string;
  x:             number;
  y:             number;
  z:             number;
  population:    number;
  is_colonised:  boolean;
  /** Distance (LY) from the reference at the moment it was pinned. */
  distance?:     number | null;
  /** Snapshot of the score at pin time. Not refreshed — the point of a pin
   *  is to remember "this looked good when I saw it". */
  rating:        number | null;
  /** Snapshot of the suggested economy at pin time. */
  economy:       string | null;
  pinned_at:     string;
}

const STORAGE_KEY = 'ed_pinned';

function readStorage(): PinnedEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PinnedEntry[]) : [];
  } catch {
    // Corrupt JSON, quota error, disabled storage — degrade to empty rather
    // than crash the app. Legacy vanilla does the same (swallowed errors).
    return [];
  }
}

function writeStorage(entries: PinnedEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    /* ignore quota / private-mode errors */
  }
}

export interface UsePinned {
  entries: PinnedEntry[];
  has:     (id64: number) => boolean;
  /** Toggle-style add: if already pinned, removes it; otherwise adds.
   *  Returns the new pinned state for this id64. */
  toggle:  (entry: PinnedEntry) => boolean;
  remove:  (id64: number) => void;
  clear:   () => void;
  exportJson: () => void;
}

/**
 * Local-storage-backed pinned-systems list, with cross-tab sync via the
 * `storage` event so opening the app in two windows doesn't desync.
 */
export function usePinned(): UsePinned {
  const [entries, setEntries] = useState<PinnedEntry[]>(readStorage);

  // Cross-tab sync: another window / tab modified the same key.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setEntries(readStorage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const persist = useCallback((next: PinnedEntry[]) => {
    writeStorage(next);
    setEntries(next);
  }, []);

  const has = useCallback(
    (id64: number) => entries.some((e) => e.id64 === id64),
    [entries],
  );

  const toggle = useCallback((entry: PinnedEntry): boolean => {
    const idx = entries.findIndex((e) => e.id64 === entry.id64);
    if (idx >= 0) {
      persist(entries.filter((e) => e.id64 !== entry.id64));
      return false;
    }
    persist([{ ...entry, pinned_at: entry.pinned_at || new Date().toISOString() }, ...entries]);
    return true;
  }, [entries, persist]);

  const remove = useCallback((id64: number) => {
    persist(entries.filter((e) => e.id64 !== id64));
  }, [entries, persist]);

  const clear = useCallback(() => {
    persist([]);
  }, [persist]);

  const exportJson = useCallback(() => {
    // Re-read from storage to capture the most up-to-date snapshot, even if
    // the user clicked Export during an optimistic state update.
    const snapshot = readStorage();
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ed-pinned-systems-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  return { entries, has, toggle, remove, clear, exportJson };
}
