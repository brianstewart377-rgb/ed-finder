import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { EddnEvent } from '@/lib/api';

/**
 * Live EDDN events feed hook.
 *
 * Strategy:
 *   • Prefer SSE in production.
 *   • If SSE is slow or reconnecting, fall back to recent-events polling.
 *   • Keep UI status compact and user-facing (`live`, `reconnecting`,
 *     `offline`, `connecting`) without exposing transport internals.
 */
export type { EddnEvent };
export type EddnFeedStatus = 'connecting' | 'live' | 'reconnecting' | 'offline';

const KEY = (e: EddnEvent) => `${e.id64}|${e.type}|${e.timestamp}`;

function coerceEvent(input: unknown): EddnEvent | null {
  if (!input || typeof input !== 'object') return null;
  const raw = input as Record<string, unknown>;
  const id64 = Number(raw.id64);
  if (!Number.isFinite(id64) || id64 <= 0) return null;
  const systemName = typeof raw.system_name === 'string' && raw.system_name.trim().length > 0
    ? raw.system_name.trim()
    : 'Unknown system';
  const type = typeof raw.type === 'string' && raw.type.trim().length > 0
    ? raw.type.trim()
    : 'Event';
  const timestamp = typeof raw.timestamp === 'string' ? raw.timestamp : null;
  return {
    id64,
    system_name: systemName,
    type,
    timestamp,
  };
}

export function useEddnFeed({
  intervalMs = 4000,
  keep = 30,
  flushMs = 1500,
  sseGraceMs = 9000,
  preferSse = import.meta.env.PROD,
}: {
  intervalMs?: number;
  keep?: number;
  flushMs?: number;
  sseGraceMs?: number;
  preferSse?: boolean;
} = {}) {
  const [events, setEvents] = useState<EddnEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<EddnFeedStatus>('connecting');
  const seen = useRef<Set<string>>(new Set());
  const pending = useRef<EddnEvent[]>([]);
  const flushT = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let pollTimer: number | null = null;
    let graceTimer: number | null = null;
    let es: EventSource | null = null;
    let pollingEnabled = false;

    const scheduleFlush = () => {
      if (flushT.current != null) return;
      flushT.current = window.setTimeout(() => {
        flushT.current = null;
        if (cancelled || pending.current.length === 0) return;
        const batch = pending.current;
        pending.current = [];
        setEvents((prev) => [...batch, ...prev].slice(0, keep));
      }, flushMs);
    };

    const push = (incoming: unknown[]) => {
      if (cancelled) return;
      const fresh = incoming
        .map(coerceEvent)
        .filter((event): event is EddnEvent => Boolean(event))
        .filter((event) => {
          const key = KEY(event);
          if (seen.current.has(key)) return false;
          seen.current.add(key);
          return true;
        });
      if (!fresh.length) return;
      pending.current = [...fresh, ...pending.current];
      setStatus('live');
      setError(null);
      scheduleFlush();
    };

    const pollRecentEvents = async () => {
      try {
        const json = await api.recentEvents(Math.max(20, keep));
        const incoming = Array.isArray(json.events) ? json.events : [];
        push(incoming);
        if (seen.current.size === 0) {
          setStatus(preferSse ? 'reconnecting' : 'connecting');
        }
        setError(null);
      } catch {
        if (cancelled) return;
        if (seen.current.size > 0) {
          setStatus('reconnecting');
          setError('reconnecting');
        } else {
          setStatus('offline');
          setError('offline');
        }
      } finally {
        if (!cancelled && pollingEnabled) {
          pollTimer = window.setTimeout(() => {
            void pollRecentEvents();
          }, intervalMs);
        }
      }
    };

    const startPollingFallback = () => {
      if (pollingEnabled || cancelled) return;
      pollingEnabled = true;
      if (seen.current.size > 0) {
        setStatus('reconnecting');
      }
      void pollRecentEvents();
    };

    const stopPollingFallback = () => {
      pollingEnabled = false;
      if (pollTimer != null) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    };

    if (preferSse && typeof EventSource !== 'undefined') {
      try {
        es = new EventSource('/api/events/live');
        es.onopen = () => {
          if (cancelled) return;
          if (seen.current.size === 0) setStatus('connecting');
          setError(null);
        };
        es.onmessage = (event) => {
          const parsed = coerceEvent(safeParse(event.data));
          if (!parsed) return;
          push([parsed]);
          stopPollingFallback();
        };
        es.onerror = () => {
          if (cancelled) return;
          setStatus(seen.current.size > 0 ? 'reconnecting' : 'offline');
          setError('reconnecting');
          startPollingFallback();
        };

        graceTimer = window.setTimeout(() => {
          if (cancelled) return;
          if (seen.current.size === 0) {
            setStatus('reconnecting');
            startPollingFallback();
          }
        }, sseGraceMs);
      } catch {
        setStatus('reconnecting');
        startPollingFallback();
      }
    } else {
      pollingEnabled = true;
      void pollRecentEvents();
    }

    return () => {
      cancelled = true;
      es?.close();
      stopPollingFallback();
      if (graceTimer != null) {
        window.clearTimeout(graceTimer);
      }
      if (flushT.current != null) {
        window.clearTimeout(flushT.current);
        flushT.current = null;
      }
    };
  }, [flushMs, intervalMs, keep, preferSse, sseGraceMs]);

  return { events, error, status };
}

function safeParse(input: string): unknown {
  try {
    return JSON.parse(input);
  } catch {
    return null;
  }
}
