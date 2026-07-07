import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { useEliteNewsFeed } from './useEliteNewsFeed';

vi.mock('@/lib/api', () => ({
  api: {
    eliteNewsLatest: vi.fn(),
  },
}));

describe('useEliteNewsFeed', () => {
  beforeEach(() => {
    vi.mocked(api.eliteNewsLatest).mockReset();
  });

  it('clears stale items after a later poll fails', async () => {
    vi.mocked(api.eliteNewsLatest)
      .mockResolvedValueOnce({
        items: [{
          title: 'Live headline',
          url: 'https://www.elitedangerous.com/news/live-headline',
          source: 'news',
        }],
        stale: false,
        source_url: 'https://www.elitedangerous.com/news',
        fetched_at: '2026-07-07T00:00:00Z',
      })
      .mockRejectedValueOnce(new Error('offline'));

    const { result, unmount } = renderHook(() => useEliteNewsFeed({ intervalMs: 100, limit: 1 }));

    await waitFor(() => {
      expect(result.current.items).toHaveLength(1);
      expect(result.current.status).toBe('live');
    });

    await waitFor(() => {
      expect(api.eliteNewsLatest).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(result.current.status).toBe('offline');
      expect(result.current.items).toEqual([]);
    });

    unmount();
  });
});
