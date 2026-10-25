import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  getSystem,
  getSystemRatingExplanation,
  getSystemRatings,
  systemDetailFromV3,
} from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import {
  ratingsIdentity,
  referenceRatingExplanation,
  referenceSystemDetail,
  referenceSystemRatings,
  v3Body,
  v3Ring,
  v3Station,
  v3System,
} from '$lib/api/v3-system-fixtures';
import { parseId64 } from '$lib/domain/id64';
import SystemDetailTestHost from './SystemDetailTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return {
    ...original,
    getSystem: vi.fn(),
    getSystemRatings: vi.fn(),
    getSystemRatingExplanation: vi.fn(),
  };
});

const mockedGetSystem = vi.mocked(getSystem);
const mockedGetRatings = vi.mocked(getSystemRatings);
const mockedGetExplanation = vi.mocked(getSystemRatingExplanation);

/** Each child element's text, whitespace-normalised: one entry per column. */
const partsOf = (element: HTMLElement): string[] =>
  [...element.children].map(
    (child) => child.textContent?.replace(/\s+/gu, ' ').trim() ?? '',
  );

function detailValue(term: string): string | null {
  const dt = screen.getByText(term, { selector: 'dt' });
  return dt.parentElement?.querySelector('dd')?.textContent?.trim() ?? null;
}

