import { useCallback, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type WatchlistEntry } from '@/lib/api';
import { useSyncKeyStore } from '@/store/syncKeyStore';

/**
 * Watchlist state.
 *
 * Audit Phase 8 (2026-05-09): rewritten on top of TanStack Query so the
 * NavBar count, the Watchlist tab, the SystemDetailModal "Save to
 * Watchlist" toggle, and any future consumer all share one cache entry
 * per sync key (`['watchlist', syncKey]`). Previously each `useWatchlist()` callsite owned its
 * own `useState`, so every tab refetched independently and the same
 * data could be in three different states at once.
 *
 * Optimistic updates: add/remove mutate the cache immediately via
 * `setQueryData` and roll back on `onError`. Without this, the UI feels
 * laggy on every click — the vanilla app waits for the round-trip and
 * it's noticeable. After settle we invalidate to pull canonical data
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

export function useWatchlist(): UseWatchlist {
  const qc = useQueryClient();
  const syncKey = useSyncKeyStore((state) => state.syncKey);
  const queryKey = watchlistKey(syncKey);

  const query = useQuery({
    queryKey,
    queryFn:     async () => (await api.watchlist(syncKey)).watchlist,
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
    onMutate: async ({ id64, hint }: { id64: number; hint?: Partial<WatchlistEntry> }) => {
      // Cancel any in-flight refetch so it doesn't overwrite our optimistic update.
      await qc.cancelQueries({ queryKey });
      const previous = qc.getQueryData<WatchlistEntry[]>(queryKey) ?? [];
      if (previous.some((e) => e.system_id64 === id64)) {
        return { previous, skip: true };
      }
      const optimistic: WatchlistEntry = {
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
      qc.setQueryData<WatchlistEntry[]>(queryKey, [optimistic, ...previous]);
      return { previous, skip: false };
    },
    onError: (_err, _vars, ctx) => {
      // Roll back to the snapshot we took in onMutate.
      if (ctx?.previous) qc.setQueryData(queryKey, ctx.previous);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id64: number) => api.watchRemove(syncKey, id64),
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
