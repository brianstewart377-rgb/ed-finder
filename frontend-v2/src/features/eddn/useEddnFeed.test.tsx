import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEddnFeed } from './useEddnFeed';

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  emit(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }

  fail() {
    this.onerror?.(new Event('error'));
  }
}

function FeedHarness() {
  const { events, error } = useEddnFeed({ useSse: true, flushMs: 1 });
  return (
    <div>
      <div data-testid="error">{error ?? 'no-error'}</div>
      <div data-testid="count">{events.length}</div>
      {events.map((event) => <div key={event.id64}>{event.system_name}</div>)}
    </div>
  );
}

describe('useEddnFeed', () => {
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    globalThis.EventSource = originalEventSource;
  });

  it('clears a stale SSE connection error after a valid recovered event', () => {
    render(<FeedHarness />);
    const source = MockEventSource.instances[0];

    act(() => {
      source.fail();
    });

    expect(screen.getByTestId('error').textContent).toContain('SSE connection interrupted');

    act(() => {
      source.emit('heartbeat');
    });

    expect(screen.getByTestId('error').textContent).toContain('SSE connection interrupted');

    act(() => {
      source.emit(JSON.stringify({
        system_name: 'Recovered System',
        id64: 42,
        type: 'Scan',
        timestamp: '2026-05-16T00:00:00Z',
      }));
    });

    expect(screen.getByTestId('error').textContent).toBe('no-error');

    act(() => {
      vi.advanceTimersByTime(2);
    });

    expect(screen.getByText('Recovered System')).toBeTruthy();
    expect(screen.getByTestId('count').textContent).toBe('1');
  });
});
