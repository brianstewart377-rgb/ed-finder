import { useCallback, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type WatchlistEntry } from '@/lib/api';
import { useSyncKeyStore } from '@/store/syncKeyStore';

/**
 * Watchlist state.
 *
 * Audit Phase 8 (2026-05-09): rewritten on top of TanStack Query so the
 * NavBar count, the Watchlist tab, the SystemDetailModal "Save to
 * Watchlist" toggle, and any future consumer all share one cache entry
 * (`['watchlist']`). Previously each `useWatchlist()` callsite owned its
 * own `useState`, so every tab refetched independently and the same
 * data could be in three different states at once.
 *
 * Adds wait for the server before marking a system saved so a fresh
 * review session never claims membership before persistence confirms it.
 * Removes still clear the local cache immediately and roll back on
 * non-404 failures. After settle we invalidate to pull canonical data
 * (score + economy_suggestion are joined server-side and only available
 * after the round-trip).
 *
 * Public interface (`UseWatchlist`) is unchanged from the bespoke
 * implementation, so no consumers need rewriting.
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

const watchlistKey = (syncKey: string) => ['watchlist', syncKey] as const;

function entryFromHint(id64: number, hint?: Partial<WatchlistEntry>): WatchlistEntry {
  return {
    system_id64:  id64,
    name:         hint?.name ?? `System ${id64}`,
    x:            hint?.x ?? null,
    y:            hint?.y ?? null,
    z:            hint?.z ?? null,
    population:   hint?.population ?? null,
    is_colonised: hint?.is_colonised ?? false,
    added_at:     new Date().toISOString(),
    score:        hint?.score ?? null,
  };
}

export function useWatchlist(): UseWatchlist {
  const qc = useQueryClient();
  const syncKey = useSyncKeyStore((state) => state.syncKey);
  const queryKey = useMemo(() => watchlistKey(syncKey), [syncKey]);

  const query = useQuery({
    queryKey,
    queryFn:     async () => (await api.watchlist(syncKey)).watchlist,
    enabled:     Boolean(syncKey),
    staleTime:   30_000,        // re-fetch on tab focus only after 30s
    gcTime:      5 * 60_000,    // 5min cache retention
  });

  const entries = useMemo(() => query.data ?? [], [query.data]);
  const loading = query.isPending;
  const error   = query.error
    ? (query.error instanceof Error ? query.error.message : String(query.error))
    : null;

  const refresh = useCallback(async () => {
    await qc.invalidateQueries({ queryKey });
  }, [qc, queryKey]);

  const addMutation = useMutation({
    mutationFn: (vars: { id64: number; hint?: Partial<WatchlistEntry> }) =>
      api.watchAdd(syncKey, vars.id64),
    onSuccess: (_data, { id64, hint }) => {
      qc.setQueryData<WatchlistEntry[]>(queryKey, (current = []) => {
        if (current.some((entry) => entry.system_id64 === id64)) return current;
        return [entryFromHint(id64, hint), ...current];
      });
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey });
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id64: number) => {
      try {
        await api.watchRemove(syncKey, id64);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return;
        throw error;
      }
    },
    onMutate: async (id64: number) => {
      await qc.cancelQueries({ queryKey });
      const previous = qc.getQueryData<WatchlistEntry[]>(queryKey) ?? [];
      qc.setQueryData<WatchlistEntry[]>(
        queryKey,
        previous.filter((e) => e.system_id64 !== id64),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(queryKey, ctx.previous);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey });
    },
  });

  const add = useCallback(
    async (id64: number, hint?: Partial<WatchlistEntry>) => {
      await addMutation.mutateAsync({ id64, hint });
    },
    [addMutation],
  );

  const remove = useCallback(
    async (id64: number) => {
      await removeMutation.mutateAsync(id64);
    },
    [removeMutation],
  );

  const has = useCallback(
    (id64: number) => entries.some((e) => e.system_id64 === id64),
    [entries],
  );

  return { entries, loading, error, refresh, add, remove, has };
}
