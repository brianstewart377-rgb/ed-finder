import { QueryClient } from '@tanstack/svelte-query';
import type { Id64 } from '$lib/domain/id64';
import type { CatalogueViewportRequest, ExploreSearchRequest } from './client';

export const queryKeys = {
  all: ['ed-finder'] as const,
  auth: () => [...queryKeys.all, 'auth'] as const,
  galaxyImpact: (accountId: string) =>
    [...queryKeys.auth(), accountId, 'galaxy-impact'] as const,
  health: () => [...queryKeys.all, 'health'] as const,
  system: (id64: Id64) => [...queryKeys.all, 'system', id64] as const,
  autocomplete: (query: string) =>
    [...queryKeys.all, 'explore', 'autocomplete', query] as const,
  explore: (request: ExploreSearchRequest) =>
    [...queryKeys.all, 'explore', 'results', JSON.stringify(request)] as const,
  catalogueViewport: (request: CatalogueViewportRequest) =>
    [
      ...queryKeys.all,
      'map',
      'catalogue-stars',
      JSON.stringify(request),
    ] as const,
  commanderViewport: (syncKey: string, request: CatalogueViewportRequest) =>
    [
      ...queryKeys.all,
      'map',
      'commander-history',
      syncKey,
      JSON.stringify(request),
    ] as const,
  compare: (id64s: readonly Id64[]) =>
    [...queryKeys.all, 'compare', ...id64s] as const,
  watchlist: (accountId: string | null, syncKey: string) =>
    [...queryKeys.all, 'watchlist', accountId, syncKey] as const,
};

/** The one application query client; feature providers should reuse this root. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 300_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
});
