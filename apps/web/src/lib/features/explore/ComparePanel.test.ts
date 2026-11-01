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
import {
  PERSISTENCE_KEYS,
  SNAPSHOT_SOL_ID64,
  type CompareEntry,
  type SnapshotRankingProvenance,
} from '$lib/persistence/storage';
import CompareTestHost from './CompareTestHost.svelte';

const { feature, mockedPage, mockedGoto } = vi.hoisted(() => ({
  feature: { enabled: false },
  mockedPage: { url: new URL('http://localhost/explore'), state: {} },
  mockedGoto: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('$lib/config', () => ({
  get FINDER_F4_ENABLED() {
    return feature.enabled;
  },
}));
vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));

const provenance: SnapshotRankingProvenance = {
  ranking_version: 'ranking-v1',
  ranking_sha256: 'a'.repeat(64),
  archetype_version: 'archetype-v1',
  archetype_model_sha256: 'b'.repeat(64),
  derived_generation_id: 'generation-1',
  publication_sequence: 1,
  archetype_manifest_sha256: 'c'.repeat(64),
};
const solReference = {
  kind: 'sol' as const,
  id64: SNAPSHOT_SOL_ID64,
  name: 'Sol',
};
function savedEntry(
  id: string,
  fields: Partial<CompareEntry> = {},
): CompareEntry {
  return {
    id64: parseId64(id),
    name: `Candidate ${id}`,
    score_kind: 'selected_fit',
    selected_archetype: 'flexible',
    ranking_score: 88,
    ranking_tier: 'B',
    overall_development_potential: 91,
    ranking_provenance: provenance,
    distance_reference: solReference,
    distance: 12,
    primary_archetype: 'flexible',
    ...fields,
  };
}

function metricRow(name: RegExp): HTMLElement {
  return screen.getByRole('rowheader', { name }).closest('tr')!;
}

function captureCsv() {
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:compare');
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = createObjectURL;
      static revokeObjectURL = vi.fn();
    },
  );
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  return async () => {
    await fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsText(createObjectURL.mock.calls[0]![0]);
    });
  };
}

