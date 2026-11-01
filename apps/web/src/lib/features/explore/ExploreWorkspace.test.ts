import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axe from 'axe-core';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { tick } from 'svelte';
import * as api from '$lib/api/client';
import { queryClient, queryKeys } from '$lib/api/query';
import { auth } from '$lib/auth/auth';
import { FINDER_F4_ENABLED } from '$lib/config';
import { parseId64 } from '$lib/domain/id64';
import type {
  RuntimeEvent,
  RuntimeCommand,
  SpatialRuntimeStatus,
  GalaxySceneContract,
} from '$lib/spatial/contracts';
import type { ExploreAnchor } from './navigation';
import * as galaxyRegions from '$lib/spatial/galaxy-regions';
import * as galaxyNebulae from '$lib/spatial/galaxy-nebulae';
import { createManagedSpatialRuntime } from '$lib/spatial/lifecycle';
import ExploreWorkspaceTestHost from './ExploreWorkspaceTestHost.svelte';

const { mockedPage, mockedGoto, featureGate } = vi.hoisted(() => ({
  mockedPage: {
    url: new URL('http://localhost/explore'),
    state: {} as App.PageState,
  },
  mockedGoto: vi.fn().mockResolvedValue(undefined),
  featureGate: { enabled: false },
}));

vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));
vi.mock('$lib/config', () => ({
  get FINDER_F4_ENABLED() {
    return featureGate.enabled;
  },
}));
vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return {
    ...original,
    autocompleteSystems: vi.fn(),
    searchExploreSystems: vi.fn(),
    getArchetypeRankings: vi.fn(),
    getSystem: vi.fn(),
    getCatalogueViewportSystems: vi.fn(),
    getCommanderTravelHeatmap: vi.fn(),
    getAuthSession: vi.fn(),
    getMapHeatmap: vi.fn(),
  };
});

const runtimeAdapter = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('$lib/spatial/babylon/adapter', () => ({
  createBabylonSpatialRuntime: runtimeAdapter.create,
}));

const pyramidFixture: api.MapHeatmapPyramidResponse = {
  source: 'pyramid',
  generation_id: 'gen-1',
  spatial_generation_id: 'gen-1',
  spatial_pyramid_version: 'v1',
  source_system_count: 200,
  coverage_at: '2026-01-01T00:00:00Z',
  level: 0,
  cell_size_ly: 1000,
  voxel_size: 1000,
  bounds: {
    min_x: 0,
    max_x: 2000,
    min_y: 0,
    max_y: 1000,
    min_z: 0,
    max_z: 1000,
  },
  cells: [
    {
      origin_x_ly: 0,
      origin_y_ly: 0,
      origin_z_ly: 0,
      centroid_x_ly: 500,
      centroid_y_ly: 500,
      centroid_z_ly: 500,
      system_count: 120,
    },
    {
      origin_x_ly: 1000,
      origin_y_ly: 0,
      origin_z_ly: 0,
      centroid_x_ly: 1500,
      centroid_y_ly: 500,
      centroid_z_ly: 500,
      system_count: 80,
    },
  ],
  count: 2,
  max_cells: 40_000,
  truncated: false,
};

const coarsePyramidFixture: api.MapHeatmapPyramidResponse = {
  ...pyramidFixture,
  cells: [{ ...pyramidFixture.cells[0], system_count: 200 }],
  count: 1,
};

const legacyFixture: api.MapHeatmapResponse = { source: 'legacy-fallback' };

function stubRuntime(): void {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      disconnect = vi.fn();
      unobserve = vi.fn();
    },
  );
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(640);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(360);
  runtimeAdapter.create.mockImplementation(
    (_canvas, onStatus: (status: SpatialRuntimeStatus) => void) => {
      let listener: ((event: RuntimeEvent) => void) | undefined;
      return {
        getStatus: () => ({ state: 'created' as const }),
        start: vi.fn(async () => {
          const ready = { state: 'ready' as const, backend: 'WEBGL2' as const };
          onStatus(ready);
          return ready;
        }),
        dispatch: vi.fn((command: RuntimeCommand) => {
          if (command.type === 'FLY_TO')
            queueMicrotask(() =>
              listener?.({
                type: 'TRANSITION_FINISHED',
                target: command.target,
              }),
            );
          return { status: 'executed' as const };
        }),
        subscribe: vi.fn((next: (event: RuntimeEvent) => void) => {
          listener = next;
          return vi.fn();
        }),
        resize: vi.fn(),
        dispose: vi.fn(),
      };
    },
  );
}

function mockFacadeDefaults(): void {
  featureGate.enabled = false;
  Object.defineProperties(mockedPage, {
    url: {
      configurable: true,
      writable: true,
      value: new URL('http://localhost/explore'),
    },
    state: { configurable: true, writable: true, value: {} },
  });
  mockedGoto.mockImplementation(async () => undefined);
  vi.mocked(api.autocompleteSystems).mockResolvedValue({ results: [] });
  mockedPage.url = new URL('http://localhost/explore');
  vi.mocked(api.searchExploreSystems).mockResolvedValue({
    results: [],
    page: {
      page_size: 24,
      count: 0,
      total: 0,
      navigable_total: 0,
      offset: 0,
      navigation_limit: 10_000,
      truncation: { source: 'local-search', total_is_capped: false },
    },
    ranking: {
      ranking_version: 'v3-colony-potential-2',
      ranking_sha256: 'ranking-sha',
      derived_generation_id: 'generation-id',
      publication_sequence: 1,
      archetype_version: 'archetype-version',
      archetype_manifest_sha256: 'manifest-sha',
      archetype_model_sha256: 'model-sha',
    },
  });
  vi.mocked(api.getCatalogueViewportSystems).mockResolvedValue({
    systems: [],
    truncated: false,
  });
  vi.mocked(api.getCommanderTravelHeatmap).mockResolvedValue({
    mode: 'markers',
    visits: [],
    count: 0,
    truncated: false,
  });
  vi.mocked(api.getAuthSession).mockResolvedValue({
    authenticated: false,
    user: null,
  });
}

