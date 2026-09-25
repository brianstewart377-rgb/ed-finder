import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/svelte';
import { get } from 'svelte/store';
import axe from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseId64 } from '$lib/domain/id64';
import { compare } from '$lib/persistence/stores';
import { PERSISTENCE_KEYS } from '$lib/persistence/storage';
import CompareTestHost from './CompareTestHost.svelte';

describe('comparison panel', () => {
  beforeEach(() => {
    localStorage.clear();
    compare.set([]);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('explains how to start with an empty browser comparison', () => {
    render(CompareTestHost);
    expect(
      screen.getByRole('heading', { name: 'Compare systems' }),
    ).toBeInTheDocument();
    expect(screen.getByText('0 / 6 systems')).toBeInTheDocument();
    expect(
      screen.getByText(/Choose Compare on at least two systems/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('keeps a single snapshot visible and asks for one more', () => {
    compare.set([{ id64: parseId64('42'), name: 'First candidate' }]);
    render(CompareTestHost);
    expect(screen.getByText(/Add one more system/)).toBeInTheDocument();
    expect(
      screen.getByRole('table', { name: 'System comparison' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Best value')).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'First candidate' }),
    ).toHaveAttribute('href', '/inspect?system=42');
  });

  it('renders side-by-side snapshots, exact identifiers, and text best-value indicators', async () => {
    const onOpenDetail = vi.fn();
    const id64 = parseId64('18446744073709551615');
    compare.set([
      {
        id64,
        name: 'Far candidate',
        archetype_score: 91,
        distance: 20,
        purity_score: 75,
        primary_archetype: 'refinery_industrial',
      },
      {
        id64: parseId64('42'),
        name: 'Near candidate',
        archetype_score: 75,
        distance: 12,
        purity_score: 65,
      },
    ]);
    render(CompareTestHost, { props: { onOpenDetail } });
    const scoreRow = screen.getByRole('row', { name: /Development score/ });
    expect(within(scoreRow).getByText('S 91')).toBeInTheDocument();
    expect(within(scoreRow).getByText('Best value')).toBeInTheDocument();
    expect(
      screen.getByRole('row', { name: /Distance from ref/ }),
    ).toHaveTextContent('12.00 LY Best value');
    expect(
      screen.getByText('Refinery / Industrial Megacomplex'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Far candidate on Spansh' }),
    ).toHaveAttribute('href', `https://spansh.co.uk/system/${id64}`);
    await fireEvent.click(
      screen.getByRole('button', { name: 'Far candidate' }),
    );
    expect(onOpenDetail).toHaveBeenCalledWith(id64);
    await fireEvent.click(
      screen.getByRole('button', {
        name: 'Remove Far candidate from comparison',
      }),
    );
    expect(get(compare).value.map((entry) => entry.name)).toEqual([
      'Near candidate',
    ]);
    expect(
      JSON.parse(localStorage.getItem(PERSISTENCE_KEYS.compare)!),
    ).toHaveLength(1);
  });

  it('confirms clearing all snapshots and exports CSV', async () => {
    compare.set([{ id64: parseId64('42'), name: 'Candidate', population: 0 }]);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const createObjectURL = vi.fn(() => 'blob:compare');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = createObjectURL;
        static revokeObjectURL = revokeObjectURL;
      },
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});
    render(CompareTestHost);
    await fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:compare');
    await fireEvent.click(
      screen.getByRole('button', { name: 'Clear comparison' }),
    );
    expect(get(compare).value).toHaveLength(1);
    confirm.mockReturnValue(true);
    await fireEvent.click(
      screen.getByRole('button', { name: 'Clear comparison' }),
    );
    expect(get(compare).value).toHaveLength(0);
    expect(screen.getByText('0 / 6 systems')).toBeInTheDocument();
  });

  it('has no automated accessibility violations with a populated comparison', async () => {
    compare.set([
      { id64: parseId64('42'), name: 'Candidate A', archetype_score: 88 },
      { id64: parseId64('43'), name: 'Candidate B', archetype_score: 70 },
    ]);
    const { container } = render(CompareTestHost);
    const result = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });
});
