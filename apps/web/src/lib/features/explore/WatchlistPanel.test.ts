import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import {
  addWatchlist,
  getWatchlist,
  removeWatchlist,
  type WatchlistEntry,
} from '$lib/api/client';
import { queryClient, queryKeys } from '$lib/api/query';
import { parseId64 } from '$lib/domain/id64';
import type { AuthState } from '$lib/auth/auth';
import type { PersistenceContext } from '$lib/persistence/context';
import { applicationStores } from '$lib/persistence/stores';
import {
  createPersistedStore,
  compareCodec,
  pinnedCodec,
  syncKeyCodec,
  PERSISTENCE_KEYS,
} from '$lib/persistence/storage';
import WatchlistTestHost from './WatchlistTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => ({
  ...(await loadOriginal<typeof import('$lib/api/client')>()),
  getWatchlist: vi.fn(),
  addWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
}));
vi.mock('$lib/persistence/context', async (loadOriginal) => ({
  ...(await loadOriginal<typeof import('$lib/persistence/context')>()),
  usePersistenceContext: () => services,
}));
vi.mock('$lib/auth/auth', () => ({
  auth: {
    subscribe: (run: (value: AuthState) => void) => session.subscribe(run),
  },
}));

let services: PersistenceContext;
const signedOut: AuthState = {
  loading: false,
  authenticated: false,
  user: null,
  ownerClaimAvailable: false,
  error: null,
};
const session = writable<AuthState>(signedOut);
const id64 = parseId64('18446744073709551615');
const entry: WatchlistEntry = {
  system_id64: id64,
  name: 'Far Reach',
  added_at: '2026-09-01T12:00:00Z',
  x: 3,
  y: 4,
  z: 0,
  population: 1200,
  is_colonised: true,
  archetype_score: 72,
  primary_archetype: 'industrial',
  secondary_archetype: 'refinery',
  economy_suggestion: 'Industrial',
  score: 65,
};
const getMock = vi.mocked(getWatchlist);
const addMock = vi.mocked(addWatchlist);
const removeMock = vi.mocked(removeWatchlist);

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
  localStorage.clear();
  session.set(signedOut);
  services = {
    ...applicationStores,
    pins: createPersistedStore({
      key: PERSISTENCE_KEYS.pins,
      initial: () => [],
      codec: pinnedCodec,
    }),
    compare: createPersistedStore({
      key: PERSISTENCE_KEYS.compare,
      initial: () => [],
      codec: compareCodec,
    }),
    syncKey: createPersistedStore({
      key: PERSISTENCE_KEYS.syncKey,
      initial: () => ({
        state: { syncKey: 'commander-a-key-1234' },
        version: 0,
      }),
      codec: syncKeyCodec,
    }),
  };
  services.pins.hydrate();
  services.compare.hydrate();
  services.syncKey.hydrate();
  getMock.mockResolvedValue({
    sync_key: 'commander-a-key-1234',
    watchlist: [],
  });
  addMock.mockResolvedValue({ ok: true, sync_key: 'commander-a-key-1234' });
  removeMock.mockResolvedValue({ ok: true });
});
afterEach(() => {
  cleanup();
  queryClient.clear();
});