describe('ExploreWorkspace density cross-fade wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    stubRuntime();
    mockFacadeDefaults();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('fetches the galaxy heatmap when zoomed out and shows the live density cell count', async () => {
    vi.mocked(api.getMapHeatmap).mockResolvedValue(pyramidFixture);

    render(ExploreWorkspaceTestHost);

    await waitFor(() => expect(api.getMapHeatmap).toHaveBeenCalled());
    expect(await screen.findByText(/2 density cells/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Known-system density · zoom in/),
    ).not.toBeInTheDocument();
    // The density swirl requests every occupied cell (min_systems: 1) so a
    // non-truncated payload reconciles, and keys by the normalized voxel size
    // (118_000 ly / 200, rounded) rather than the raw float distance.
    expect(api.getMapHeatmap).toHaveBeenCalledWith(
      expect.objectContaining({
        min_systems: 1,
        voxel_size: 590,
        max_cells: 40_000,
      }),
      expect.anything(),
    );
  });

  it('reports no density contribution and no error for a legacy-fallback heatmap', async () => {
    vi.mocked(api.getMapHeatmap).mockResolvedValue(legacyFixture);

    render(ExploreWorkspaceTestHost);

    await waitFor(() => expect(api.getMapHeatmap).toHaveBeenCalled());
    await screen.findByText(/exact stars/);
    expect(screen.queryByText(/density cells/)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('patches an older cached density viewport without reloading the scene', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.mocked(api.getMapHeatmap).mockImplementation(async (request) =>
      request.voxel_size === 590 ? pyramidFixture : coarsePyramidFixture,
    );
    render(ExploreWorkspaceTestHost);
    await vi.waitFor(
      () => {
        expect(screen.getByText(/2 density cells/)).toBeInTheDocument();
        expect(
          runtimeCommands().some((command) => command.type === 'LOAD_SCENE'),
        ).toBe(true);
      },
      { interval: 1 },
    );
    const initialLoads = runtimeCommands().filter(
      (command) => command.type === 'LOAD_SCENE',
    ).length;
    const densityPatches = () =>
      runtimeCommands().filter(
        (command) => command.type === 'PATCH_CONTRIBUTION',
      );
    emitRuntime({
      type: 'CAMERA_CHANGED',
      camera: { ...currentScene().camera, distanceLy: 180_000, revision: 1 },
    });
    await vi.advanceTimersByTimeAsync(180);
    await vi.waitFor(
      () => expect(screen.getByText(/1 density cells/)).toBeInTheDocument(),
      { interval: 1 },
    );
    const newerRevision = densityPatches().at(-1)!.contribution.revision;
    const cachedUpdatedAt = queryClient.getQueryState([
      'map-heatmap',
      590,
    ])!.dataUpdatedAt;
    expect(cachedUpdatedAt).toBeLessThan(
      queryClient.getQueryState(['map-heatmap', 900])!.dataUpdatedAt,
    );
    const fetchesBeforeReturn = vi.mocked(api.getMapHeatmap).mock.calls.length;

    emitRuntime({
      type: 'CAMERA_CHANGED',
      camera: { ...currentScene().camera, distanceLy: 118_000, revision: 2 },
    });
    await vi.advanceTimersByTimeAsync(180);
    await vi.waitFor(
      () => expect(screen.getByText(/2 density cells/)).toBeInTheDocument(),
      { interval: 1 },
    );
    expect(api.getMapHeatmap).toHaveBeenCalledTimes(fetchesBeforeReturn);
    expect(queryClient.getQueryState(['map-heatmap', 590])!.dataUpdatedAt).toBe(
      cachedUpdatedAt,
    );
    expect(densityPatches().at(-1)!.contribution.revision).toBeGreaterThan(
      newerRevision,
    );
    expect(densityPatches().at(-1)!.contribution.layers[0].targetCount).toBe(2);
    expect(
      runtimeCommands().filter((command) => command.type === 'LOAD_SCENE'),
    ).toHaveLength(initialLoads);
  });

  it('removes a density contribution once when a refreshed response is unavailable', async () => {
    vi.mocked(api.getMapHeatmap).mockResolvedValue(pyramidFixture);
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/2 density cells/);
    await waitFor(() => expect(currentScene()).toBeDefined());
    const initialLoads = runtimeCommands().filter(
      (command) => command.type === 'LOAD_SCENE',
    ).length;
    vi.mocked(api.getMapHeatmap).mockResolvedValue(legacyFixture);
    await queryClient.invalidateQueries({ queryKey: ['map-heatmap'] });
    await waitFor(() =>
      expect(
        runtimeCommands().filter((command) => command.type === 'LOAD_SCENE'),
      ).toHaveLength(initialLoads + 1),
    );
    expect(
      currentScene()
        .contributions.flatMap((contribution) => contribution.layers)
        .some((layer) => layer.id === 'catalogue-density'),
    ).toBe(false);
    expect(screen.queryByText(/density cells/)).not.toBeInTheDocument();
    await queryClient.invalidateQueries({ queryKey: ['map-heatmap'] });
    await tick();
    expect(
      runtimeCommands().filter((command) => command.type === 'LOAD_SCENE'),
    ).toHaveLength(initialLoads + 1);
  });
});

describe('ExploreWorkspace Finder F4 gate (default off)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    stubRuntime();
    mockFacadeDefaults();
    vi.mocked(api.getMapHeatmap).mockResolvedValue(legacyFixture);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('is built with the gate off', () => {
    expect(FINDER_F4_ENABLED).toBe(false);
  });

  it("replace-strips a hand-authored archetype URL, never calls rankings, issues exactly today's request and renders no ranking UI", async () => {
    mockedPage.url = new URL(
      'http://localhost/explore?archetype=flexible&min-tier=A&page_size=1&offset=1&selected=9007199254740993&system=158872029&view=cards#results',
    );

    render(ExploreWorkspaceTestHost);

    await waitFor(() => expect(api.searchExploreSystems).toHaveBeenCalled());
    await waitFor(() => expect(mockedGoto).toHaveBeenCalledTimes(1));

    // F4 parameters are stripped by replacement; `selected`, `system` and
    // unrelated parameters (plus the hash) survive in their original order.
    expect(mockedGoto).toHaveBeenCalledWith(
      '/explore?selected=9007199254740993&system=158872029&view=cards#results',
      { replaceState: true, noScroll: true, keepFocus: true },
    );

    // The rankings facade is unreachable and the local-search body is exactly
    // today's unanchored request: no tier floor, no codec-driven size/from.
    expect(api.getArchetypeRankings).not.toHaveBeenCalled();
    expect(api.searchExploreSystems).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.searchExploreSystems).mock.calls[0]?.[0]).toEqual({
      galaxy_wide: true,
      sort_by: 'development',
      size: 24,
      from: 0,
    });
    // Unanchored: no distance reference is supplied to the facade.
    expect(vi.mocked(api.searchExploreSystems).mock.calls[0]?.[2]).toBeNull();

    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/minimum tier/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Best Colony Potential/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Galaxy-wide .* ranking/),
    ).not.toBeInTheDocument();
  });

  it('leaves a URL without F4 parameters alone (no replacement navigation)', async () => {
    mockedPage.url = new URL(
      'http://localhost/explore?selected=9007199254740993&view=cards',
    );

    render(ExploreWorkspaceTestHost);

    await waitFor(() => expect(api.searchExploreSystems).toHaveBeenCalled());
    await screen.findByText(/exact stars/);
    expect(mockedGoto).not.toHaveBeenCalled();
  });
});

const rankingIdentity: api.RankingProvenance = {
  ranking_version: 'v3-colony-potential-2',
  ranking_sha256: 'ranking-sha',
  derived_generation_id: 'generation-id',
  publication_sequence: 1,
  archetype_version: 'archetype-version',
  archetype_manifest_sha256: 'manifest-sha',
  archetype_model_sha256: 'model-sha',
};
const anchorA: ExploreAnchor = {
  id64: parseId64('9007199254740993'),
  name: 'Anchor A',
  x: 10,
  y: 20,
  z: 30,
};
const anchorB: ExploreAnchor = {
  id64: parseId64('9007199254740994'),
  name: 'Anchor B',
  x: -10,
  y: -20,
  z: -30,
};
const rankedRows: api.ExploreSystem[] = [1, 2, 3].map((index) => ({
  id64: parseId64(`900719925474100${index}`),
  name: `Ranked ${index}`,
  coords: { x: index * 10, y: index, z: index * 20 },
  overall_development_potential: 90 - index,
  ranking_score: 80 - index,
  ranking_tier: 'A',
  score_kind: 'selected_fit',
  selected_archetype: 'manufacturing_hub',
  primary_archetype: 'manufacturing_hub',
  confidence: 0.9,
  completeness: 0.9,
}));

function finderPage(offset: number, pageSize = 1, total = 3, selected = false) {
  return {
    results: rankedRows.slice(offset, Math.min(total, offset + pageSize)),
    page: {
      page_size: pageSize,
      offset,
      total,
      navigable_total: total,
      count: Math.max(0, Math.min(pageSize, total - offset)),
      navigation_limit: 10_000,
      truncation: selected
        ? { source: 'rankings' as const, is_truncated: false }
        : { source: 'local-search' as const, total_is_capped: false },
    },
    ranking: rankingIdentity,
  };
}

