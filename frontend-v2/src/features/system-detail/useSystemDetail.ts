/**
 * `useSystemDetail` — TanStack Query-backed system detail fetch.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §3 / Phase 7): replaces
 * 49 lines of `useState/useEffect/abort-handling` boilerplate with
 * 12 lines of `useQuery`. Get for free:
 *   • Auto-dedupe of concurrent requests (open the same system in two
 *     places → one HTTP call)
 *   • Stale-while-revalidate (re-opening shows cached, then refreshes)
 *   • In-memory cache survives modal close → next open is instant
 *   • Configurable retry (we cap at 1 globally — see lib/queryClient.ts)
 *
 * Public signature unchanged for backward compat with `<SystemDetailModal>`.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { SystemDetail } from '@/types/api';

export interface UseSystemDetail {
  data:    SystemDetail | null;
  loading: boolean;
  error:   string | null;
  refetch: () => void;
}

export function useSystemDetail(id64: number | null): UseSystemDetail {
  const q = useQuery<SystemDetail, Error>({
    queryKey: ['system', id64],
    enabled:  id64 != null,
    queryFn:  () => api.system(id64 as number),
  });
  return {
    data:    q.data ?? null,
    loading: q.isLoading,
    error:   q.error ? q.error.message : null,
    refetch: () => { void q.refetch(); },
  };
}
