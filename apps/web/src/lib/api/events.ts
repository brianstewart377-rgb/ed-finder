import { parseLosslessJson } from './lossless-json';

export const LIVE_EVENTS_PATH = '/api/events/live';

export type EventStreamStatus =
  'connecting' | 'open' | 'error' | 'reconnecting' | 'closed';

export interface EventStreamContract {
  close(): void;
}

export interface EventStreamOptions<T> {
  onEvent(event: T): void;
  onOpen?(): void;
  /** Native EventSource reconnects. Consumers may start bounded polling here. */
  onDisconnected?(event: Event): void;
  /** Observable connection state for status UI and polling-fallback ownership. */
  onStatusChange?(status: EventStreamStatus): void;
  /** Malformed frames are reported and ignored rather than escaping the handler. */
  onParseError?(error: Error): void;
  eventSource?: typeof EventSource;
}

/**
 * SSE deliberately stays outside generated query functions: EventSource owns
 * native reconnect, cookies are enabled, and consumers own a polling fallback.
 */
export function openLiveEventStream<T>(
  options: EventStreamOptions<T>,
): EventStreamContract {
  const EventSourceClass = options.eventSource ?? globalThis.EventSource;
  if (!EventSourceClass)
    throw new Error('EventSource is unavailable; use the polling fallback');

  let closed = false;
  let status: EventStreamStatus = 'connecting';
  const setStatus = (next: EventStreamStatus) => {
    if (next === status) return;
    status = next;
    options.onStatusChange?.(next);
  };
  options.onStatusChange?.(status);
  const source = new EventSourceClass(LIVE_EVENTS_PATH, {
    withCredentials: true,
  });

  source.onopen = () => {
    if (closed) return;
    setStatus('open');
    options.onOpen?.();
  };
  source.onmessage = (event) => {
    if (closed) return;
    let parsed: T;
    try {
      parsed = parseLosslessJson(event.data) as T;
    } catch (cause) {
      setStatus('error');
      options.onParseError?.(
        cause instanceof Error
          ? cause
          : new Error('Live event frame could not be parsed', { cause }),
      );
      return;
    }
    // A well-formed frame proves the application protocol recovered even when
    // EventSource did not need a transport reconnect. Consumer exceptions are
    // deliberately outside the parse guard and retain their own identity.
    if (status === 'error') setStatus('open');
    options.onEvent(parsed);
  };
  source.onerror = (event) => {
    if (closed) return;
    if (source.readyState === source.CLOSED) {
      closed = true;
      setStatus('closed');
    } else {
      setStatus('reconnecting');
    }
    options.onDisconnected?.(event);
  };

  return {
    close() {
      if (closed) return;
      closed = true;
      source.close();
      setStatus('closed');
    },
  };
}
