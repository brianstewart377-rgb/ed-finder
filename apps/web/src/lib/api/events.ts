import { parseLosslessJson } from './lossless-json';

export const LIVE_EVENTS_PATH = '/api/events/live';

export interface EventStreamContract {
  close(): void;
}

export interface EventStreamOptions<T> {
  onEvent(event: T): void;
  onOpen?(): void;
  /** Native EventSource reconnects. Consumers may start bounded polling here. */
  onDisconnected?(event: Event): void;
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
  const source = new EventSourceClass(LIVE_EVENTS_PATH, {
    withCredentials: true,
  });
  source.onopen = () => options.onOpen?.();
  source.onmessage = (event) =>
    options.onEvent(parseLosslessJson(event.data) as T);
  source.onerror = (event) => options.onDisconnected?.(event);
  return { close: () => source.close() };
}
