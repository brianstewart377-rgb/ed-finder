import { useSystemDetail } from './useSystemDetail';
import type { SelectedSystemRouteStatus } from '@/hooks/useHashRoute';
import type { SystemDetail } from '@/types/api';

export type SelectedSystemResolution = 'none' | 'loading' | 'available' | 'invalid' | 'unavailable';

export interface SelectedSystemContext {
  id64: number | null;
  resolution: SelectedSystemResolution;
  data: SystemDetail | null;
  error: string | null;
  refetch: () => void;
}

/**
 * Resolves route-owned selected-system context without allowing stale query
 * data to masquerade as the destination after an invalid or unavailable link.
 */
export function useSelectedSystemContext(
  id64: number | null,
  routeStatus: SelectedSystemRouteStatus,
): SelectedSystemContext {
  const shouldResolve = routeStatus === 'pending' && id64 != null;
  const detail = useSystemDetail(shouldResolve ? id64 : null);

  if (routeStatus === 'invalid') {
    return {
      id64: null,
      resolution: 'invalid',
      data: null,
      error: 'The requested system link is invalid.',
      refetch: detail.refetch,
    };
  }

  if (!shouldResolve) {
    return {
      id64: null,
      resolution: 'none',
      data: null,
      error: null,
      refetch: detail.refetch,
    };
  }

  if (detail.loading) {
    return {
      id64,
      resolution: 'loading',
      data: null,
      error: null,
      refetch: detail.refetch,
    };
  }

  if (detail.data) {
    return {
      id64,
      resolution: 'available',
      data: detail.data,
      error: null,
      refetch: detail.refetch,
    };
  }

  return {
    id64: null,
    resolution: 'unavailable',
    data: null,
    error: detail.error ?? 'The requested system is unavailable to this workspace.',
    refetch: detail.refetch,
  };
}
