import { QueryClient } from '@tanstack/svelte-query';
import type { Id64 } from '$lib/domain/id64';

export const queryKeys = {
  all: ['ed-finder'] as const,
  auth: () => [...queryKeys.all, 'auth'] as const,
  health: () => [...queryKeys.all, 'health'] as const,
  system: (id64: Id64) => [...queryKeys.all, 'system', id64] as const,
  compare: (id64s: readonly Id64[]) =>
    [...queryKeys.all, 'compare', ...id64s] as const,
  optimiser: (id64: Id64) => [...queryKeys.system(id64), 'optimiser'] as const,
  operator: (resource: string) =>
    [...queryKeys.all, 'operator', resource] as const,
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
