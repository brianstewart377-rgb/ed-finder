import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import TestShell from '$lib/components/TestShell.svelte';
import { getAuthSession, getHealth } from '$lib/api/client';
import {
  applicationStores,
  hydrateApplicationStores,
  resetApplicationStoreHydrationForTest,
} from '$lib/persistence/stores';

vi.mock('$lib/api/client', () => ({
  claimOwner: vi.fn(),
  frontierLoginUrl: vi.fn(() => '/api/auth/frontier/login'),
  getAuthSession: vi.fn(),
  getHealth: vi.fn(),
  authLogout: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);
const mockedGetAuthSession = vi.mocked(getAuthSession);

const renderPage = () => render(TestShell);

describe('ED-Finder V3 shell', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    resetApplicationStoreHydrationForTest();
  });
  afterEach(cleanup);
  it('renders accessible journey navigation and guest status', async () => {
    mockedGetHealth.mockResolvedValue({
      status: 'ok',
      database: 'connected',
      version: 'test',
      build_sha: 'abc',
    });
    mockedGetAuthSession.mockResolvedValue({
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    renderPage();
    expect(
      screen.getByRole('heading', { name: /finder/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Primary navigation' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Explore' })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('frontier-sign-in')).toBeInTheDocument(),
    );
  });
  it('reports failed bootstrap requests without hiding the shell', async () => {
    mockedGetHealth.mockRejectedValue(new Error('Request failed (503)'));
    mockedGetAuthSession.mockRejectedValue(new Error('Request failed (503)'));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('frontier-sign-in')).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('navigation', { name: 'Primary navigation' }),
    ).toBeInTheDocument();
  });
  it('hydrates legacy persisted state during boot before rendering its context', async () => {
    localStorage.setItem(
      'ed-finder:selected-system-context',
      '18446744073709551615',
    );
    mockedGetAuthSession.mockResolvedValue({
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('selected-system-context')).toHaveTextContent(
        '18446744073709551615',
      ),
    );
  });
  it('hydrates each singleton persistence service exactly once', () => {
    resetApplicationStoreHydrationForTest();
    const hydrateSpies = Object.values(applicationStores).map((store) =>
      vi.spyOn(store, 'hydrate'),
    );
    hydrateApplicationStores();
    hydrateApplicationStores();
    for (const hydrate of hydrateSpies)
      expect(hydrate).toHaveBeenCalledTimes(1);
  });
});
