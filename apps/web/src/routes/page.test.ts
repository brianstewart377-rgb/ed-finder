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
  });
  afterEach(cleanup);
  it('renders accessible journey navigation and guest status', async () => {
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
      screen.getByText(
        'Explore freely. Sign in with Frontier when you need your commander account.',
      ),
    ).toBeInTheDocument();
  });
  it('preserves the hero actions followed by exactly three journey cards', () => {
    renderPage();
    const main = screen.getByRole('main');
    const primary = within(main).getByRole('link', {
      name: 'Explore the galaxy',
    });
    const secondary = within(main).getByRole('link', {
      name: 'Inspect a system',
    });
    expect(primary).toHaveAttribute('href', '/explore');
    expect(secondary).toHaveAttribute('href', '/inspect');

    const tools = screen.getByRole('region', {
      name: 'A galaxy of possibilities.',
    });
    const cards = Array.from(
      tools.querySelectorAll<HTMLAnchorElement>('.tool-card'),
    );
    expect(cards).toHaveLength(3);
    const journey = [
      { label: 'Explore', href: '/explore' },
      { label: 'Inspect', href: '/inspect' },
      { label: 'Plan', href: '/plan' },
    ];
    journey.forEach(({ label, href }, index) => {
      expect(cards[index]).toHaveAttribute('href', href);
      expect(
        within(cards[index]).getByRole('heading', {
          name: label,
          level: 3,
        }),
      ).toBeInTheDocument();
    });
    expect(within(main).getAllByRole('link').slice(0, 5)).toEqual([
      primary,
      secondary,
      ...cards,
    ]);
    for (const link of [primary, secondary, ...cards]) {
      expect(link).not.toHaveAttribute('tabindex');
    }
  });
  it('keeps the decorative compass and orbits out of the accessible content', () => {
    renderPage();
    const main = screen.getByRole('main');
    const art = main.querySelector('.galaxy-motif');
    expect(art).toHaveAttribute('aria-hidden', 'true');
    expect(art?.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(
      art?.querySelectorAll('a, button, input, select, textarea, [tabindex]'),
    ).toHaveLength(0);
    expect(within(main).queryByRole('img')).not.toBeInTheDocument();
  });
  it('points review and export to Plan without introducing a fourth tool', () => {
    renderPage();
    const tools = screen.getByRole('region', {
      name: 'A galaxy of possibilities.',
    });
    const availability = within(tools).getByRole('link', {
      name: 'Available in Plan',
    });
    expect(availability).toHaveAttribute('href', '/plan');
    expect(availability.closest('.tool-card')).toBeNull();
    expect(availability.parentElement).toHaveTextContent('Review & export');
    expect(within(tools).getAllByRole('link')).toHaveLength(4);
    expect(within(tools).getAllByRole('heading', { level: 3 })).toHaveLength(3);
    expect(screen.queryByText('Coming later')).not.toBeInTheDocument();
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
