import {
  createMutation,
  createQuery,
  useIsMutating,
  useQueryClient,
} from '@tanstack/svelte-query';
import { fromStore } from 'svelte/store';
import { addWatchlist, getWatchlist, removeWatchlist } from '$lib/api/client';
import { queryKeys } from '$lib/api/query';
import { auth } from '$lib/auth/auth';
import type { Id64 } from '$lib/domain/id64';
import { usePersistenceContext } from '$lib/persistence/context';

interface WatchlistChange {
  action: 'add' | 'remove';
  id64: Id64;
  accountId: string | null;
  syncKey: string;
}

/** Shared cache and captured mutation scopes for Finder actions and saved lists. */
export function createWatchlistQuery() {
  const client = useQueryClient();
  const session = fromStore(auth);
  const credential = fromStore(usePersistenceContext().syncKey);
  const accountId = $derived(session.current.user?.account_id ?? null);
  const syncKey = $derived(credential.current.value.state.syncKey);
  const enabled = $derived(
    !session.current.loading &&
      credential.current.hydrated &&
      syncKey.length > 0,
  );
  const query = createQuery(() => {
    const requestAccountId = accountId;
    const requestKey = syncKey;
    return {
      queryKey: queryKeys.watchlist(requestAccountId, requestKey),
      queryFn: ({ signal }) => getWatchlist(requestKey, signal),
      enabled,
      staleTime: 30_000,
      gcTime: 300_000,
      retry: 0,
    };
  });
  const mutationKey = [...queryKeys.all, 'watchlist-change'] as const;
  const belongsToCurrentScope = (change: WatchlistChange | undefined) =>
    change?.accountId === accountId && change?.syncKey === syncKey;
  const changes = useIsMutating({
    mutationKey,
    predicate: (mutation) =>
      belongsToCurrentScope(
        mutation.state.variables as WatchlistChange | undefined,
      ),
  });
  const mutation = createMutation(() => ({
    mutationKey,
    mutationFn: (change: WatchlistChange) =>
      change.action === 'add'
        ? addWatchlist(change.syncKey, change.id64)
        : removeWatchlist(change.syncKey, change.id64),
    onSuccess: async (_result, change) => {
      // Account/key changes during the request must not update the new user's list.
      await client.invalidateQueries({
        queryKey: queryKeys.watchlist(change.accountId, change.syncKey),
        exact: true,
      });
    },
  }));
  const ready = $derived(enabled && query.data !== undefined);
  function change(action: WatchlistChange['action'], id64: Id64): void {
    if (!ready || changes.current > 0) return;
    mutation.mutate({ action, id64, accountId, syncKey });
  }

  return {
    query,
    add: (id64: Id64) => change('add', id64),
    remove: (id64: Id64) => change('remove', id64),
    get ready() {
      return ready;
    },
    get pending() {
      return changes.current > 0;
    },
    get error(): string | null {
      return mutation.isError && belongsToCurrentScope(mutation.variables)
        ? 'Your watchlist could not be updated. Try again.'
        : null;
    },
    retry(): void {
      if (
        mutation.isError &&
        belongsToCurrentScope(mutation.variables) &&
        mutation.variables
      ) {
        change(mutation.variables.action, mutation.variables.id64);
      } else if (enabled) {
        void query.refetch();
      }
    },
  };
}
