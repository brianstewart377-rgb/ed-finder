import { useEffect, useState } from 'react';
import { api, type EliteNewsItem } from '@/lib/api';

export type EliteNewsFeedStatus = 'loading' | 'live' | 'offline';

export function useEliteNewsFeed({
  intervalMs = 15 * 60 * 1000,
  limit = 8,
}: {
  intervalMs?: number;
  limit?: number;
} = {}) {
  const [items, setItems] = useState<EliteNewsItem[]>([]);
  const [status, setStatus] = useState<EliteNewsFeedStatus>('loading');
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const load = async () => {
      try {
        const response = await api.eliteNewsLatest(limit);
        if (cancelled) return;
        setItems(Array.isArray(response.items) ? response.items : []);
        setStale(Boolean(response.stale));
        setStatus('live');
      } catch {
        if (cancelled) return;
        setStatus('offline');
        setStale(false);
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(() => {
            void load();
          }, intervalMs);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [intervalMs, limit]);

  return { items, status, stale };
}