describe('saved systems panel', () => {
  it('explains the independent empty lists and sync-key ownership', async () => {
    render(WatchlistTestHost);
    expect(
      await screen.findByText('No systems watched yet'),
    ).toBeInTheDocument();
    expect(screen.getByText('No pinned systems yet')).toBeInTheDocument();
    expect(
      screen.getByText(/Pins and comparison selections stay in this browser/),
    ).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      'commander-a-key-1234',
      expect.any(AbortSignal),
    );
  });

  it('waits for credential hydration and reports loading without an empty flash', async () => {
    services.syncKey = createPersistedStore({
      key: PERSISTENCE_KEYS.syncKey,
      initial: () => ({
        state: { syncKey: 'commander-a-key-1234' },
        version: 0,
      }),
      codec: syncKeyCodec,
    });
    getMock.mockImplementation(() => new Promise(() => {}));
    render(WatchlistTestHost);
    expect(getMock).not.toHaveBeenCalled();
    expect(
      screen.queryByText('No systems watched yet'),
    ).not.toBeInTheDocument();
    services.syncKey.hydrate();
    expect(await screen.findByText('Loading watchlist…')).toBeInTheDocument();
    await waitFor(() => expect(getMock).toHaveBeenCalledOnce());
  });

  it('renders the V2 watchlist columns, safe inspect links, and comparison actions', async () => {
    getMock.mockResolvedValue({
      sync_key: 'commander-a-key-1234',
      watchlist: [entry],
    });
    render(WatchlistTestHost);
    const table = await screen.findByRole('table', { name: 'Watched systems' });
    for (const name of [
      'System',
      'Coords (LY)',
      'Population',
      'Development',
      'Archetype',
      'Added',
    ]) {
      expect(
        within(table).getByRole('columnheader', { name }),
      ).toBeInTheDocument();
    }
    expect(within(table).getByText('1,200')).toBeInTheDocument();
    expect(within(table).getByText('72')).toBeInTheDocument();
    expect(within(table).getByText('5.0 ly from Sol')).toBeInTheDocument();
    expect(
      within(table).getByRole('link', { name: 'Inspect Far Reach' }),
    ).toHaveAttribute('href', `/inspect?system=${id64}`);
    await fireEvent.click(
      within(table).getByRole('button', { name: 'Compare Far Reach' }),
    );
    expect(services.compare.read().value[0]).toMatchObject({
      id64,
      name: 'Far Reach',
      archetype_score: 72,
    });
    expect(
      within(table).getByRole('button', { name: 'Compare Far Reach' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await fireEvent.click(
      within(table).getByRole('button', { name: 'Pin Far Reach' }),
    );
    expect(services.pins.read().value[0]).toMatchObject({
      id64,
      name: 'Far Reach',
    });
  });

  it('renders pin snapshots, adds them to the watchlist, removes them, and exports exact IDs', async () => {
    services.pins.set([
      {
        id64,
        name: 'Far Reach',
        pinned_at: '2026-09-01T12:00:00Z',
        x: 3,
        y: 4,
        z: 0,
        archetype_score: 72,
        primary_archetype: 'industrial',
        distance: 12.5,
      },
    ]);
    render(WatchlistTestHost);
    await screen.findByText('No systems watched yet');
    const table = screen.getByRole('table', { name: 'Pinned systems' });
    expect(
      within(table).getByRole('columnheader', { name: 'Dist. from ref.' }),
    ).toBeInTheDocument();
    expect(within(table).getByText('12.5 ly')).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'Spansh' })).toHaveAttribute(
      'href',
      `https://spansh.co.uk/system/${id64}`,
    );
    const exportLink = screen.getByRole('link', {
      name: 'Export pins as JSON',
    });
    expect(
      JSON.parse(
        decodeURIComponent(exportLink.getAttribute('href')!.split(',')[1]),
      )[0].id64,
    ).toBe(id64);
    getMock.mockResolvedValue({
      sync_key: 'commander-a-key-1234',
      watchlist: [entry],
    });
    await fireEvent.click(
      within(table).getByRole('button', { name: 'Watch Far Reach' }),
    );
    await waitFor(() =>
      expect(addMock).toHaveBeenCalledWith('commander-a-key-1234', id64),
    );
    await screen.findByRole('table', { name: 'Watched systems' });
    await fireEvent.click(
      within(table).getByRole('button', { name: 'Unpin Far Reach' }),
    );
    expect(services.pins.read().value).toEqual([]);
  });

  it('removes a watched system and refreshes only its captured cache scope', async () => {
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockResolvedValue({ sync_key: 'commander-a-key-1234', watchlist: [] });
    render(WatchlistTestHost);
    await fireEvent.click(
      await screen.findByRole('button', {
        name: 'Remove Far Reach from watchlist',
      }),
    );
    await waitFor(() =>
      expect(removeMock).toHaveBeenCalledWith('commander-a-key-1234', id64),
    );
    expect(
      await screen.findByText('No systems watched yet'),
    ).toBeInTheDocument();
    expect(
      queryClient.getQueryData(
        queryKeys.watchlist(null, 'commander-a-key-1234'),
      ),
    ).toMatchObject({ watchlist: [] });
  });

  it('shows a retryable error without exposing backend text or credentials', async () => {
    getMock
      .mockRejectedValueOnce(
        new Error('private commander-a-key-1234 /api/watchlist'),
      )
      .mockResolvedValue({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      });
    render(WatchlistTestHost);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your watchlist could not be loaded. Try again.',
    );
    expect(
      screen.queryByText(/private commander-a-key-1234/),
    ).not.toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Retry watchlist' }),
    );
    expect(
      await screen.findByRole('table', { name: 'Watched systems' }),
    ).toBeInTheDocument();
  });

  it('switches account caches without showing the previous account list', async () => {
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockResolvedValue({ sync_key: 'commander-a-key-1234', watchlist: [] });
    render(WatchlistTestHost);
    await screen.findByRole('table', { name: 'Watched systems' });
    session.set({
      ...signedOut,
      authenticated: true,
      user: {
        account_id: 'another-account',
        commander_name: null,
        is_owner: false,
      },
    });
    expect(
      await screen.findByText('No systems watched yet'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('table', { name: 'Watched systems' }),
    ).not.toBeInTheDocument();
    expect(
      queryClient.getQueryData(
        queryKeys.watchlist('another-account', 'commander-a-key-1234'),
      ),
    ).toMatchObject({ watchlist: [] });
  });

  it('sorts watchlist rows by name, development, distance, and recently added', async () => {
    const second = {
      ...entry,
      system_id64: parseId64('42'),
      name: 'Achenar',
      archetype_score: 90,
      x: 12,
      y: 0,
      z: 0,
      added_at: '2026-09-02T12:00:00Z',
    };
    getMock.mockResolvedValue({
      sync_key: 'commander-a-key-1234',
      watchlist: [entry, second],
    });
    render(WatchlistTestHost);
    const table = await screen.findByRole('table', { name: 'Watched systems' });
    const firstRowName = () =>
      within(table).getAllByRole('rowheader')[0].textContent;
    expect(firstRowName()).toContain('Achenar');
    const sort = screen.getByRole('combobox', { name: 'Sort watchlist' });
    await fireEvent.change(sort, { target: { value: 'distance' } });
    expect(firstRowName()).toContain('Far Reach');
    await fireEvent.change(sort, { target: { value: 'name' } });
    expect(firstRowName()).toContain('Achenar');
    await fireEvent.change(sort, { target: { value: 'development' } });
    expect(firstRowName()).toContain('Achenar');
  });

  it('keeps saved rows visible after a refresh fails', async () => {
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockRejectedValue(new Error('unavailable'));
    render(WatchlistTestHost);
    await screen.findByRole('table', { name: 'Watched systems' });
    await fireEvent.click(
      screen.getByRole('button', { name: 'Refresh watchlist' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your watchlist could not be loaded. Try again.',
    );
    expect(
      screen.getByRole('table', { name: 'Watched systems' }),
    ).toBeInTheDocument();
  });

  it('retries a failed mutation while retaining the watched system', async () => {
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockResolvedValue({ sync_key: 'commander-a-key-1234', watchlist: [] });
    removeMock
      .mockRejectedValueOnce(new Error('private credential'))
      .mockResolvedValue({ ok: true });
    render(WatchlistTestHost);
    await fireEvent.click(
      await screen.findByRole('button', {
        name: 'Remove Far Reach from watchlist',
      }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your watchlist could not be updated. Try again.',
    );
    expect(
      screen.getByRole('table', { name: 'Watched systems' }),
    ).toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Retry watchlist change' }),
    );
    expect(
      await screen.findByText('No systems watched yet'),
    ).toBeInTheDocument();
    expect(removeMock).toHaveBeenCalledTimes(2);
  });

  it('retries loading without repeating an earlier failed removal', async () => {
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockRejectedValueOnce(new Error('load failed'))
      .mockResolvedValue({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      });
    removeMock.mockRejectedValue(new Error('remove failed'));
    render(WatchlistTestHost);
    await fireEvent.click(
      await screen.findByRole('button', {
        name: 'Remove Far Reach from watchlist',
      }),
    );
    await screen.findByRole('button', { name: 'Retry watchlist change' });
    await fireEvent.click(
      screen.getByRole('button', { name: 'Refresh watchlist' }),
    );
    await fireEvent.click(
      await screen.findByRole('button', {
        name: 'Retry watchlist',
      }),
    );
    await waitFor(() =>
      expect(
        screen.queryByText('Your watchlist could not be loaded. Try again.'),
      ).not.toBeInTheDocument(),
    );
    expect(removeMock).toHaveBeenCalledOnce();
  });

  it('does not expose an old mutation error after switching the sync key', async () => {
    let rejectRemove!: (error: Error) => void;
    removeMock.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectRemove = reject;
        }),
    );
    getMock
      .mockResolvedValueOnce({
        sync_key: 'commander-a-key-1234',
        watchlist: [entry],
      })
      .mockResolvedValue({ sync_key: 'commander-b-key-1234', watchlist: [] });
    render(WatchlistTestHost);
    await fireEvent.click(
      await screen.findByRole('button', {
        name: 'Remove Far Reach from watchlist',
      }),
    );
    await waitFor(() => expect(removeMock).toHaveBeenCalledOnce());
    services.syncKey.set({
      state: { syncKey: 'commander-b-key-1234' },
      version: 0,
    });
    await screen.findByText('No systems watched yet');
    rejectRemove(new Error('late private failure'));
    await waitFor(() => expect(queryClient.isMutating()).toBe(0));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(
      queryClient.getQueryData(
        queryKeys.watchlist(null, 'commander-b-key-1234'),
      ),
    ).toMatchObject({ watchlist: [] });
  });

  it('retains the original credential when an inactive cached query is refetched', async () => {
    getMock.mockImplementation(async (key) => ({
      sync_key: key,
      watchlist: [],
    }));
    render(WatchlistTestHost);
    await screen.findByText('No systems watched yet');
    services.syncKey.set({
      state: { syncKey: 'commander-b-key-1234' },
      version: 0,
    });
    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(
        'commander-b-key-1234',
        expect.any(AbortSignal),
      ),
    );
    await queryClient.refetchQueries({
      queryKey: queryKeys.watchlist(null, 'commander-a-key-1234'),
      exact: true,
      type: 'inactive',
    });
    expect(getMock).toHaveBeenLastCalledWith(
      'commander-a-key-1234',
      expect.any(AbortSignal),
    );
    expect(
      queryClient.getQueryData(
        queryKeys.watchlist(null, 'commander-a-key-1234'),
      ),
    ).toMatchObject({ sync_key: 'commander-a-key-1234' });
  });

  it('waits for the session bootstrap before requesting an account-scoped list', async () => {
    session.set({ ...signedOut, loading: true });
    render(WatchlistTestHost);
    expect(getMock).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'Refresh watchlist' }),
    ).toBeDisabled();
    session.set({
      ...signedOut,
      authenticated: true,
      user: { account_id: 'captain', commander_name: null, is_owner: false },
    });
    await screen.findByText('No systems watched yet');
    expect(
      queryClient.getQueryData(
        queryKeys.watchlist('captain', 'commander-a-key-1234'),
      ),
    ).toMatchObject({ watchlist: [] });
  });

  it('confirms clearing local pins without removing the server watchlist', async () => {
    services.pins.set([
      { id64, name: 'Far Reach', pinned_at: '2026-09-01T12:00:00Z' },
    ]);
    render(WatchlistTestHost);
    await screen.findByText('No systems watched yet');
    await fireEvent.click(
      screen.getByRole('button', { name: 'Clear all pins' }),
    );
    expect(services.pins.read().value).toHaveLength(1);
    await fireEvent.click(
      screen.getByRole('button', { name: 'Confirm clear pins' }),
    );
    expect(services.pins.read().value).toEqual([]);
    expect(removeMock).not.toHaveBeenCalled();
  });

  it('reports pins that could not be restored without exposing stored content', async () => {
    localStorage.setItem(PERSISTENCE_KEYS.pins, 'corrupt private snapshot');
    services.pins = createPersistedStore({
      key: PERSISTENCE_KEYS.pins,
      initial: () => [],
      codec: pinnedCodec,
    });
    services.pins.hydrate();
    render(WatchlistTestHost);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your pins could not be saved or restored in this browser.',
    );
    expect(
      screen.queryByText(/corrupt private snapshot/),
    ).not.toBeInTheDocument();
  });
});
