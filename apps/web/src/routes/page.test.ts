import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import TestShell from '$lib/components/TestShell.svelte';
import { getAuthSession, getHealth } from '$lib/api/client';

vi.mock('$lib/api/client', () => ({
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
      screen.getByRole('heading', { name: /find your place/i }),
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
  });
  it('reports failed bootstrap requests without hiding the shell', async () => {
    mockedGetHealth.mockRejectedValue(new Error('Request failed (503)'));
    mockedGetAuthSession.mockRejectedValue(new Error('Request failed (503)'));
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByText('Unavailable')).toHaveLength(2),
    );
    expect(
      screen.getByRole('navigation', { name: 'Product journey' }),
    ).toBeInTheDocument();
  });
});