describe('comparison panel', () => {
  beforeEach(() => {
    feature.enabled = false;
    mockedPage.url = new URL('http://localhost/explore');
    mockedPage.state = {};
    mockedGoto.mockClear();
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
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:compare');
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

  it('compares same-reference zero distances and exports them with a reference label in F4', async () => {
    feature.enabled = true;
    compare.set([
      savedEntry('42', { distance: 0 }),
      savedEntry('43', { distance: 20 }),
    ]);
    const exportCsv = captureCsv();
    render(CompareTestHost);
    const distanceRow = metricRow(/Distance from Sol/);
    expect(within(distanceRow).getByText('0.00 LY')).toBeInTheDocument();
    expect(within(distanceRow).getAllByRole('cell')[0]).toHaveTextContent(
      '0.00 LY Best value',
    );
    expect(within(distanceRow).getAllByText('Best value')).toHaveLength(1);
    expect(await exportCsv()).toContain('"Distance from Sol LY","0","20"');
  });

  it.each([
    ['legacy zero', { distance: 0, distance_reference: null }],
    [
      'another anchor',
      {
        distance_reference: {
          kind: 'anchor',
          id64: parseId64('7'),
          name: 'Achenar',
        },
      },
    ],
  ])(
    'omits distance from the F4 table and CSV for %s',
    async (_label, fields) => {
      feature.enabled = true;
      compare.set([savedEntry('42'), savedEntry('43', fields)]);
      const exportCsv = captureCsv();
      render(CompareTestHost);
      expect(
        screen.queryByRole('rowheader', { name: /Distance from/ }),
      ).not.toBeInTheDocument();
      expect(await exportCsv()).not.toMatch(/Distance from/);
    },
  );

  it('uses canonical labels and only the API selected-fit tier, across generations of the same model', () => {
    feature.enabled = true;
    compare.set([
      savedEntry('42'),
      savedEntry('43', {
        ranking_score: 76,
        ranking_tier: null,
        primary_archetype: 'old_custom_key',
        ranking_provenance: {
          ...provenance,
          derived_generation_id: 'generation-2',
          publication_sequence: 9,
          archetype_manifest_sha256: 'd'.repeat(64),
        },
      }),
    ]);
    render(CompareTestHost);
    const fitRow = metricRow(/Flexible Multi-Role Colony fit/);
    expect(within(fitRow).getAllByRole('cell')[0]).toHaveTextContent(
      /B.*88|88.*B/,
    );
    expect(within(fitRow).getAllByRole('cell')[1]).toHaveTextContent(/^76$/);
    expect(metricRow(/Primary archetype/)).toHaveTextContent('old custom key');
    const overall = metricRow(/Best Colony Potential/);
    expect(within(overall).getAllByRole('cell')[0]).toHaveTextContent(/^91$/);
    expect(
      screen.getByText(/Ranked on generation generation-1/i),
    ).toHaveTextContent('publication 1');
    expect(
      screen.getByText(/Ranked on generation generation-2/i),
    ).toHaveTextContent('d'.repeat(64));
  });

  it('compares overall potential across Any and selected modes but omits unlike fits', () => {
    feature.enabled = true;
    compare.set([
      savedEntry('42'),
      savedEntry('43', {
        score_kind: 'overall_potential',
        selected_archetype: null,
        ranking_score: 80,
        ranking_tier: null,
        overall_development_potential: 80,
        distance_reference: { ...solReference, kind: 'anchor' },
        distance: 0,
      }),
    ]);
    render(CompareTestHost);
    expect(metricRow(/Best Colony Potential/)).toHaveTextContent(
      '91 Best value',
    );
    expect(
      screen.queryByRole('rowheader', { name: /Colony fit/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/different ranking modes/i)).toBeInTheDocument();
    expect(metricRow(/Distance from Sol/)).toHaveTextContent(
      '0.00 LY Best value',
    );
  });

  it('omits both score comparisons for different model versions while retaining stored scores', () => {
    feature.enabled = true;
    compare.set([
      savedEntry('42'),
      savedEntry('43', {
        ranking_provenance: {
          ...provenance,
          archetype_model_sha256: 'f'.repeat(64),
        },
      }),
    ]);
    render(CompareTestHost);
    expect(
      screen.queryByRole('rowheader', { name: /Best Colony Potential/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('rowheader', { name: /Colony fit/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/different ranking versions/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Best Colony Potential.*91/)).toHaveLength(2);
  });

  it('keeps older saved scores visible without guessed mode, tier or comparison', () => {
    feature.enabled = true;
    compare.set([
      {
        id64: parseId64('42'),
        name: 'Older candidate',
        archetype_score: 88,
        distance: 0,
      },
      savedEntry('43'),
    ]);
    render(CompareTestHost);
    expect(
      screen.getByRole('link', { name: 'Older candidate' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/older save/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/stored score.*88/i)).not.toHaveTextContent(
      /Tier [SABCD]/,
    );
    expect(
      screen.queryByRole('rowheader', {
        name: /Best Colony Potential|Colony fit|Distance from/,
      }),
    ).not.toBeInTheDocument();
  });

  it('has no automated accessibility violations for F4 comparison notes and snapshot provenance', async () => {
    feature.enabled = true;
    compare.set([savedEntry('42'), savedEntry('43', { distance: 0 })]);
    const { container } = render(CompareTestHost);
    const result = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });

  it('carries the originating Explore query and anchor state through the F4 Inspect link', async () => {
    feature.enabled = true;
    mockedPage.url = new URL(
      'http://localhost/explore?archetype=mining&min-tier=A&page_size=1&offset=2&selected=99',
    );
    mockedPage.state = {
      anchor: { id64: '7', name: 'Reference', x: 10, y: 20, z: 30 },
    };
    compare.set([{ id64: parseId64('42'), name: 'Candidate' }]);
    render(CompareTestHost);
    const link = screen.getByRole('link', { name: 'Candidate' });
    const destination = new URL(link.getAttribute('href')!, 'http://localhost');
    expect(destination.pathname).toBe('/inspect');
    expect(destination.searchParams.get('system')).toBe('42');
    expect(destination.searchParams.get('from')).toBe(
      mockedPage.url.searchParams.toString(),
    );
    await fireEvent.click(link);
    expect(mockedGoto).toHaveBeenCalledWith(
      link.getAttribute('href'),
      expect.objectContaining({ state: mockedPage.state }),
    );
  });
});
