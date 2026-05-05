import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { SystemDetail } from '@/types/api';

/**
 * Fetches /api/system/{id64} for a full join (system + rating + bodies +
 * stations). Backend caches the result in Redis under `sys:{id64}` for 24h
 * (settings.ttl_system) so re-opening the same system is instant.
 *
 * No abort-on-id-change handling — the modal is mounted briefly and the
 * happy path is "open one, look, close". If we ever pre-fetch on hover or
 * deep-link from a sibling tab, revisit with AbortController.
 */
export interface UseSystemDetail {
  data:    SystemDetail | null;
  loading: boolean;
  error:   string | null;
  /** Force a fresh fetch (bypasses local component state, not the Redis cache). */
  refetch: () => void;
}

export function useSystemDetail(id64: number | null): UseSystemDetail {
  const [data,    setData]    = useState<SystemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [tick,    setTick]    = useState(0);

  useEffect(() => {
    if (id64 == null) { setData(null); setError(null); setLoading(false); return; }

    let cancelled = false;
    setLoading(true);
    setError(null);

    api.system(id64)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setData(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [id64, tick]);

  return { data, loading, error, refetch: () => setTick((t) => t + 1) };
}
