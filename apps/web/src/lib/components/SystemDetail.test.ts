import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getSystem } from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import { parseId64 } from '$lib/domain/id64';
import SystemDetailTestHost from './SystemDetailTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return { ...original, getSystem: vi.fn() };
});

const mockedGetSystem = vi.mocked(getSystem);

describe('shared system detail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });
  afterEach(cleanup);

  it('renders typed catalogue fields with an exact unsafe id64', async () => {
    const id64 = parseId64('18446744073709551615');
    mockedGetSystem.mockResolvedValue({
      id64,
      name: 'Edge of Address Space',
      x: 1,
      y: 2,
      z: 3,
      population: 12_345,
      primary_economy: 'HighTech',
      security: 'High',
      bodies: [],
      stations: [],
    });

    render(SystemDetailTestHost, { props: { id64 } });

    expect(
      await screen.findByRole('heading', { name: 'Edge of Address Space' }),
    ).toBeInTheDocument();
    expect(screen.getByText('18446744073709551615')).toBeInTheDocument();
    expect(screen.getByText('1.00, 2.00, 3.00 ly')).toBeInTheDocument();
    expect(screen.getByText('12,345')).toBeInTheDocument();
  });

  it('distinguishes not-found and retries other API errors', async () => {
    const id64 = parseId64('42');
    mockedGetSystem.mockRejectedValueOnce(
      new ApiError(404, '/api/system/42', {}),
    );
    const first = render(SystemDetailTestHost, { props: { id64 } });
    expect(
      await screen.findByRole('heading', { name: 'System not found' }),
    ).toBeInTheDocument();
    first.unmount();

    mockedGetSystem
      .mockRejectedValueOnce(new ApiError(503, '/api/system/42', {}))
      .mockRejectedValueOnce(new ApiError(503, '/api/system/42', {}))
      .mockResolvedValueOnce({ id64, name: 'Recovered system' });
    render(SystemDetailTestHost, { props: { id64 } });
    expect(
      await screen.findByRole(
        'heading',
        { name: 'System detail unavailable' },
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Recovered system' }),
      ).toBeInTheDocument(),
    );
  });
});
