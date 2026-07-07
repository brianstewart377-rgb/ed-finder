import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import { useWatchlist } from './useWatchlist';
import type { WatchlistEntry } from '@/lib/api';

const SYNC_KEY = 'reviewwatchlistkey000000000000';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createTestClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function WatchlistProbe({ id64 = 777 }: { id64?: number }) {
  const watchlist = useWatchlist();

  return (
    <div>
      <div data-testid="watchlist-loading">{watchlist.loading ? 'loading' : 'settled'}</div>
      <div data-testid="watchlist-membership">{watchlist.has(id64) ? 'saved' : 'unsaved'}</div>
      <div data-testid="watchlist-count">{watchlist.entries.length}</div>
      <button
        type="button"
        onClick={() => void watchlist.add(id64, { name: 'Finder Candidate', score: 88 })}
      >
        Save
      </button>
      <button
        type="button"
        onClick={() => void watchlist.remove(id64)}
      >
        Remove
      </button>
    </div>
  );
}

function renderProbe(id64 = 777) {
  const client = createTestClient();
  return render(
    <QueryClientProvider client={client}>
      <WatchlistProbe id64={id64} />
    </QueryClientProvider>,
  );
}

function expectNoRetiredWatchlistCalls(fetchMock: ReturnType<typeof vi.fn>) {
  const urls = fetchMock.mock.calls.map(([url]) => String(url));
  expect(urls).not.toContain('/api/watchlist');
  expect(urls.some((url) => url.startsWith('/api/watchlist/'))).toBe(false);
}

const savedEntry: WatchlistEntry = {
  system_id64: 777,
  name: 'Finder Candidate',
  x: 10,
  y: 20,
  z: 30,
  population: 0,
  is_colonised: false,
  added_at: '2026-06-25T00:00:00.000Z',
  score: 88,
};

describe('useWatchlist scoped membership', () => {
  beforeEach(() => {
    localStorage.clear();
    useSyncKeyStore.setState({ syncKey: SYNC_KEY });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads a fresh scoped Watchlist as unsaved', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ sync_key: SYNC_KEY, watchlist: [] }));
    vi.stubGlobal('fetch', fetchMock);

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-loading').textContent).toBe('settled');
    });

    expect(screen.getByTestId('watchlist-membership').textContent).toBe('unsaved');
    expect(screen.getByTestId('watchlist-count').textContent).toBe('0');
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v2/watchlist/${SYNC_KEY}`,
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expectNoRetiredWatchlistCalls(fetchMock);
  });

  it('keeps a first save unsaved until the add request succeeds', async () => {
    const saveRequest = deferred<Response>();
    let serverEntries: WatchlistEntry[] = [];
    const fetchMock = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'POST') return saveRequest.promise;
      return Promise.resolve(jsonResponse({ sync_key: SYNC_KEY, watchlist: serverEntries }));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-membership').textContent).toBe('unsaved');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/v2/watchlist/${SYNC_KEY}/777`,
        expect.objectContaining({ method: 'POST' }),
      );
    });
    expect(screen.getByTestId('watchlist-membership').textContent).toBe('unsaved');

    await act(async () => {
      serverEntries = [savedEntry];
      saveRequest.resolve(jsonResponse({ ok: true, sync_key: SYNC_KEY }));
      await saveRequest.promise;
    });

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-membership').textContent).toBe('saved');
    });
    expectNoRetiredWatchlistCalls(fetchMock);
  });

  it('loads an existing scoped entry and reconciles remove 404 to unsaved', async () => {
    let serverEntries: WatchlistEntry[] = [savedEntry];
    const fetchMock = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'DELETE') {
        serverEntries = [];
        return Promise.resolve(jsonResponse({ detail: 'Not Found' }, 404));
      }
      return Promise.resolve(jsonResponse({ sync_key: SYNC_KEY, watchlist: serverEntries }));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-membership').textContent).toBe('saved');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-membership').textContent).toBe('unsaved');
    });
    expect(screen.getByTestId('watchlist-count').textContent).toBe('0');
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v2/watchlist/${SYNC_KEY}/777`,
      expect.objectContaining({ method: 'DELETE' }),
    );
    expectNoRetiredWatchlistCalls(fetchMock);
  });
});
