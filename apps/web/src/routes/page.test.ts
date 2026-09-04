import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import TestShell from '$lib/components/TestShell.svelte';
import { autocomplete, getWatchlist, localSearch } from '$lib/api/client';
vi.mock('$lib/api/client', () => ({
  autocomplete: vi.fn(),
  getWatchlist: vi.fn(),
  localSearch: vi.fn(),
  clusterSearch: vi.fn(),
  addWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
  ApiError: class extends Error {
    status = 500;
  },
}));
describe('Finder vertical', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    vi.mocked(getWatchlist).mockResolvedValue({ watchlist: [] });
  });
  afterEach(cleanup);
  it('renders the accessible Finder and searches', async () => {
    vi.mocked(localSearch).mockResolvedValue({
      count: 1,
      total: 1,
      results: [{ id64: '9223372036854775807', name: 'Far Reach' }],
    });
    render(TestShell);
    expect(
      screen.getByRole('heading', { name: /system finder/i }),
    ).toBeInTheDocument();
    await fireEvent.click(screen.getByTestId('search-submit'));
    await waitFor(() =>
      expect(screen.getByText('Far Reach')).toBeInTheDocument(),
    );
    expect(screen.getByText(/9223372036854775807/)).toBeInTheDocument();
  });
  it('supports keyboard autocomplete selection', async () => {
    vi.useFakeTimers();
    vi.mocked(autocomplete).mockResolvedValue({
      results: [{ id64: '1', name: 'Solitude', x: 1, y: 2, z: 3 }],
    });
    render(TestShell);
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'Sol' } });
    await vi.advanceTimersByTimeAsync(210);
    await vi.runAllTimersAsync();
    expect(screen.getByRole('option')).toBeInTheDocument();
    await fireEvent.keyDown(input, { key: 'ArrowDown' });
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue('Solitude');
    vi.useRealTimers();
  });
});
