import { useEffect, useRef, useState } from 'react';

/**
 * Live EDDN events feed hook.
 *
 * Strategy:
 *   • Production / preview build → Server-Sent Events on /api/events/live.
 *     This piggybacks on the existing Redis-pubsub bridge in the API
 *     (see backend/routers/events.py) and costs ~zero DB I/O per user.
 *   • Dev build → poll /api/events/recent every `intervalMs`. SSE +
 *     Vite HMR is jittery (the dev proxy reconnects on every HMR ping)
 *     so we keep the polling fallback for local development only.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §H3): the previous
 * always-polling implementation hammered Postgres at 4 s × N concurrent
 * users in production despite the SSE bridge already existing.
 */
export interface EddnEvent {
  system_name: string;
  id64:        number;
  type:        string;
  timestamp:   string | null;
}

const KEY = (e: EddnEvent) => `${e.id64}|${e.type}|${e.timestamp}`;

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
    let es: EventSource | null = null;

    const push = (incoming: EddnEvent[]) => {
      if (cancelled) return;
      const fresh = incoming.filter((e) => {
        const k = KEY(e);
        if (seen.current.has(k)) return false;
        seen.current.add(k);
        return true;
      });
      if (fresh.length) setEvents((prev) => [...fresh, ...prev].slice(0, keep));
    };

    // ── PROD / preview: SSE ──────────────────────────────────────────────
    if (import.meta.env.PROD && typeof EventSource !== 'undefined') {
      try {
        es = new EventSource('/api/events/live');
        es.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data) as EddnEvent;
            if (data && data.id64) push([data]);
          } catch { /* heartbeat / non-JSON — ignore */ }
        };
        es.onerror = () => {
          // Browser auto-reconnects; just surface the state.
          setError('SSE connection interrupted (auto-reconnect)');
        };
        return () => { cancelled = true; es?.close(); };
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        // Fall through to polling on EventSource construction failure.
      }
    }

    // ── DEV: polling fallback ────────────────────────────────────────────
    const tick = async () => {
      try {
        const res = await fetch('/api/events/recent?limit=20', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const fresh: EddnEvent[] = Array.isArray(json.events) ? json.events : [];
        push(fresh);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) timer = window.setTimeout(tick, intervalMs);
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
