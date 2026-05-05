import { useCallback, useEffect, useState } from 'react';
import { api, type WatchlistEntry } from '@/lib/api';

/**
 * Watchlist state.
 *
 * Optimistic updates: add/remove mutate the local list immediately and roll
 * back on API failure. Without this, the UI feels laggy on every click —
 * the vanilla app waits for the round-trip and it's noticeable.
 */
export interface UseWatchlist {
  entries:   WatchlistEntry[];
  loading:   boolean;
  error:     string | null;
  refresh:   () => Promise<void>;
  add:       (id64: number, hint?: Partial<WatchlistEntry>) => Promise<void>;
  remove:    (id64: number) => Promise<void>;
  has:       (id64: number) => boolean;
}

export function useWatchlist(): UseWatchlist {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.watchlist();
      setEntries(r.watchlist);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load — explicit so consumers can opt in (e.g. lazy-load on the
  // watchlist tab only). For now we always load on mount; the API call is
  // cheap (~50 rows max) and the badge wants the count regardless.
  useEffect(() => { void refresh(); }, [refresh]);

  const add = useCallback(async (id64: number, hint?: Partial<WatchlistEntry>) => {
    if (entries.some((e) => e.system_id64 === id64)) return;
    // Optimistic insert with whatever hint info the caller supplied.
    const optimistic: WatchlistEntry = {
      system_id64:  id64,
      name:         hint?.name ?? `System ${id64}`,
      x:            hint?.x ?? 0,
      y:            hint?.y ?? 0,
      z:            hint?.z ?? 0,
      population:   hint?.population ?? 0,
      is_colonised: hint?.is_colonised ?? false,
      added_at:     new Date().toISOString(),
      score:        hint?.score ?? null,
    };
    setEntries((prev) => [optimistic, ...prev]);
    try {
      await api.watchAdd(id64);
      // Refresh to pull canonical data (score + economy_suggestion are
      // joined server-side and only available after the round-trip).
      void refresh();
    } catch (e) {
      // Roll back.
      setEntries((prev) => prev.filter((e2) => e2.system_id64 !== id64));
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [entries, refresh]);

  const remove = useCallback(async (id64: number) => {
    const before = entries;
    setEntries((prev) => prev.filter((e) => e.system_id64 !== id64));
    try {
      await api.watchRemove(id64);
    } catch (e) {
      setEntries(before);                                  // roll back
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [entries]);

  const has = useCallback((id64: number) => entries.some((e) => e.system_id64 === id64), [entries]);

  return { entries, loading, error, refresh, add, remove, has };
}
