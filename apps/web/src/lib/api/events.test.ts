import { describe, expect, it, vi } from 'vitest';
import { LIVE_EVENTS_PATH, openLiveEventStream } from './events';

describe('SSE contract', () => {
  it('uses credentialed EventSource and parses oversized ids losslessly', () => {
    const received = vi.fn();
    const instance = {
      url: '',
      init: undefined as EventSourceInit | undefined,
      onopen: null as ((event: Event) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      close: vi.fn(),
    };
    const FakeEventSource = vi.fn(function (
      url: string,
      init?: EventSourceInit,
    ) {
      instance.url = url;
      instance.init = init;
      return instance;
    });
    const stream = openLiveEventStream({
      onEvent: received,
      eventSource: FakeEventSource as unknown as typeof EventSource,
    });
    expect(instance).toMatchObject({
      url: LIVE_EVENTS_PATH,
      init: { withCredentials: true },
    });
    instance.onmessage?.(
      new MessageEvent('message', { data: '{"id64":18446744073709551615}' }),
    );
    expect(received).toHaveBeenCalledWith({ id64: '18446744073709551615' });
    stream.close();
    expect(instance.close).toHaveBeenCalled();
  });
});
