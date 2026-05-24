/**
 * Pinned-systems store (Zustand + persist middleware).
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §3 / Phase 7):
 * `usePinned.ts` used to be 125 lines of `useState + useEffect +
 * cross-tab `storage` event + manual JSON serialise/deserialise`. The
 * Zustand persist middleware gives us all of that out of the box at
 * roughly a third of the code.
 *
 * Backwards compatibility: the storage key is unchanged (`ed_pinned`)
 * so existing users keep their pins after the refactor. The persisted
 * shape is the array directly (not Zustand's default `{state, version}`
 * envelope) so old vanilla-app snapshots still round-trip — see the
 * custom `storage` adapter below.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface PinnedEntry {
  id64:          number;
  name:          string;
  x:             number | null;
  y:             number | null;
  z:             number | null;
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

interface PinnedState {
  entries: PinnedEntry[];
  has:     (id64: number) => boolean;
  toggle:  (entry: PinnedEntry) => boolean;
  remove:  (id64: number) => void;
  clear:   () => void;
}

const STORAGE_KEY = 'ed_pinned';

/**
 * Custom storage adapter that reads/writes the bare array (the legacy
 * shape) instead of Zustand's default `{state: {...}, version: ...}`
 * envelope. This is what keeps existing users' pins intact across the
 * vanilla-app → React migration.
 */
const legacyStorage = {
  getItem: (name: string) => {
    if (name !== STORAGE_KEY) return null;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    // Re-wrap the legacy bare array into Zustand's expected envelope.
    return JSON.stringify({ state: { entries: JSON.parse(raw) }, version: 0 });
  },
  setItem: (name: string, value: string) => {
    if (name !== STORAGE_KEY) return;
    try {
      const parsed = JSON.parse(value);
      const entries = parsed?.state?.entries ?? [];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch {
      /* ignore quota / private-mode errors — same posture as legacy */
    }
  },
  removeItem: (name: string) => {
    if (name === STORAGE_KEY) localStorage.removeItem(STORAGE_KEY);
  },
};

export const usePinnedStore = create<PinnedState>()(
  persist(
    (set, get) => ({
      entries: [],
      has: (id64) => get().entries.some((e) => e.id64 === id64),
      toggle: (entry) => {
        const exists = get().entries.some((e) => e.id64 === entry.id64);
        if (exists) {
          set({ entries: get().entries.filter((e) => e.id64 !== entry.id64) });
          return false;
        }
        set({
          entries: [
            { ...entry, pinned_at: entry.pinned_at || new Date().toISOString() },
            ...get().entries,
          ],
        });
        return true;
      },
      remove: (id64) =>
        set({ entries: get().entries.filter((e) => e.id64 !== id64) }),
      clear: () => set({ entries: [] }),
    }),
    {
      name:    STORAGE_KEY,
      storage: createJSONStorage(() => legacyStorage),
    },
  ),
);

/**
 * Convenience helper for export-as-JSON. Stays a free function (rather
 * than a store action) because it has DOM side-effects (`<a> click`)
 * that don't belong in store internals.
 */
export function exportPinnedJson(entries: PinnedEntry[]): void {
  const blob = new Blob([JSON.stringify(entries, null, 2)], {
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
}
