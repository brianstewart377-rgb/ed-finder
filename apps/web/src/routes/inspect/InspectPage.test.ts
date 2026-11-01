import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import { parseId64 } from '$lib/domain/id64';
import ExploreWorkspaceTestHost from '$lib/features/explore/ExploreWorkspaceTestHost.svelte';
import {
  inspectHref,
  navigateWithAnchor,
  type ExploreAnchor,
} from '$lib/features/explore/navigation';
import InspectPageTestHost from './InspectPageTestHost.svelte';

const { mockedPage, mockedGoto, featureGate } = vi.hoisted(() => ({
  mockedPage: {
    url: new URL('http://localhost/inspect'),
    state: {} as App.PageState,
  },
  mockedGoto: vi.fn(),
  featureGate: { enabled: false },
}));

vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));
vi.mock('$lib/config', () => ({
  get FINDER_F4_ENABLED() {
    return featureGate.enabled;
  },
}));
vi.mock('$lib/api/client', async (loadOriginal) => ({
  ...(await loadOriginal<typeof import('$lib/api/client')>()),
  getSystem: vi.fn(),
  autocompleteSystems: vi.fn(),
  searchExploreSystems: vi.fn(),
  getArchetypeRankings: vi.fn(),
  getCatalogueViewportSystems: vi.fn(),
  getMapHeatmap: vi.fn(),
}));
vi.mock('$lib/spatial/babylon/adapter', () => ({
  createBabylonSpatialRuntime: () => ({
    getStatus: () => ({ state: 'created' }),
    start: async () => ({ state: 'ready', backend: 'WEBGL2' }),
    dispatch: () => ({ status: 'executed' }),
    subscribe: () => () => {},
    resize: () => {},
    dispose: () => {},
  }),
}));

const inspectedId = parseId64('18446744073709551615');
const originalId = parseId64('9007199254740993');
const anchor: ExploreAnchor = {
  id64: parseId64('128666762'),
  name: 'Achenar',
  x: 67.5,
  y: -12.25,
  z: 42,
};

function arriveFrom(source: string, state: App.PageState = {}): void {
  mockedPage.url = new URL(
    inspectHref(inspectedId, new URL(`http://localhost/explore?${source}`)),
    'http://localhost',
  );
  mockedPage.state = state;
}

function renderExplore(): void {
  render(ExploreWorkspaceTestHost, {
    initialPage: { url: mockedPage.url, state: mockedPage.state },
    installPage(model) {
      Object.defineProperties(mockedPage, {
        url: {
          configurable: true,
          get: () => model.url,
          set: (url: URL) => {
            model.url = url;
          },
        },
        state: {
          configurable: true,
          get: () => model.state,
          set: (state: App.PageState) => {
            model.state = state;
          },
        },
      });
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
  featureGate.enabled = false;
  Object.defineProperties(mockedPage, {
    url: {
      configurable: true,
      writable: true,
      value: new URL(`http://localhost/inspect?system=${inspectedId}`),
    },
    state: { configurable: true, writable: true, value: {} },
  });
  mockedGoto.mockImplementation(async (destination, options) => {
    mockedPage.url = new URL(destination, mockedPage.url);
    mockedPage.state = options.state;
  });
  // Keep detail mounted under its real QueryClientProvider without starting a map.
  vi.mocked(api.getSystem).mockImplementation(() => new Promise(() => {}));
  vi.mocked(api.searchExploreSystems).mockImplementation(
    () => new Promise(() => {}),
  );
  vi.mocked(api.getArchetypeRankings).mockImplementation(
    () => new Promise(() => {}),
  );
  vi.mocked(api.autocompleteSystems).mockResolvedValue({ results: [] });
  vi.mocked(api.getCatalogueViewportSystems).mockResolvedValue({
    systems: [],
    truncated: false,
  });
  vi.mocked(api.getMapHeatmap).mockResolvedValue({ source: 'legacy-fallback' });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      disconnect = vi.fn();
      unobserve = vi.fn();
    },
  );
});

afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.unstubAllGlobals();
});

