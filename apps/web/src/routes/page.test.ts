import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import TestShell from '$lib/components/TestShell.svelte';

const renderPage = () => render(TestShell);

describe('ED-Finder V3 shell', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(cleanup);
  it('renders accessible journey navigation and guest status', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes('health') ? { status: 'ok', database: 'connected', version: 'test', build_sha: 'abc' } : { authenticated: false, user: null, owner_claim_available: false }), { status: 200 }))));
    renderPage();
    expect(screen.getByRole('heading', { name: /find your place/i })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Product journey' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Explore' }).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText('Connected')).toBeInTheDocument());
    expect(screen.getByText('Guest')).toBeInTheDocument();
  });
  it('reports failed bootstrap requests without hiding the shell', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(null, { status: 503 }))));
    renderPage();
    await waitFor(() => expect(screen.getAllByText('Unavailable')).toHaveLength(2));
    expect(screen.getByRole('navigation', { name: 'Product journey' })).toBeInTheDocument();
  });
});
