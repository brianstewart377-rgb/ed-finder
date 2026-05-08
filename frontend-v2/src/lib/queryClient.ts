/**
 * Shared TanStack Query client.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §H3 follow-up / Phase 7):
 * The previous codebase had every `useFoo` hook re-implementing
 * `useState/useEffect` + manual loading/error/data state machines for
 * every API call. TanStack Query gives us:
 *   • Automatic dedupe of identical concurrent requests
 *   • Configurable retries with exponential backoff
 *   • Stale-while-revalidate caching
 *   • DevTools (mounted in dev only — see App.tsx)
 *
 * Tuning notes:
 *   • staleTime = 30s — most ED Finder data (system records, ratings)
 *     doesn't change between consecutive view-renders. 30 s avoids
 *     refetch storms when a user toggles tabs.
 *   • gcTime = 5 min — keep responses around long enough that a user
 *     re-opening a system detail modal doesn't see a flash.
 *   • retry = 1 — the API is local; one retry is enough. More than
 *     that on the 503 path we just added in §C5 would mask outages.
 *   • refetchOnWindowFocus = false — would interrupt a user pasting a
 *     system name into the search box.
 */
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      gcTime:    5 * 60 * 1000,
      retry:     1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
