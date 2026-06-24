import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

const SYNC_KEY = 'finderwatchlistkey0000000001';

function mockFetch(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => body,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api watchlist', () => {
  it('loads the scoped v2 watchlist with the persisted sync key', async () => {
    const fetchMock = mockFetch({ sync_key: SYNC_KEY, watchlist: [] });

    await api.watchlist(SYNC_KEY);

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v2/watchlist/${SYNC_KEY}`,
      expect.objectContaining({
        headers: expect.objectContaining({ Accept: 'application/json' }),
      }),
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty('method');
  });

  it('adds and removes systems through scoped v2 watchlist endpoints', async () => {
    const fetchMock = mockFetch({ ok: true, sync_key: SYNC_KEY });

    await api.watchAdd(SYNC_KEY, 123);
    await api.watchRemove(SYNC_KEY, 123);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `/api/v2/watchlist/${SYNC_KEY}/123`,
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/v2/watchlist/${SYNC_KEY}/123`,
      expect.objectContaining({ method: 'DELETE' }),
    );
  });
});
