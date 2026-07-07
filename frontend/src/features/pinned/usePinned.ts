/**
 * `usePinned` — thin compatibility wrapper around `usePinnedStore`.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §3 / Phase 7):
 * The previous implementation was 125 lines of useState/useEffect/
 * cross-tab `storage`-event glue. We now delegate to the Zustand store
 * (which gets cross-tab sync via the persist middleware for free) and
 * keep this file as a stable public API surface for the existing
 * call-sites (`<App />`, `<PinnedTab />`, `<ResultCard />`).
 *
 * The signature is identical to the old hook so no caller had to change.
 */
import { usePinnedStore, exportPinnedJson, type PinnedEntry } from '@/store/pinnedStore';

export type { PinnedEntry };

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

export function usePinned(): UsePinned {
  const entries = usePinnedStore((s) => s.entries);
  const has     = usePinnedStore((s) => s.has);
  const toggle  = usePinnedStore((s) => s.toggle);
  const remove  = usePinnedStore((s) => s.remove);
  const clear   = usePinnedStore((s) => s.clear);

  return {
    entries,
    has,
    toggle,
    remove,
    clear,
    exportJson: () => exportPinnedJson(entries),
  };
}