function mockRankedPages(total = 3): void {
  vi.mocked(api.searchExploreSystems).mockImplementation(
    async (request, _signal, _anchor, pageSize) =>
      finderPage(request.from ?? 0, pageSize ?? request.size ?? 50, total),
  );
  vi.mocked(api.getArchetypeRankings).mockImplementation(async (request) => ({
    ...finderPage(request.offset, request.page_size, total, true),
    archetype: request.archetype,
    archetype_label: 'Manufacturing Hub',
  }));
}

function renderEnabled(query = 'page_size=1', state: App.PageState = {}) {
  const entries = [
    { url: new URL(`http://localhost/explore?${query}`), state },
  ];
  let index = 0;
  mockedGoto.mockImplementation(
    async (destination: string | URL, options = {}) => {
      const entry = {
        url: new URL(destination, mockedPage.url),
        state: options.state ?? {},
      };
      if (options.replaceState) entries[index] = entry;
      else {
        entries.splice(index + 1);
        entries.push(entry);
        index += 1;
      }
      mockedPage.url = entry.url;
      mockedPage.state = entry.state;
    },
  );
  render(ExploreWorkspaceTestHost, {
    initialPage: entries[0],
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
  return {
    back() {
      index -= 1;
      mockedPage.url = entries[index].url;
      mockedPage.state = entries[index].state;
    },
    forward() {
      index += 1;
      mockedPage.url = entries[index].url;
      mockedPage.state = entries[index].state;
    },
    restore(query: string, restored: App.PageState = state) {
      mockedPage.url = new URL(`http://localhost/explore?${query}`);
      mockedPage.state = restored;
    },
  };
}

function runtimeCommands(): RuntimeCommand[] {
  const runtime = runtimeAdapter.create.mock.results.at(-1)?.value;
  return (
    runtime?.dispatch.mock.calls.map(
      ([command]: [RuntimeCommand]) => command,
    ) ?? []
  );
}

function currentScene(): GalaxySceneContract {
  const runtime = runtimeAdapter.create.mock.results.at(-1)?.value;
  const loads = runtime.dispatch.mock.calls.filter(
    ([command]: [{ type: string }]) => command.type === 'LOAD_SCENE',
  );
  return loads.at(-1)?.[0].scene;
}

function scenePointIds(): string[] {
  return currentScene().contributions.flatMap((contribution) =>
    contribution.layers.flatMap((layer) => {
      const payload = layer.payload as { systems?: { systemId64: string }[] };
      return payload.systems?.map((point) => point.systemId64) ?? [];
    }),
  );
}

function emitRuntime(event: RuntimeEvent): void {
  const runtime = runtimeAdapter.create.mock.results.at(-1)?.value;
  runtime.subscribe.mock.calls[0][0](event);
}

async function expectPage(index: number): Promise<void> {
  await waitFor(() =>
    expect(
      within(screen.getByRole('list', { name: 'System results' })).getByText(
        `Ranked ${index + 1}`,
      ),
    ).toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty(
      'disabled',
      index === 2,
    ),
  );
  const list = screen.getByRole('list', { name: 'System results' });
  expect(within(list).getAllByRole('listitem')).toHaveLength(1);
  expect(within(list).getByText(`Ranked ${index + 1}`)).toBeInTheDocument();
  expect(
    screen.getByText(`Showing 1 of 3 (results ${index + 1}–${index + 1})`),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(scenePointIds()).toEqual([rankedRows[index].id64]),
  );
}

describe('ExploreWorkspace enabled Finder ranking surface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    localStorage.clear();
    stubRuntime();
    mockFacadeDefaults();
    featureGate.enabled = true;
    mockRankedPages();
    vi.mocked(api.getMapHeatmap).mockResolvedValue(legacyFixture);
    vi.mocked(api.getSystem).mockImplementation(async (id64) => ({
      id64,
      name: `Restored ${id64}`,
      lifecycleState: 'ACTIVE',
      x: 50,
      y: 60,
      z: 70,
      sourceBodyCount: null,
      loadedBodyCount: 0,
      sourceUpdatedAt: null,
      bodies: [],
      stations: [],
    }));
  });

  afterEach(() => {
    cleanup();
    featureGate.enabled = false;
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(['any', 'selected'])(
    'keeps %s one-row page requests, range, list and map together across three pages',
    async (mode) => {
      renderEnabled(
        mode === 'any'
          ? 'page_size=1'
          : 'archetype=manufacturing_hub&page_size=1',
      );
      for (let index = 0; index < 3; index += 1) {
        await expectPage(index);
        expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty(
          'disabled',
          index === 0,
        );
        if (index < 2)
          await fireEvent.click(screen.getByRole('button', { name: 'Next' }));
      }
      if (mode === 'any') {
        expect(
          vi
            .mocked(api.searchExploreSystems)
            .mock.calls.map(([request, , , pageSize]) => ({
              size: request.size,
              from: request.from,
              pageSize,
            })),
        ).toEqual([0, 1, 2].map((from) => ({ size: 1, from, pageSize: 1 })));
        expect(api.getArchetypeRankings).not.toHaveBeenCalled();
      } else {
        expect(
          vi
            .mocked(api.getArchetypeRankings)
            .mock.calls.map(([request]) => request),
        ).toEqual(
          [0, 1, 2].map((offset) => ({
            archetype: 'manufacturing_hub',
            min_score: 60,
            page_size: 1,
            offset,
          })),
        );
        expect(api.searchExploreSystems).not.toHaveBeenCalled();
      }
    },
  );

  it('replaces a positive stale offset once and refetches with the committed anchor', async () => {
    renderEnabled('page_size=1&offset=9&view=cards', { anchor: anchorA });
    await screen.findByText('Page reset to the last available results.');
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenCalledTimes(2),
    );
    expect(mockedGoto).toHaveBeenCalledTimes(1);
    expect(mockedGoto).toHaveBeenCalledWith(
      '/explore?page_size=1&offset=2&view=cards',
      expect.objectContaining({
        replaceState: true,
        state: { anchor: anchorA },
      }),
    );
    expect(
      vi.mocked(api.searchExploreSystems).mock.calls.map(([request]) => ({
        from: request.from,
        reference: request.reference_coords,
      })),
    ).toEqual([
      { from: 9, reference: { x: 10, y: 20, z: 30 } },
      { from: 2, reference: { x: 10, y: 20, z: 30 } },
    ]);
    await expectPage(2);
    expect(screen.queryByText(/No systems match/)).not.toBeInTheDocument();
  });

  it('resets offset on tier and page-size commits and resizes the shared list/map page', async () => {
    renderEnabled(
      'archetype=manufacturing_hub&min-tier=A&page_size=1&offset=1',
    );
    await screen.findByText('Ranked 2');
    await fireEvent.change(
      screen.getByRole('combobox', { name: 'Minimum tier' }),
      { target: { value: 'S' } },
    );
    await waitFor(() =>
      expect(api.getArchetypeRankings).toHaveBeenLastCalledWith(
        {
          archetype: 'manufacturing_hub',
          min_score: 88,
          page_size: 1,
          offset: 0,
        },
        expect.anything(),
      ),
    );
    expect(mockedPage.url.searchParams.has('offset')).toBe(false);
    await fireEvent.change(
      screen.getByRole('spinbutton', { name: 'Results per page' }),
      { target: { value: '2' } },
    );
    await screen.findByText('Showing 2 of 3 (results 1–2)');
    expect(api.getArchetypeRankings).toHaveBeenLastCalledWith(
      {
        archetype: 'manufacturing_hub',
        min_score: 88,
        page_size: 2,
        offset: 0,
      },
      expect.anything(),
    );
    expect(
      within(screen.getByRole('list', { name: 'System results' })).getAllByRole(
        'listitem',
      ),
    ).toHaveLength(2);
    await waitFor(() =>
      expect(scenePointIds()).toEqual([rankedRows[0].id64, rankedRows[1].id64]),
    );
  });

  it('keeps a genuine zero-result selected page empty without rewriting its offset', async () => {
    mockRankedPages(0);
    renderEnabled(
      'archetype=manufacturing_hub&min-tier=S&page_size=1&offset=9',
    );
    await screen.findByText(
      'No systems meet minimum tier S for Manufacturing Hub.',
    );
    expect(mockedGoto).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'Reset to tier B' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Choose Any' }),
    ).toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Reset to tier B' }),
    );
    await waitFor(() =>
      expect(mockedPage.url.search).toBe(
        '?archetype=manufacturing_hub&page_size=1',
      ),
    );
  });

  it('canonicalizes a fresh huge offset before the first request reaches the API', async () => {
    vi.mocked(api.searchExploreSystems).mockImplementation(async (request) => ({
      ...finderPage(request.from ?? 0, 1, 10_000),
      results: [rankedRows[0]],
    }));
    renderEnabled('page_size=1&offset=2000000000');
    await screen.findByText('Ranked 1');
    expect(mockedGoto).toHaveBeenCalledTimes(1);
    expect(mockedGoto).toHaveBeenCalledWith(
      '/explore?page_size=1&offset=9999',
      expect.objectContaining({ replaceState: true }),
    );
    expect(
      vi.mocked(api.searchExploreSystems).mock.calls.map(([request]) => ({
        from: request.from,
        size: request.size,
      })),
    ).toEqual([{ from: 9999, size: 1 }]);
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('canonicalizes a non-finite restored anchor as unanchored before dispatch', async () => {
    renderEnabled('page_size=1', { anchor: { ...anchorA, x: Infinity } });
    await screen.findByText('Ranked 1');
    expect(mockedPage.state.anchor).toBeNull();
    expect(mockedGoto).toHaveBeenCalledTimes(1);
    expect(mockedGoto.mock.calls[0][1].replaceState).toBe(true);
    expect(api.searchExploreSystems).toHaveBeenCalledWith(
      expect.objectContaining({ galaxy_wide: true }),
      expect.anything(),
      null,
      1,
    );
    expect(
      screen.queryByRole('button', { name: /Clear anchor/ }),
    ).not.toBeInTheDocument();
  });

  it('keeps old envelopes visibly updating during history navigation without correcting from placeholder totals', async () => {
    let finish!: (response: api.ArchetypeRankingsPage) => void;
    vi.mocked(api.getArchetypeRankings).mockImplementation((request) => {
      if (request.offset === 9)
        return new Promise((resolve) => {
          finish = resolve;
        });
      return Promise.resolve({
        ...finderPage(0, 1, 1, true),
        archetype: request.archetype,
        archetype_label: 'Manufacturing Hub',
      });
    });
    const history = renderEnabled('archetype=manufacturing_hub&page_size=1');
    await screen.findByText('Ranked 1');
    history.restore('archetype=manufacturing_hub&page_size=1&offset=9');
    await screen.findByText(/Updating…/);
    expect(screen.getByText('Ranked 1')).toBeInTheDocument();
    expect(mockedGoto).not.toHaveBeenCalled();
    expect(screen.queryByText(/No systems meet/)).not.toBeInTheDocument();
    finish({
      ...finderPage(9, 1, 10, true),
      results: [rankedRows[2]],
      archetype: 'manufacturing_hub',
      archetype_label: 'Manufacturing Hub',
    });
    await screen.findByText('Showing 1 of 10 (results 10–10)');
    expect(mockedGoto).not.toHaveBeenCalled();
  });

  it('retains the committed anchor while draft text changes and selected mode switches back to Any', async () => {
    let finishAny!: (
      page: Awaited<ReturnType<typeof api.searchExploreSystems>>,
    ) => void;
    vi.mocked(api.searchExploreSystems).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishAny = resolve;
        }),
    );
    renderEnabled('archetype=manufacturing_hub&page_size=1&offset=1', {
      anchor: anchorA,
    });
    await screen.findByText('Ranked 2');
    const input = screen.getByRole('combobox', { name: 'System name' });
    expect(input).toHaveValue('Anchor A');
    await fireEvent.input(input, { target: { value: 'Draft other star' } });
    expect(mockedPage.state.anchor).toEqual(anchorA);
    expect(mockedPage.url.searchParams.get('offset')).toBe('1');
    expect(mockedGoto).not.toHaveBeenCalled();
    expect(
      screen.getByText(/choose Any to search around Anchor A/),
    ).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('radio', { name: 'Any' }));
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenCalledWith(
        expect.objectContaining({
          reference_coords: { x: 10, y: 20, z: 30 },
          from: 0,
        }),
        expect.anything(),
        { id64: anchorA.id64, name: anchorA.name },
        1,
      ),
    );
    const retainedList = screen.getByRole('list', { name: 'System results' });
    expect(within(retainedList).getByText('Ranked 2')).toBeInTheDocument();
    expect(retainedList).not.toHaveTextContent(/fit/i);
    expect(
      within(retainedList).getByRole('button', { name: /^Ranked 2/ }),
    ).not.toHaveAccessibleName(/fit/i);
    expect(screen.getByText(/Updating…/)).toBeInTheDocument();
    finishAny(finderPage(0));
    await screen.findByText('Ranked 1');
  });

  it('clears anchor state in one push, preserves selection/detail, resets offset and restores anchor with Back', async () => {
    const history = renderEnabled(
      'page_size=1&offset=1&selected=9007199254741001&system=9007199254741002&view=cards',
      { anchor: anchorA },
    );
    await screen.findByText('Ranked 2');
    await fireEvent.click(
      screen.getByRole('button', { name: 'Clear anchor Anchor A' }),
    );
    await screen.findByText('Anchor cleared; searching galaxy-wide.');
    expect(mockedPage.state.anchor).toBeNull();
    expect(mockedPage.url.search).toBe(
      '?page_size=1&selected=9007199254741001&system=9007199254741002&view=cards',
    );
    expect(mockedGoto).toHaveBeenCalledTimes(1);
    expect(mockedGoto.mock.calls[0][1].replaceState).toBe(false);
    expect(screen.getByRole('combobox', { name: 'System name' })).toHaveFocus();
    expect(screen.getByRole('combobox', { name: 'System name' })).toHaveValue(
      '',
    );
    expect(
      screen.queryByRole('button', { name: /Clear anchor/ }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenLastCalledWith(
        expect.objectContaining({ galaxy_wide: true, from: 0 }),
        expect.anything(),
        null,
        1,
      ),
    );
    history.back();
    await screen.findByRole('button', { name: 'Clear anchor Anchor A' });
    expect(screen.getByRole('combobox', { name: 'System name' })).toHaveValue(
      'Anchor A',
    );
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenLastCalledWith(
        expect.objectContaining({
          reference_coords: { x: 10, y: 20, z: 30 },
          from: 1,
        }),
        expect.anything(),
        { id64: anchorA.id64, name: anchorA.name },
        1,
      ),
    );
  });

  it('keeps selected archetype and tier when clearing its remembered anchor', async () => {
    renderEnabled(
      'archetype=manufacturing_hub&min-tier=A&page_size=1&offset=1',
      { anchor: anchorA },
    );
    await screen.findByText('Ranked 2');
    await fireEvent.click(
      screen.getByRole('button', { name: 'Clear anchor Anchor A' }),
    );
    await waitFor(() => expect(mockedPage.state.anchor).toBeNull());
    expect(mockedPage.url.search).toBe(
      '?archetype=manufacturing_hub&min-tier=A&page_size=1',
    );
    expect(api.searchExploreSystems).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: 'Minimum tier' })).toHaveValue(
      'A',
    );
  });

  it('exposes the Clear anchor button with no automated accessibility violations', async () => {
    renderEnabled('page_size=1', { anchor: anchorA });
    const clear = await screen.findByRole('button', {
      name: 'Clear anchor Anchor A',
    });
    expect(clear).toHaveTextContent('Clear');
    expect(clear).toHaveAttribute('type', 'button');
    expect(clear.tabIndex).toBe(0);
    const result = await axe.run(clear.parentElement!, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });

  it('commits anchor B and restores anchor A coordinates, input, selection and offset with Back', async () => {
    vi.mocked(api.autocompleteSystems).mockResolvedValue({
      results: [anchorB],
    });
    const history = renderEnabled(
      'page_size=1&offset=1&selected=9007199254740993',
      { anchor: anchorA },
    );
    await screen.findByText('Ranked 2');
    await fireEvent.input(
      screen.getByRole('combobox', { name: 'System name' }),
      { target: { value: 'Anchor B' } },
    );
    await fireEvent.click(
      await screen.findByRole('option', { name: /Anchor B/ }),
    );
    await waitFor(() => expect(mockedPage.state.anchor).toEqual(anchorB));
    expect(mockedPage.url.search).toBe(
      '?page_size=1&selected=9007199254740994',
    );
    history.back();
    await screen.findByRole('button', { name: 'Clear anchor Anchor A' });
    expect(screen.getByRole('combobox', { name: 'System name' })).toHaveValue(
      'Anchor A',
    );
    expect(mockedPage.url.search).toBe(
      '?page_size=1&offset=1&selected=9007199254740993',
    );
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenLastCalledWith(
        expect.objectContaining({
          reference_coords: { x: 10, y: 20, z: 30 },
          from: 1,
        }),
        expect.anything(),
        { id64: anchorA.id64, name: anchorA.name },
        1,
      ),
    );
  });

  it('result and Babylon picks commit lossless passive selection without opening detail', async () => {
    renderEnabled('page_size=1&view=cards', { anchor: anchorA });
    await screen.findByText('Ranked 1');
    await fireEvent.click(
      screen.getByRole('button', { name: /Ranked 1.*9007199254741001/ }),
    );
    await waitFor(() =>
      expect(mockedPage.url.searchParams.get('selected')).toBe(
        rankedRows[0].id64,
      ),
    );
    expect(mockedPage.url.searchParams.has('system')).toBe(false);
    expect(mockedPage.state.anchor).toEqual(anchorA);
    expect(mockedPage.url.searchParams.get('view')).toBe('cards');
    await waitFor(() => expect(runtimeAdapter.create).toHaveBeenCalled());
    emitRuntime({
      type: 'TARGET_PICKED',
      target: { kind: 'system', systemId64: rankedRows[1].id64 },
    });
    await waitFor(() =>
      expect(mockedPage.url.searchParams.get('selected')).toBe(
        rankedRows[1].id64,
      ),
    );
    expect(mockedPage.url.searchParams.has('system')).toBe(false);
    expect(mockedPage.state.anchor).toEqual(anchorA);
  });

  it('keeps a selected page point once across pagination without refetching its known coordinates', async () => {
    renderEnabled('page_size=1');
    await expectPage(0);
    await fireEvent.click(
      screen.getByRole('button', { name: /Ranked 1.*9007199254741001/ }),
    );
    await waitFor(() =>
      expect(currentScene().selection).toEqual([
        { kind: 'system', systemId64: rankedRows[0].id64 },
      ]),
    );
    expect(scenePointIds()).toEqual([rankedRows[0].id64]);
    await fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await screen.findByText('Ranked 2');
    await waitFor(() =>
      expect(scenePointIds().sort()).toEqual(
        [rankedRows[0].id64, rankedRows[1].id64].sort(),
      ),
    );
    expect(api.getSystem).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(scenePointIds()).toEqual([rankedRows[0].id64]));
  });

  it('hydrates a clean off-page selection even when the catalogue arrives before rankings', async () => {
    let finishRankings!: (page: api.ArchetypeRankingsPage) => void;
    vi.mocked(api.getArchetypeRankings).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishRankings = resolve;
        }),
    );
    vi.mocked(api.getCatalogueViewportSystems).mockResolvedValue({
      systems: [{ ...anchorA, populated: false }],
      truncated: false,
    });
    renderEnabled(
      `archetype=manufacturing_hub&page_size=1&offset=1&selected=${anchorA.id64}`,
    );
    // The normal wide catalogue includes every Product fixture system. Hold
    // rankings pending until that response has reached the real component.
    await screen.findByRole('heading', { name: 'Anchor A' });
    expect(api.getSystem).not.toHaveBeenCalled();
    finishRankings({
      ...finderPage(1, 1, 3, true),
      archetype: 'manufacturing_hub',
      archetype_label: 'Manufacturing Hub',
    });
    await screen.findByText('Ranked 2');
    await waitFor(() =>
      expect(api.getSystem).toHaveBeenCalledExactlyOnceWith(
        anchorA.id64,
        expect.anything(),
      ),
    );
    expect(
      within(screen.getByRole('list', { name: 'System results' })).queryByText(
        'Anchor A',
      ),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        currentScene().contributions.filter(
          (contribution) => contribution.id === 'finder-selection',
        ),
      ).toHaveLength(1),
    );
    expect(currentScene().selection).toEqual([
      { kind: 'system', systemId64: anchorA.id64 },
    ]);
    expect(mockedPage.url.searchParams.get('selected')).toBe(anchorA.id64);
    expect(mockedPage.url.searchParams.has('system')).toBe(false);
  });

  it.each([
    {
      label: 'finite coordinates',
      id64: anchorA.id64,
      x: 50,
      y: 60,
      z: 70,
      visible: true,
    },
    {
      label: 'missing coordinates',
      id64: anchorA.id64,
      x: null,
      y: null,
      z: null,
      visible: false,
    },
    {
      label: 'nonfinite coordinates',
      id64: anchorA.id64,
      x: Infinity,
      y: 1,
      z: 2,
      visible: false,
    },
    {
      label: 'legacy origin',
      id64: anchorA.id64,
      x: 0,
      y: 0,
      z: 0,
      visible: false,
    },
    {
      label: 'Sol at the origin',
      id64: parseId64('10477373803'),
      x: 0,
      y: 0,
      z: 0,
      visible: true,
    },
  ])(
    'reconstructs selection from getSystem with $label without inventing a point',
    async ({ id64, x, y, z, visible }) => {
      mockRankedPages(0);
      vi.mocked(api.getSystem).mockResolvedValue({
        id64,
        name: 'Reconstructed selection',
        lifecycleState: 'ACTIVE',
        x,
        y,
        z,
        sourceBodyCount: null,
        loadedBodyCount: 0,
        sourceUpdatedAt: null,
        bodies: [],
        stations: [],
      } as api.SystemDetail);
      renderEnabled(`page_size=1&selected=${id64}`);
      await screen.findByRole('heading', { name: 'Reconstructed selection' });
      expect(api.getSystem).toHaveBeenCalledWith(id64, expect.anything());
      await waitFor(() =>
        expect(currentScene().selection).toEqual([
          { kind: 'system', systemId64: id64 },
        ]),
      );
      expect(scenePointIds()).toEqual(visible ? [id64] : []);
      expect(mockedPage.url.searchParams.get('selected')).toBe(id64);
      expect(mockedPage.url.searchParams.has('system')).toBe(false);
    },
  );

  it('retains passive selection and an empty point set when getSystem fails', async () => {
    mockRankedPages(0);
    vi.mocked(api.getSystem).mockRejectedValue(
      new api.ApiError(503, '/api/system', {}),
    );
    renderEnabled(`page_size=1&selected=${anchorA.id64}`);
    await waitFor(() => expect(api.getSystem).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(currentScene().selection).toEqual([
        { kind: 'system', systemId64: anchorA.id64 },
      ]),
    );
    expect(
      screen.getByRole('heading', { name: `System ${anchorA.id64}` }),
    ).toBeInTheDocument();
    expect(scenePointIds()).toEqual([]);
    expect(mockedPage.url.searchParams.get('selected')).toBe(anchorA.id64);
  });

  it('ignores a late selected-point response after selection changes', async () => {
    mockRankedPages(0);
    let finishA!: (value: api.SystemDetail) => void;
    vi.mocked(api.getSystem).mockImplementation((id64) => {
      if (id64 === anchorA.id64)
        return new Promise((resolve) => {
          finishA = resolve;
        });
      return Promise.resolve({
        id64,
        name: 'Selection B',
        x: 40,
        y: 50,
        z: 60,
        lifecycleState: 'ACTIVE',
        sourceBodyCount: null,
        loadedBodyCount: 0,
        sourceUpdatedAt: null,
        bodies: [],
        stations: [],
      });
    });
    const history = renderEnabled(`page_size=1&selected=${anchorA.id64}`);
    await waitFor(() =>
      expect(api.getSystem).toHaveBeenCalledWith(
        anchorA.id64,
        expect.anything(),
      ),
    );
    history.restore(`page_size=1&selected=${anchorB.id64}`);
    await screen.findByRole('heading', { name: 'Selection B' });
    finishA({
      id64: anchorA.id64,
      name: 'Late A',
      x: 1,
      y: 2,
      z: 3,
      lifecycleState: 'ACTIVE',
      sourceBodyCount: null,
      loadedBodyCount: 0,
      sourceUpdatedAt: null,
      bodies: [],
      stations: [],
    });
    await waitFor(() => expect(scenePointIds()).toEqual([anchorB.id64]));
    expect(
      screen.queryByRole('heading', { name: 'Late A' }),
    ).not.toBeInTheDocument();
    expect(currentScene().selection).toEqual([
      { kind: 'system', systemId64: anchorB.id64 },
    ]);
  });

  it('clears URL-owned selection when a history entry omits selected while preserving explicit detail', async () => {
    const history = renderEnabled(`page_size=1&selected=${rankedRows[0].id64}`);
    await waitFor(() =>
      expect(currentScene().selection).toEqual([
        { kind: 'system', systemId64: rankedRows[0].id64 },
      ]),
    );
    history.restore(`page_size=1&system=${rankedRows[0].id64}`);
    await waitFor(() => expect(currentScene().selection).toEqual([]));
    expect(mockedPage.url.searchParams.get('system')).toBe(rankedRows[0].id64);
  });

  it('carries the query and committed anchor on result Inspect navigation', async () => {
    renderEnabled(
      'archetype=manufacturing_hub&min-tier=A&page_size=1&offset=1',
      { anchor: anchorA },
    );
    await screen.findByText('Ranked 2');
    const origin = mockedPage.url.searchParams.toString();
    mockedGoto.mockResolvedValueOnce(undefined);
    await fireEvent.click(
      screen.getByRole('link', { name: 'Inspect Ranked 2' }),
    );
    const destination = new URL(mockedGoto.mock.calls[0][0], mockedPage.url);
    expect(destination.pathname).toBe('/inspect');
    expect(destination.searchParams.get('from')).toBe(origin);
    expect(destination.searchParams.get('system')).toBe(rankedRows[1].id64);
    expect(mockedGoto.mock.calls[0][1].state.anchor).toEqual(anchorA);
  });

  it.each([
    {
      body: { detail: { reason: 'finder_products_not_ready' } },
      heading: 'Ranking data not ready',
    },
    {
      body: { reason: 'finder_products_not_ready' },
      heading: 'Ranking data not ready',
    },
    {
      body: { detail: 'finder_products_not_ready' },
      heading: 'Ranking temporarily unavailable',
    },
    {
      body: 'finder_products_not_ready',
      heading: 'Ranking temporarily unavailable',
    },
  ])(
    'selects readiness copy only from the typed reason: $heading',
    async ({ body, heading }) => {
      vi.mocked(api.getArchetypeRankings).mockRejectedValue(
        new api.ApiError(503, '/api/archetypes/rankings', body),
      );
      renderEnabled('archetype=manufacturing_hub&page_size=1');
      await screen.findByRole('heading', { name: heading });
      expect(screen.queryByText(/No systems meet/)).not.toBeInTheDocument();
      expect(
        within(
          screen.getByRole('region', {
            name: 'Galaxy-wide Manufacturing Hub ranking',
          }),
        ).getByRole('button', { name: 'Retry' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Choose Any' }),
      ).toBeInTheDocument();
    },
  );

  it('preserves picker and pagination focus instead of focusing results on ordinary refetches', async () => {
    renderEnabled('page_size=1', { anchor: anchorA });
    await expectPage(0);
    const next = screen.getByRole('button', { name: 'Next' });
    next.focus();
    await fireEvent.click(next);
    await screen.findByText('Ranked 2');
    await waitFor(() => expect(next).toHaveFocus());
    const picker = screen.getByRole('radio', { name: 'Manufacturing Hub' });
    picker.focus();
    await fireEvent.click(picker);
    await waitFor(() => expect(api.getArchetypeRankings).toHaveBeenCalled());
    expect(picker).toHaveFocus();
  });

  it('focuses the first result only after an explicit new Any anchor', async () => {
    vi.mocked(api.autocompleteSystems).mockResolvedValue({
      results: [anchorA],
    });
    renderEnabled('page_size=1');
    await expectPage(0);
    const input = screen.getByRole('combobox', { name: 'System name' });
    input.focus();
    await fireEvent.input(input, { target: { value: 'Anchor A' } });
    await fireEvent.click(
      await screen.findByRole('option', { name: /Anchor A/ }),
    );
    await waitFor(() =>
      expect(
        within(screen.getByRole('list', { name: 'System results' })).getByRole(
          'button',
          { name: /Ranked 1.*9007199254741001/ },
        ),
      ).toHaveFocus(),
    );
    expect(mockedPage.state.anchor).toEqual(anchorA);
  });

  it.each(['during', 'after', 'first after'] as const)(
    'bounds initial overview work when density arrives %s its flight',
    async (densityTiming) => {
      const { createBabylonSession } = await vi.importActual<
        typeof import('$lib/spatial/babylon/adapter')
      >('$lib/spatial/babylon/adapter');
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
      // Preserve the real overview extent and validated region contribution,
      // with simple bands so constructor counts do not require production-sized
      // boundary geometry. The adapter and camera state machine remain real.
      const regions = galaxyRegions.buildGalaxyRegionsPayload(
        {
          version: 1,
          origin: { x: -49_985, z: -24_105 },
          pixel_scale: 49.34939759036145,
          regions: ['', ...galaxyRegions.GALAXY_REGION_NAMES],
          regionmap: Array.from({ length: 2_048 }, (_, row) => [
            [2_048, row === 0 ? 0 : Math.min(42, Math.floor(row / 49) + 1)],
          ]),
        },
        galaxyRegions.GALAXY_REGION_SOURCE_SHA256,
      );
      let finishRegions!: (value: galaxyRegions.GalaxyRegionsPayload) => void;
      vi.spyOn(
        galaxyRegions,
        'fetchAuthoritativeGalaxyRegions',
      ).mockImplementation(
        () => new Promise((resolve) => (finishRegions = resolve)),
      );
      vi.spyOn(galaxyNebulae, 'fetchGalaxyNebulae').mockRejectedValue(
        new Error('No nebulae in this fixture'),
      );
      let finishDensity!: (value: api.MapHeatmapResponse) => void;
      const nextDensity = new Promise<api.MapHeatmapResponse>(
        (resolve) => (finishDensity = resolve),
      );
      vi.mocked(api.getMapHeatmap).mockImplementation((request) =>
        densityTiming === 'first after'
          ? nextDensity
          : request.voxel_size === 590
            ? Promise.resolve(pyramidFixture)
            : densityTiming === 'during'
              ? Promise.resolve(coarsePyramidFixture)
              : nextDensity,
      );
      vi.stubGlobal('matchMedia', () => ({ matches: false }));

      const engine = new NullEngine();
      let animationTime = 0;
      const session = createBabylonSession(
        engine,
        'WEBGL2',
        () => animationTime,
      );
      const events = vi.fn<(event: RuntimeEvent) => void>();
      const sceneCreated = vi.fn();
      engine.onNewSceneAddedObservable.add((scene) => {
        sceneCreated();
        // NullEngine cannot provide GPU readiness; count actual scene creation
        // without shader warmup or drawing, and advance real camera frames below.
        vi.spyOn(scene, 'render').mockImplementation(() => undefined);
        vi.spyOn(scene, 'isReady').mockReturnValue(true);
      });
      const frames = new Map<number, () => void>();
      let nextFrame = 0;
      runtimeAdapter.create.mockImplementation(
        (_canvas, onStatus: (status: SpatialRuntimeStatus) => void) => {
          const runtime = createManagedSpatialRuntime(
            {
              createWebGpu: async () => null,
              createWebGl2: () => session,
            },
            onStatus,
            {
              request(callback) {
                frames.set(++nextFrame, callback);
                return nextFrame;
              },
              cancel(handle) {
                frames.delete(handle);
              },
            },
          );
          runtime.subscribe(events);
          vi.spyOn(runtime, 'dispatch');
          return runtime;
        },
      );
      const work = () => {
        const runtime = runtimeAdapter.create.mock.results.at(-1)!.value;
        const commands = runtime.dispatch.mock.calls.map(
          ([command]: [RuntimeCommand]) => command,
        ) as RuntimeCommand[];
        return {
          loads: commands.filter((command) => command.type === 'LOAD_SCENE')
            .length,
          scenes: sceneCreated.mock.calls.length,
          transitions: commands.filter(
            (command) =>
              command.type === 'FLY_TO' ||
              (command.type === 'SET_CAMERA' && command.transition),
          ).length,
        };
      };
      const finishFrames = async () => {
        for (let index = 0; frames.size && index < 150; index += 1) {
          animationTime += 1_000;
          const callbacks = [...frames.values()];
          frames.clear();
          callbacks.forEach((callback) => callback());
          await tick();
        }
        expect(frames.size).toBe(0);
      };

      const navigation = renderEnabled();
      await vi.waitFor(
        () => {
          expect(screen.getByText('Ranked 1')).toBeInTheDocument();
          if (densityTiming !== 'first after')
            expect(screen.getByText(/2 density cells/)).toBeInTheDocument();
          expect(scenePointIds()).toEqual([rankedRows[0].id64]);
        },
        { interval: 1 },
      );
      await finishFrames();
      expect(work()).toEqual({ loads: 1, scenes: 1, transitions: 0 });
      finishRegions(regions);
      await vi.waitFor(() => expect(work().transitions).toBe(1), {
        interval: 1,
      });
      expect(work()).toEqual({ loads: 2, scenes: 2, transitions: 1 });

      vi.mocked(api.searchExploreSystems).mockResolvedValueOnce({
        ...finderPage(0),
        results: [rankedRows[1]],
      });
      await queryClient.invalidateQueries({
        queryKey: [...queryKeys.all, 'explore', 'results'],
      });
      await vi.waitFor(
        () => expect(screen.getByText('Ranked 2')).toBeInTheDocument(),
        { interval: 1 },
      );
      expect(work()).toEqual({ loads: 2, scenes: 2, transitions: 1 });
      // The 180 ms viewport debounce fires during the 650 ms overview flight.
      // Both a prompt density reply and one arriving after settle must stay
      // within the pre-part-3 scene/command budget.
      await vi.advanceTimersByTimeAsync(180);
      await finishFrames();
      if (densityTiming !== 'during') finishDensity(coarsePyramidFixture);
      await vi.advanceTimersByTimeAsync(180);
      await finishFrames();
      expect(scenePointIds()).toEqual([rankedRows[1].id64]);
      expect(work()).toEqual({ loads: 3, scenes: 3, transitions: 1 });
      expect(
        events.mock.calls.filter(
          ([event]) => event.type === 'TRANSITION_FINISHED',
        ),
      ).toHaveLength(1);
      expect(currentScene().camera.distanceLy).toBeGreaterThan(100_000);
      expect(
        engine.scenes.at(-1)?.getMeshByName('catalogue-density-cells')?.metadata
          .spatialLayer.renderedCellCount,
      ).toBe(1);
      expect(api.getCatalogueViewportSystems).toHaveBeenCalledTimes(1);
      expect(api.getCatalogueViewportSystems).toHaveBeenCalledWith(
        expect.objectContaining({ limit: 8_000 }),
        expect.anything(),
      );
      // Even a first density response after settle must keep the same overlay
      // order as the parent's next scene. Selection can then update its marker
      // in place instead of rebuilding every mesh after a late density patch.
      const settledCamera = currentScene().camera;
      navigation.restore(`page_size=1&selected=${rankedRows[1].id64}`);
      await vi.waitFor(
        () =>
          expect(currentScene().selection).toContainEqual({
            kind: 'system',
            systemId64: rankedRows[1].id64,
          }),
        { interval: 1 },
      );
      await finishFrames();
      expect(work()).toEqual({ loads: 4, scenes: 3, transitions: 1 });
      expect(currentScene().camera).toEqual(settledCamera);
      expect(
        engine.scenes.at(-1)?.getMeshByName('selected-system-marker'),
      ).toBeTruthy();
    },
  );

  it('keeps F4 results and the settled selection camera when a refetch arrives during fly-to', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    renderEnabled('page_size=2', { anchor: anchorA });
    await screen.findByText('Showing 2 of 3 (results 1–2)');
    await waitFor(() =>
      expect(scenePointIds()).toEqual([rankedRows[0].id64, rankedRows[1].id64]),
    );

    const runtime = runtimeAdapter.create.mock.results.at(-1)!.value;
    // Match the real adapter's synchronous camera receipt on scene replacement.
    // The test controls the animation's completion while Finder data is pending.
    runtime.dispatch.mockImplementation((command: RuntimeCommand) => {
      if (command.type === 'LOAD_SCENE')
        emitRuntime({ type: 'CAMERA_CHANGED', camera: command.scene.camera });
      return { status: 'executed' as const };
    });
    const overviewCamera = {
      ...currentScene().camera,
      distanceLy: 118_000,
      revision: 10,
    };
    emitRuntime({ type: 'CAMERA_CHANGED', camera: overviewCamera });
    const target = {
      kind: 'system' as const,
      systemId64: rankedRows[0].id64,
    };
    await fireEvent.click(
      within(screen.getByRole('list', { name: 'System results' })).getByRole(
        'button',
        { name: /Ranked 1.*9007199254741001/ },
      ),
    );
    await waitFor(() =>
      expect(runtime.dispatch).toHaveBeenCalledWith({
        type: 'FLY_TO',
        target,
        reducedMotion: false,
      }),
    );
    expect(mockedPage.url.searchParams.get('selected')).toBe(target.systemId64);
    expect(mockedPage.state.anchor).toEqual(anchorA);

    let finish!: (
      response: Awaited<ReturnType<typeof api.searchExploreSystems>>,
    ) => void;
    vi.mocked(api.searchExploreSystems).mockImplementationOnce(
      () => new Promise((resolve) => (finish = resolve)),
    );
    const refetch = queryClient.invalidateQueries({
      queryKey: [...queryKeys.all, 'explore', 'results'],
    });
    await screen.findByText(/Updating…/);
    expect(scenePointIds()).toEqual([rankedRows[0].id64, rankedRows[1].id64]);
    expect(screen.getByText('Ranked 2')).toBeInTheDocument();
    finish({
      ...finderPage(0, 2),
      results: [rankedRows[0], rankedRows[2]],
    });
    await refetch;
    await screen.findByText('Ranked 3');

    const settledCamera = {
      ...overviewCamera,
      focusLy: { x: 10, y: 1, z: 20 },
      distanceLy: 60,
      revision: 11,
    };
    emitRuntime({ type: 'CAMERA_CHANGED', camera: settledCamera });
    emitRuntime({ type: 'TRANSITION_FINISHED', target });

    await waitFor(() => expect(currentScene().camera).toEqual(settledCamera));
    expect(scenePointIds()).toEqual([rankedRows[0].id64, rankedRows[2].id64]);
    expect(currentScene().selection).toContainEqual(target);
    expect(document.querySelector('[data-camera-distance]')).toHaveAttribute(
      'data-camera-distance',
      '60',
    );
    expect(
      document.querySelector(
        `[data-map-label-key="system:${target.systemId64}"]`,
      ),
    ).toHaveTextContent('Ranked 1');
  });

  it('cancels pending anchor autofocus when the user changes archetype before the anchored response', async () => {
    let finishAnchor!: (
      response: Awaited<ReturnType<typeof api.searchExploreSystems>>,
    ) => void;
    vi.mocked(api.searchExploreSystems).mockImplementation((request) =>
      request.reference_coords
        ? new Promise((resolve) => {
            finishAnchor = resolve;
          })
        : Promise.resolve(finderPage(0)),
    );
    vi.mocked(api.autocompleteSystems).mockResolvedValue({
      results: [anchorA],
    });
    renderEnabled('page_size=1');
    await expectPage(0);
    const input = screen.getByRole('combobox', { name: 'System name' });
    input.focus();
    await fireEvent.input(input, { target: { value: 'Anchor A' } });
    await fireEvent.click(
      await screen.findByRole('option', { name: /Anchor A/ }),
    );
    await waitFor(() =>
      expect(api.searchExploreSystems).toHaveBeenCalledTimes(2),
    );
    const picker = screen.getByRole('radio', { name: 'Manufacturing Hub' });
    picker.focus();
    await fireEvent.click(picker);
    await waitFor(() => expect(api.getArchetypeRankings).toHaveBeenCalled());
    finishAnchor(finderPage(0));
    await waitFor(() => expect(picker).toHaveFocus());
    mockRankedPages();
    const any = screen.getByRole('radio', { name: 'Any' });
    any.focus();
    await fireEvent.click(any);
    await waitFor(() =>
      expect(
        screen.getByRole('region', { name: 'Near Anchor A' }),
      ).toHaveAttribute('aria-busy', 'false'),
    );
    expect(any).toHaveFocus();
  });
});

