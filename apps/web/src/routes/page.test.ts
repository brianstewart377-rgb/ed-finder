import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import TestShell from '$lib/components/TestShell.svelte';
import { getAuthSession, getHealth } from '$lib/api/client';

vi.mock('$lib/api/client', () => ({
  authLogout: vi.fn(),
  claimOwner: vi.fn(),
  frontierLoginUrl: vi.fn(() => '/api/auth/frontier/login'),
  getAuthSession: vi.fn(),
  getHealth: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);
const mockedGetAuthSession = vi.mocked(getAuthSession);

const renderPage = () => render(TestShell);

describe('ED-Finder V3 shell', () => {
  beforeEach(() => {
    vi.resetAllMocks();
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
      screen.getByRole('heading', { name: /search the galaxy/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Product journey' }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('link', { name: 'Explore' }).length,
    ).toBeGreaterThan(0);
    await waitFor(() =>
      expect(screen.getByText('Connected')).toBeInTheDocument(),
    );
    expect(screen.getByText('Guest')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Sign in with Frontier' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Explore the galaxy' }),
    ).toHaveAttribute('href', '/explore');
    const tools = within(
      screen.getByRole('region', { name: 'A galaxy of possibilities.' }),
    );
    expect(tools.getAllByRole('link')).toHaveLength(3);
    expect(
      tools.getByRole('link', {
        name: 'Plan Lay out a colony body by body, check construction points and economies, and import a Raven Colonial layout.',
      }),
    ).toHaveAttribute('href', '/plan');
    expect(screen.getAllByText('Coming later')).toHaveLength(1);
    expect(screen.getByText('Review & export')).toBeInTheDocument();
    expect(screen.queryByText('Colony planning')).not.toBeInTheDocument();
  });
  it('reports failed bootstrap requests without hiding the shell', async () => {
    mockedGetHealth.mockRejectedValue(new Error('Request failed (503)'));
    mockedGetAuthSession.mockRejectedValue(new Error('Request failed (503)'));
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByText('Unavailable')).toHaveLength(2),
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Product journey' }),
    ).toBeInTheDocument();
  });
});
