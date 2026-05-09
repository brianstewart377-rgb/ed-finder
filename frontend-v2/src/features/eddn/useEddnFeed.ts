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
  // Batch-flush window — at the production EDDN rate (~19 events/sec)
  // calling setState on every SSE message makes React re-render the
  // marquee 19 times per second, which restarts the CSS animation
  // every frame and produces the "ticker is just a blur" effect the
  // user reported. We accumulate incoming events in a ref and only
  // commit to React state every `flushMs`, so the marquee animation
  // can actually play through. 1500 ms = roughly 1 visual cycle of
  // updates per visible system on screen.
  flushMs    = 1500,
}: { intervalMs?: number; keep?: number; flushMs?: number } = {}) {
  const [events, setEvents] = useState<EddnEvent[]>([]);
  const [error,  setError]  = useState<string | null>(null);
  const seen    = useRef<Set<string>>(new Set());
  const pending = useRef<EddnEvent[]>([]);
  const flushT  = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    let es: EventSource | null = null;

    const scheduleFlush = () => {
      if (flushT.current != null) return;       // already armed
      flushT.current = window.setTimeout(() => {
        flushT.current = null;
        if (cancelled || pending.current.length === 0) return;
        const batch = pending.current;
        pending.current = [];
        setEvents((prev) => [...batch, ...prev].slice(0, keep));
      }, flushMs);
    };

    const push = (incoming: EddnEvent[]) => {
      if (cancelled) return;
      const fresh = incoming.filter((e) => {
        const k = KEY(e);
        if (seen.current.has(k)) return false;
        seen.current.add(k);
        return true;
      });
      if (!fresh.length) return;
      pending.current = [...fresh, ...pending.current];
      scheduleFlush();
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
      if (flushT.current != null) {
        window.clearTimeout(flushT.current);
        flushT.current = null;
      }
    };
  }, [intervalMs, keep, flushMs]);

  return { events, error };
}