describe('ExploreWorkspace travel heatmap (V3 journal store)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    stubRuntime();
    mockFacadeDefaults();
    vi.mocked(api.getMapHeatmap).mockResolvedValue(legacyFixture);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function signIn(): Promise<void> {
    vi.mocked(api.getAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        account_id: 'account-a',
        commander_name: 'CMDR Test',
        is_owner: false,
      },
    });
    await auth.bootstrap();
  }

  async function showTravel(): Promise<HTMLElement> {
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Show my travel heatmap' }),
    );
    return screen.findByText(
      (_, element) =>
        element?.hasAttribute('data-commander-history-state') ?? false,
    );
  }

  it('asks a signed-out visitor to sign in and never requests travel', async () => {
    await auth.bootstrap();
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/exact stars/);

    const status = await showTravel();

    await waitFor(() =>
      expect(status).toHaveAttribute(
        'data-commander-history-state',
        'signed-out',
      ),
    );
    expect(
      screen.getByRole('link', { name: 'Sign in and import your journals' }),
    ).toHaveAttribute('href', '/account');
    expect(api.getCommanderTravelHeatmap).not.toHaveBeenCalled();
  });

  it('offers a retry, not a sign-in prompt, when the account check fails', async () => {
    vi.mocked(api.getAuthSession).mockRejectedValueOnce(
      new api.ApiError(503, '/api/v1/auth/session', {}),
    );
    await auth.bootstrap();
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/exact stars/);

    const status = await showTravel();

    await waitFor(() =>
      expect(status).toHaveAttribute(
        'data-commander-history-state',
        'auth-error',
      ),
    );
    expect(
      screen.queryByRole('link', { name: 'Sign in and import your journals' }),
    ).not.toBeInTheDocument();
    expect(api.getCommanderTravelHeatmap).not.toHaveBeenCalled();
    await fireEvent.click(
      Array.from(status.querySelectorAll('button')).find(
        (button) => button.textContent === 'Retry',
      )!,
    );
    await waitFor(() =>
      expect(status).toHaveAttribute(
        'data-commander-history-state',
        'signed-out',
      ),
    );
  });

  it('reads the signed-in account travel from the V3 route and counts it', async () => {
    await signIn();
    vi.mocked(api.getCommanderTravelHeatmap).mockResolvedValue({
      mode: 'markers',
      visits: [
        {
          kind: 'marker',
          systemId64: null,
          systemName: 'Sol',
          x: 0,
          y: 0,
          z: 0,
          visitCount: 3,
          firstVisitedAt: '2026-01-01T00:00:00Z',
          lastVisitedAt: '2026-01-02T00:00:00Z',
          cellSizeLy: null,
        },
      ],
      count: 1,
      truncated: false,
    });
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/exact stars/);

    const status = await showTravel();

    await waitFor(() =>
      expect(status).toHaveAttribute('data-commander-history-state', 'ready'),
    );
    expect(status).toHaveAttribute('data-commander-history-count', '1');
    expect(status.textContent).toMatch(/1 visited\s+systems/u);
    const [request, distance] = vi.mocked(api.getCommanderTravelHeatmap).mock
      .calls[0]!;
    expect(request).toEqual(
      expect.objectContaining({
        minX: expect.any(Number),
        limit: expect.any(Number),
      }),
    );
    expect(distance).toBeGreaterThan(0);
  });

  it('shows an honest empty state and a sign-in prompt on a 401', async () => {
    await signIn();
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/exact stars/);
    const status = await showTravel();
    await waitFor(() =>
      expect(status).toHaveAttribute('data-commander-history-state', 'empty'),
    );
    expect(status.textContent).toContain(
      'No imported journal travel in this view',
    );
    cleanup();
    queryClient.clear();

    vi.mocked(api.getCommanderTravelHeatmap).mockRejectedValue(
      new api.ApiError(401, '/api/v1/journal/travel-heatmap', {}),
    );
    render(ExploreWorkspaceTestHost);
    await screen.findByText(/exact stars/);
    const expired = await showTravel();
    await waitFor(() =>
      expect(expired).toHaveAttribute(
        'data-commander-history-state',
        'signed-out',
      ),
    );
    expect(api.getCommanderTravelHeatmap).toHaveBeenCalledTimes(2);
  });
});
