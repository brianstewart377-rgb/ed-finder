import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getSystem } from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import { referenceSystemDetail } from '$lib/api/v3-system-fixtures';
import { parseId64 } from '$lib/domain/id64';
import SystemDetailTestHost from './SystemDetailTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return { ...original, getSystem: vi.fn() };
});

const mockedGetSystem = vi.mocked(getSystem);

function detailValue(term: string): string | null {
  const dt = screen.getByText(term, { selector: 'dt' });
  return dt.parentElement?.querySelector('dd')?.textContent?.trim() ?? null;
}

describe('shared system detail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });
  afterEach(cleanup);

  it('renders V3 canonical fields with an exact unsafe id64', async () => {
    const id64 = parseId64('9007199254740993');
    mockedGetSystem.mockResolvedValue(
      referenceSystemDetail({
        id64: '9007199254740993',
        name: 'V3 Lossless Reach',
      }),
    );

    const { container } = render(SystemDetailTestHost, { props: { id64 } });

    expect(
      await screen.findByRole('heading', { name: 'V3 Lossless Reach' }),
    ).toBeInTheDocument();
    expect(screen.getByText('9007199254740993')).toBeInTheDocument();
    expect(detailValue('Coordinates')).toBe('1.00, 2.00, 3.00 ly');
    expect(detailValue('Main star')).toBe('G2 V');
    expect(detailValue('Bodies returned')).toBe('3');
    expect(detailValue('Stations returned')).toBe('1');
    expect(detailValue('Catalogue updated')).not.toBeNull();
    // Fields the V3 catalogue does not carry are explicit, never blank.
    const unavailable = container.querySelectorAll('[data-unavailable-fields]');
    expect(unavailable).toHaveLength(2);
    for (const row of unavailable)
      expect(within(row as HTMLElement).getByText('Not available yet'));
    expect(
      detailValue('Population, economy, security, allegiance, government'),
    ).toBe('Not available yet');
    expect(detailValue('Development fit')).toBe('Not available yet');
    expect(container.textContent).not.toMatch(/undefined|null|NaN/u);
  });

  it('labels a system that is no longer current in the catalogue', async () => {
    mockedGetSystem.mockResolvedValue(
      referenceSystemDetail({ lifecycle_state: 'RETIRED' }),
    );
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });
    await screen.findByRole('heading', { name: 'Reference System' });
    expect(detailValue('Catalogue status')).toBe('Retired from the catalogue');
  });

  it('flags an incomplete body catalogue but not a lagging source total', async () => {
    mockedGetSystem.mockResolvedValueOnce(
      referenceSystemDetail({ source_body_count: 5 }),
    );
    const first = render(SystemDetailTestHost, {
      props: { id64: parseId64('10477373803') },
    });
    await screen.findByRole('heading', { name: 'Reference System' });
    expect(detailValue('Bodies returned')).toBe('3 of 5 known');
    first.unmount();

    queryClient.clear();
    mockedGetSystem.mockResolvedValueOnce(
      referenceSystemDetail({ source_body_count: 2 }),
    );
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });
    await screen.findByRole('heading', { name: 'Reference System' });
    expect(detailValue('Bodies returned')).toBe('3');
  });

  it('lists selectable bodies from V3 and shows their catalogued facts', async () => {
    const id64 = parseId64('10477373803');
    mockedGetSystem.mockResolvedValue(referenceSystemDetail());

    render(SystemDetailTestHost, { props: { id64 } });

    const list = await screen.findByRole('list', { name: 'System bodies' });
    const buttons = within(list).getAllByRole('button');
    // The body without a Frontier BodyID is counted but not selectable.
    expect(buttons.map((button) => button.textContent?.trim())).toEqual([
      'Reference System Star · G2 V',
      'Reference System 3 Planet',
    ]);
    await fireEvent.click(buttons[1] as HTMLElement);
    const card = await screen.findByRole('article');
    expect(card).toHaveAttribute('data-selected-body-id', '3');
    expect(within(card).getByText('Planet')).toBeInTheDocument();
    expect(within(card).getByText('11,450 ls')).toBeInTheDocument();
    expect(within(card).getByText('70,000 km')).toBeInTheDocument();
    expect(within(card).getByText('1 known')).toBeInTheDocument();
    expect(within(card).getByText('No')).toBeInTheDocument();
    expect(
      within(card).getByText('2 biological · 1 geological'),
    ).toBeInTheDocument();

    await fireEvent.click(buttons[0] as HTMLElement);
    const star = await screen.findByRole('article');
    expect(star).toHaveAttribute('data-selected-body-id', '0');
    expect(within(star).getByText('Star · G2 V')).toBeInTheDocument();
    expect(within(star).getByText('Belts')).toBeInTheDocument();
    expect(within(star).getAllByText('None recorded')).toHaveLength(2);
  });

  it('treats 404 and out-of-range 422 as not found and retries other API errors', async () => {
    const id64 = parseId64('42');
    mockedGetSystem.mockRejectedValueOnce(
      new ApiError(404, '/api/v1/systems/42', {}),
    );
    const first = render(SystemDetailTestHost, { props: { id64 } });
    expect(
      await screen.findByRole('heading', { name: 'System not found' }),
    ).toBeInTheDocument();
    first.unmount();
    expect(mockedGetSystem).toHaveBeenCalledTimes(1);

    queryClient.clear();
    const huge = parseId64('18446744073709551615');
    mockedGetSystem.mockRejectedValueOnce(
      new ApiError(422, '/api/v1/systems/18446744073709551615', {}),
    );
    const second = render(SystemDetailTestHost, { props: { id64: huge } });
    expect(
      await screen.findByRole('heading', { name: 'System not found' }),
    ).toBeInTheDocument();
    second.unmount();

    queryClient.clear();
    mockedGetSystem
      .mockRejectedValueOnce(new ApiError(503, '/api/v1/systems/42', {}))
      .mockRejectedValueOnce(new ApiError(503, '/api/v1/systems/42', {}))
      .mockResolvedValueOnce(
        referenceSystemDetail({ id64: '42', name: 'Recovered system' }),
      );
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