describe('Inspect Explore navigation', () => {
  it('keeps the default-off links unchanged even with originating Finder context', () => {
    arriveFrom('archetype=flexible&min-tier=A&page_size=1&offset=2', {
      anchor,
    });
    render(InspectPageTestHost);
    expect(
      screen.getByRole('link', { name: 'Back to Explore' }),
    ).toHaveAttribute('href', '/explore');
    expect(
      screen.getByRole('link', { name: 'Open in Explore' }),
    ).toHaveAttribute('href', `/explore?system=${inspectedId}`);
    expect(mockedGoto).not.toHaveBeenCalled();
  });

  it('replays ranking and unrelated parameters with one inspected selection and overlay id', async () => {
    featureGate.enabled = true;
    arriveFrom(
      `archetype=flexible&min-tier=A&page_size=1&offset=2&selected=${originalId}&selected=42&system=43&system=44&campaign=survey`,
      { anchor },
    );
    const outboundState = mockedPage.state;
    render(InspectPageTestHost);
    await fireEvent.click(
      screen.getByRole('link', { name: 'Open in Explore' }),
    );
    expect(mockedPage.url.pathname).toBe('/explore');
    expect(mockedPage.url.searchParams.getAll('selected')).toEqual([
      inspectedId,
    ]);
    expect(mockedPage.url.searchParams.getAll('system')).toEqual([inspectedId]);
    expect(Object.fromEntries(mockedPage.url.searchParams)).toMatchObject({
      archetype: 'flexible',
      'min-tier': 'A',
      page_size: '1',
      offset: '2',
      campaign: 'survey',
    });
    expect(mockedGoto).toHaveBeenCalledWith(expect.any(String), {
      state: outboundState,
      replaceState: false,
      keepFocus: true,
      noScroll: true,
    });
    expect(mockedPage.state).toBe(outboundState);
  });

  it.each(['Back to Explore', 'Open in Explore'])(
    'uses the enabled bare-link fallback for %s',
    async (action) => {
      featureGate.enabled = true;
      const mounted = render(InspectPageTestHost);
      const href =
        action === 'Back to Explore'
          ? '/explore'
          : `/explore?selected=${inspectedId}&system=${inspectedId}`;
      expect(screen.getByRole('link', { name: action })).toHaveAttribute(
        'href',
        href,
      );
      await fireEvent.click(screen.getByRole('link', { name: action }));
      expect(mockedPage.url.href).toBe(`http://localhost${href}`);
      expect(mockedPage.state).toEqual({});
      mounted.unmount();
      renderExplore();
      await waitFor(() =>
        expect(api.searchExploreSystems).toHaveBeenCalledWith(
          { galaxy_wide: true, sort_by: 'development', size: 50, from: 0 },
          expect.any(AbortSignal),
          null,
          50,
        ),
      );
    },
  );

  it('Back to Explore restores the floor, page and anchor without selecting the inspected system', async () => {
    featureGate.enabled = true;
    const source = 'archetype=flexible&min-tier=A&page_size=1&offset=2';
    mockedPage.url = new URL(`http://localhost/explore?${source}`);
    mockedPage.state = { anchor };
    const originalState = mockedPage.state;
    await navigateWithAnchor(inspectHref(inspectedId, mockedPage.url));
    expect(mockedPage.state).toBe(originalState);
    const mounted = render(InspectPageTestHost);
    await fireEvent.click(
      screen.getByRole('link', { name: 'Back to Explore' }),
    );
    expect(mockedPage.url.searchParams.toString()).toBe(source);
    expect(mockedPage.url.searchParams.has('selected')).toBe(false);
    expect(mockedPage.url.searchParams.has('system')).toBe(false);
    expect(mockedPage.state).toBe(originalState);
    mounted.unmount();
    renderExplore();
    await waitFor(() =>
      expect(api.getArchetypeRankings).toHaveBeenCalledWith(
        { archetype: 'flexible', min_score: 76, page_size: 1, offset: 2 },
        expect.any(AbortSignal),
      ),
    );
    expect(
      screen.getByRole('radio', { name: 'Flexible Multi-Role Colony' }),
    ).toBeChecked();
    expect(screen.getByRole('combobox', { name: 'Minimum tier' })).toHaveValue(
      'A',
    );
    expect(screen.getByRole('combobox', { name: 'System name' })).toHaveValue(
      'Achenar',
    );
    await fireEvent.click(screen.getByRole('radio', { name: 'Any' }));
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenCalledWith(
        {
          reference_coords: { x: 67.5, y: -12.25, z: 42 },
          filters: { distance: { min: 0, max: 500 }, economy: 'any' },
          sort_by: 'distance',
          size: 1,
          from: 0,
        },
        expect.any(AbortSignal),
        { id64: anchor.id64, name: anchor.name },
        1,
      ),
    );
    expect(mockedPage.url.searchParams.has('selected')).toBe(false);
  });

  it('Back replays a prior passive selection without replacing it with the inspected system', async () => {
    featureGate.enabled = true;
    const source = `page_size=1&offset=2&selected=${originalId}`;
    arriveFrom(source, { anchor });
    render(InspectPageTestHost);
    await fireEvent.click(
      screen.getByRole('link', { name: 'Back to Explore' }),
    );
    expect(mockedPage.url.searchParams.toString()).toBe(source);
    expect(mockedPage.url.searchParams.getAll('selected')).toEqual([
      originalId,
    ]);
    expect(mockedPage.url.searchParams.has('system')).toBe(false);
  });
});
