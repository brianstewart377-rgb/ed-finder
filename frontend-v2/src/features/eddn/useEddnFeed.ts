import { useEffect, useRef, useState } from 'react';

/**
 * Live EDDN events feed hook.
 *
 * Polls `/api/events/recent` every `intervalMs` (default 4s) and keeps a
 * rolling window of the last `keep` events. We poll instead of using the
 * existing SSE endpoint (`/api/events/live`) to keep the preview-pod
 * footprint tiny and survive the inevitable pause-and-resume cycle of
 * dev work — SSE reconnections during HMR can throw in non-trivial bugs
 * we don't need here.
 */
export interface EddnEvent {
  system_name: string;
  id64:        number;
  type:        string;
  timestamp:   string | null;
}

export function useEddnFeed({
  intervalMs = 4000,
  keep       = 30,
}: { intervalMs?: number; keep?: number } = {}) {
  const [events, setEvents] = useState<EddnEvent[]>([]);
  const [error,  setError]  = useState<string | null>(null);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const tick = async () => {
      try {
        const res = await fetch('/api/events/recent?limit=20', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const fresh: EddnEvent[] = Array.isArray(json.events) ? json.events : [];
        if (cancelled) return;

        const newEvents = fresh.filter((e) => {
          const k = `${e.id64}|${e.type}|${e.timestamp}`;
          if (seen.current.has(k)) return false;
          seen.current.add(k);
          return true;
        });

        if (newEvents.length) {
          setEvents((prev) => [...newEvents, ...prev].slice(0, keep));
        }
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(tick, intervalMs);
        }
      }
    };

    void tick();

    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [intervalMs, keep]);

  return { events, error };
}
