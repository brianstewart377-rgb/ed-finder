import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { useEddnFeed } from './useEddnFeed';

vi.mock('@/lib/api', () => ({
  api: {
    recentEvents: vi.fn(),
  },
}));

const mockedRecentEvents = vi.mocked(api.recentEvents);

describe('useEddnFeed', () => {
  beforeEach(() => {
    mockedRecentEvents.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('falls back to recent-events polling and reports live status when events arrive', async () => {
    mockedRecentEvents.mockResolvedValue({
      events: [{
        id64: 42,
        system_name: 'Fallback System',
        type: 'Scan',
        timestamp: new Date().toISOString(),
      }],
      jobs: {},
    });

    const { result } = renderHook(() => useEddnFeed({ preferSse: false, intervalMs: 20, flushMs: 5 }));

    await waitFor(() => {
      expect(result.current.status).toBe('live');
    }, { timeout: 1200 });
    expect(result.current.events[0]?.system_name).toBe('Fallback System');
  });

  it('ignores malformed event payloads without crashing', async () => {
    mockedRecentEvents
      .mockResolvedValueOnce({ events: [{ bad: 'payload' }] as unknown as { id64: number; system_name: string; type: string; timestamp: string | null }[], jobs: {} })
      .mockResolvedValueOnce({
        events: [{
          id64: 84,
          system_name: 'Valid System',
          type: 'FSDJump',
          timestamp: new Date().toISOString(),
        }],
        jobs: {},
      });

    const { result } = renderHook(() => useEddnFeed({ preferSse: false, intervalMs: 20, flushMs: 5 }));

    await waitFor(() => {
      expect(result.current.events).toHaveLength(0);
    }, { timeout: 1200 });

    await waitFor(() => {
      expect(result.current.events.some((event) => event.system_name === 'Valid System')).toBe(true);
    }, { timeout: 1200 });
    expect(['live', 'reconnecting']).toContain(result.current.status);
  });

  it('surfaces offline status when fallback polling fails and no events are available', async () => {
    mockedRecentEvents.mockRejectedValue(new Error('network unavailable'));

    const { result } = renderHook(() => useEddnFeed({ preferSse: false, intervalMs: 20, flushMs: 5 }));

    await waitFor(() => {
      expect(result.current.status).toBe('offline');
    }, { timeout: 1200 });
    expect(result.current.error).toBe('offline');
  });
});
