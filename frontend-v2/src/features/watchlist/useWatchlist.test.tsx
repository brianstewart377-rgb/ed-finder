import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type WatchlistEntry } from '@/lib/api';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import { useWatchlist } from './useWatchlist';

const SYNC_KEY = 'finderwatchlistkey0000000001';

const entry: WatchlistEntry = {
  system_id64: 123,
  name: 'Inspection Candidate',
  x: 1,
  y: 2,
  z: 3,
  population: 1000,
  is_colonised: false,
  added_at: '2026-06-24T00:00:00.000Z',
  score: 87,
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
  useSyncKeyStore.getState().setKey(SYNC_KEY);
  vi.restoreAllMocks();
});

describe('useWatchlist', () => {
  it('loads saved systems through the scoped sync-key watchlist path', async () => {
    const watchlistSpy = vi.spyOn(api, 'watchlist').mockResolvedValue({
      sync_key: SYNC_KEY,
      watchlist: [entry],
    });

    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(watchlistSpy).toHaveBeenCalledWith(SYNC_KEY);
    expect(result.current.has(123)).toBe(true);
    expect(result.current.entries[0].name).toBe('Inspection Candidate');
  });

  it('adds and removes systems with the same persisted sync key', async () => {
    vi.spyOn(api, 'watchlist').mockResolvedValue({
      sync_key: SYNC_KEY,
      watchlist: [],
    });
    const addSpy = vi.spyOn(api, 'watchAdd').mockResolvedValue({ ok: true, sync_key: SYNC_KEY });
    const removeSpy = vi.spyOn(api, 'watchRemove').mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useWatchlist(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.add(123, entry);
      await result.current.remove(123);
    });

    expect(addSpy).toHaveBeenCalledWith(SYNC_KEY, 123);
    expect(removeSpy).toHaveBeenCalledWith(SYNC_KEY, 123);
  });
});
