import { describe, expect, it, vi } from 'vitest';
import {
  LIVE_EVENTS_PATH,
  openLiveEventStream,
  type EventStreamStatus,
} from './events';

function fakeEventSource() {
  const instance = {
    url: '',
    init: undefined as EventSourceInit | undefined,
    onopen: null as ((event: Event) => void) | null,
    onmessage: null as ((event: MessageEvent) => void) | null,
    onerror: null as ((event: Event) => void) | null,
    close: vi.fn(),
  };
  const EventSourceClass = vi.fn(function (
    url: string,
    init?: EventSourceInit,
  ) {
    instance.url = url;
    instance.init = init;
    return instance;
  });
  return {
    instance,
    EventSourceClass: EventSourceClass as unknown as typeof EventSource,
  };
}

describe('SSE contract', () => {
  it('uses credentialed EventSource, reports state, and parses oversized ids losslessly', () => {
    const received = vi.fn();
    const statuses: EventStreamStatus[] = [];
    const disconnected = vi.fn();
    const { instance, EventSourceClass } = fakeEventSource();

    const stream = openLiveEventStream({
      onEvent: received,
      onDisconnected: disconnected,
      onStatusChange: (status) => statuses.push(status),
      eventSource: EventSourceClass,
    });

    expect(instance).toMatchObject({
      url: LIVE_EVENTS_PATH,
      init: { withCredentials: true },
    });
    expect(statuses).toEqual(['connecting']);

    instance.onopen?.(new Event('open'));
    instance.onmessage?.(
      new MessageEvent('message', { data: '{"id64":18446744073709551615}' }),
    );
    instance.onerror?.(new Event('error'));

    expect(received).toHaveBeenCalledWith({ id64: '18446744073709551615' });
    expect(disconnected).toHaveBeenCalledOnce();
    expect(statuses).toEqual(['connecting', 'open', 'reconnecting']);

    stream.close();
    stream.close();
    expect(instance.close).toHaveBeenCalledOnce();
    expect(statuses).toEqual([
      'connecting',
      'open',
      'reconnecting',
      'closed',
    ]);
  });

  it('reports and ignores malformed frames without terminating the stream', () => {
    const received = vi.fn();
    const parseError = vi.fn();
    const { instance, EventSourceClass } = fakeEventSource();

    const stream = openLiveEventStream({
      onEvent: received,
      onParseError: parseError,
      eventSource: EventSourceClass,
    });

    expect(() =>
      instance.onmessage?.(
        new MessageEvent('message', { data: '{not-valid-json' }),
      ),
    ).not.toThrow();
    expect(received).not.toHaveBeenCalled();
    expect(parseError).toHaveBeenCalledOnce();
    expect(parseError.mock.calls[0]?.[0]).toBeInstanceOf(Error);

    instance.onmessage?.(
      new MessageEvent('message', { data: '{"id64":9007199254740993}' }),
    );
    expect(received).toHaveBeenCalledWith({ id64: '9007199254740993' });

    stream.close();
    instance.onmessage?.(
      new MessageEvent('message', { data: '{"id64":42}' }),
    );
    expect(received).toHaveBeenCalledTimes(1);
  });
});