describe('shared system detail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    mockedGetRatings.mockResolvedValue(referenceSystemRatings());
    mockedGetExplanation.mockResolvedValue(referenceRatingExplanation());
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
  it('lists each ring and belt with its type, reserves and mining hotspots', async () => {
    mockedGetSystem.mockResolvedValue(
      systemDetailFromV3(
        v3System(),
        [
          v3Body(),
          v3Body({
            body_id: '108086391056891904',
            frontier_body_id: '3',
            name: 'Reference System 3',
            body_type: 'planet',
            is_main_star: null,
            spectral_class: null,
            luminosity_class: null,
            distance_from_arrival_ls: 11_450,
          }),
        ],
        [
          v3Ring({
            ring_type: 'metallic',
            reserve_type: 'pristine',
            signals: [
              { signal_type: 'painite', count: 1 },
              { signal_type: 'platinum', count: 2 },
            ],
          }),
          v3Ring({
            ring_id: '900719925632971231',
            name: 'Reference System 3 B Ring',
            ring_type: 'icy',
            reserve_type: null,
            signals_complete: null,
          }),
        ],
        [],
      ),
    );
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });

    const list = await screen.findByRole('list', { name: 'System bodies' });
    await fireEvent.click(
      within(list).getByRole('button', { name: /Reference System 3/u }),
    );
    const card = await screen.findByRole('article');
    const rings = within(card).getAllByRole('listitem');
    expect(rings.map(partsOf)).toEqual([
      [
        'Reference System 3 A Ring',
        'Metallic · Pristine reserves',
        'Hotspots: 2 Platinum · 1 Painite',
      ],
      ['Reference System 3 B Ring', 'Icy', 'Hotspots not recorded'],
    ]);
  });

  it('lists stations with their type, distance, body and economies', async () => {
    mockedGetSystem.mockResolvedValue(
      systemDetailFromV3(
        v3System(),
        [
          v3Body(),
          v3Body({
            body_id: '108086391056891904',
            frontier_body_id: '3',
            name: 'Reference System 3',
            body_type: 'planet',
            is_main_star: null,
            distance_from_arrival_ls: 11_450,
          }),
        ],
        [],
        [
          v3Station({
            station_id: '128000002',
            name: 'Far Outpost',
            station_type: 'outpost',
            distance_from_arrival_ls: 9_000,
          }),
          v3Station({
            station_id: '128000003',
            name: 'K7Q-1XZ',
            station_type: 'fleet_carrier',
            distance_from_arrival_ls: 12,
          }),
          v3Station({
            station_type: 'coriolis_starport',
            body_id: '108086391056891904',
            association_state: 'BODY_RESOLVED',
            economies: [
              {
                economy: 'refinery',
                economy_weight: 0.3,
                is_primary: false,
                is_secondary: true,
              },
              {
                economy: 'extraction',
                economy_weight: 0.7,
                is_primary: true,
                is_secondary: false,
              },
            ],
          }),
        ],
      ),
    );
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });

    const heading = await screen.findByRole('heading', { name: 'Stations' });
    const section = heading.closest('section') as HTMLElement;
    const ports = section.querySelector(':scope > ul') as HTMLElement;
    // Nearest first; the far outpost's placement and economy are unknown.
    expect(within(ports).getAllByRole('listitem').map(partsOf)).toEqual([
      [
        'Reference Port',
        'Coriolis Starport · 500 ls · Reference System 3',
        'Extraction 70% (primary) · Refinery 30% (secondary)',
      ],
      ['Far Outpost', 'Outpost · 9,000 ls', 'Economy not recorded'],
    ]);
    // Fleet carriers are listed apart, behind a closed toggle.
    const carriers = section.querySelector(
      'details.station-carriers',
    ) as HTMLDetailsElement;
    expect(carriers.open).toBe(false);
    expect(carriers.querySelector('summary')?.textContent?.trim()).toBe(
      '1 fleet carrier',
    );
    expect(
      [...carriers.querySelectorAll('li')].map((item) => partsOf(item)),
    ).toEqual([['K7Q-1XZ', 'Fleet Carrier · 12 ls']]);
  });

  it('shows Ratings V4 potentials, highest first, without fetching an explanation', async () => {
    mockedGetSystem.mockResolvedValue(referenceSystemDetail());
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });

    const heading = await screen.findByRole('heading', {
      name: 'Economy potential',
    });
    const section = heading.closest('section') as HTMLElement;
    await waitFor(() =>
      expect(section.querySelectorAll('[data-rating-economy]')).toHaveLength(7),
    );
    const economies = [
      ...section.querySelectorAll('[data-rating-economy]'),
    ].map((row) => row.getAttribute('data-rating-economy'));
    expect(economies).toEqual([
      'Agriculture',
      'Tourism',
      'HighTech',
      'Extraction',
      'Industrial',
      'Refinery',
      'Military',
    ]);
    const first = section.querySelector('[data-rating-economy="Agriculture"]');
    // Economy, potential, confidence, explanation control.
    expect(partsOf(first as HTMLElement)).toEqual([
      'Agriculture',
      '84',
      '72%',
      'Why?',
    ]);
    expect(
      within(section).getByRole('table', { name: 'Economy potential' }),
    ).toBeInTheDocument();
    expect(mockedGetRatings).toHaveBeenCalledWith(
      '10477373803',
      expect.anything(),
    );
    expect(mockedGetExplanation).not.toHaveBeenCalled();
    expect(section.textContent).not.toMatch(/undefined|null|NaN/u);
  });

  it('explains a rating on demand with body names, links and unknowns', async () => {
    mockedGetSystem.mockResolvedValue(referenceSystemDetail());
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });

    const why = await screen.findByRole('button', { name: 'Why? Agriculture' });
    expect(why).toHaveAttribute('aria-expanded', 'false');
    await fireEvent.click(why);
    expect(why).toHaveAttribute('aria-expanded', 'true');

    const region = await screen.findByRole('region', {
      name: 'Why Agriculture scores 84',
    });
    const table = await within(region).findByRole('table', {
      name: 'Bodies that make up this score',
    });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(
      rows.map((row) => {
        const [body, role, score, weight] = partsOf(row);
        return [body, score, weight, role?.startsWith('Native') ?? false];
      }),
    ).toEqual([
      ['Reference System 3', '95', '82%', true],
      ['Reference System 3 a', '55', '11%', false],
    ]);
    for (const text of [
      'Native (water world)',
      'Base 75; +20 Biological signals, Water world',
      'Modifier',
      'Base 55; +10 Biological signals; −10 Icy body',
    ])
      expect(within(table).getByText(text)).toBeInTheDocument();
    expect(
      within(region).getByText('Reference System 3 a: reserve level'),
    ).toBeInTheDocument();
    expect(
      within(region).getByText('Scorer 4.0.0 · mechanics v4-mechanics-2026-09'),
    ).toBeInTheDocument();
    // The explanation is requested for the exact ratings on screen.
    expect(mockedGetExplanation).toHaveBeenCalledWith(
      '10477373803',
      ratingsIdentity(),
      expect.anything(),
    );

    await fireEvent.click(why);
    expect(why).toHaveAttribute('aria-expanded', 'false');
    expect(region).not.toBeVisible();
  });

  it('never shows an explanation from a different publication', async () => {
    mockedGetSystem.mockResolvedValue(referenceSystemDetail());
    mockedGetExplanation.mockResolvedValueOnce({
      kind: 'republished',
      identity: ratingsIdentity({ publicationSequence: '2' }),
    });
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });

    await fireEvent.click(
      await screen.findByRole('button', { name: 'Why? Tourism' }),
    );
    const region = await screen.findByRole('region', {
      name: 'Why Tourism scores 70',
    });
    expect(
      await within(region).findByText(
        'The ratings were republished while this page was open.',
      ),
    ).toBeInTheDocument();
    expect(within(region).queryByRole('table')).toBeNull();
    await fireEvent.click(
      within(region).getByRole('button', { name: 'Reload ratings' }),
    );
    // Both reload, even though the ratings come back with the same identity.
    await waitFor(() => expect(mockedGetRatings).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockedGetExplanation).toHaveBeenCalledTimes(2));
    expect(
      await within(region).findByRole('table', {
        name: 'Bodies that make up this score',
      }),
    ).toBeInTheDocument();
  });

  it('keeps Inspect usable when a system is unrated or ratings are down', async () => {
    mockedGetSystem.mockResolvedValue(referenceSystemDetail());
    mockedGetRatings.mockRejectedValueOnce(
      new ApiError(404, '/api/ratings/v4/systems/10477373803', {}),
    );
    const first = render(SystemDetailTestHost, {
      props: { id64: parseId64('10477373803') },
    });
    expect(
      await screen.findByText(
        'This system is not in the published ratings yet.',
      ),
    ).toBeInTheDocument();
    expect(mockedGetRatings).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole('heading', { name: 'Reference System' }),
    ).toBeInTheDocument();
    first.unmount();

    queryClient.clear();
    mockedGetRatings
      .mockRejectedValueOnce(new ApiError(503, '/api/ratings/v4/systems/1', {}))
      .mockRejectedValueOnce(
        new ApiError(503, '/api/ratings/v4/systems/1', {}),
      );
    render(SystemDetailTestHost, { props: { id64: parseId64('10477373803') } });
    expect(
      await screen.findByText(
        'Economy ratings could not be loaded.',
        {},
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() =>
      expect(document.querySelectorAll('[data-rating-economy]')).toHaveLength(
        7,
      ),
    );
  });
});
