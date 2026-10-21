import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import { FINDER_F4_ENABLED } from '$lib/config';
import ExploreWorkspaceTestHost from './ExploreWorkspaceTestHost.svelte';

const { mockedPage, mockedGoto } = vi.hoisted(() => ({
  mockedPage: { url: new URL('http://localhost/explore') },
  mockedGoto: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));
vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return {
    ...original,
    autocompleteSystems: vi.fn(),
    searchExploreSystems: vi.fn(),
    getArchetypeRankings: vi.fn(),
    getCatalogueViewportSystems: vi.fn(),
    getCommanderViewportVisits: vi.fn(),
    getMapHeatmap: vi.fn(),
  };
});

const runtimeAdapter = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('$lib/spatial/babylon/adapter', () => ({
  createBabylonSpatialRuntime: runtimeAdapter.create,
}));

const pyramidFixture: api.MapHeatmapResponse = {
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
  runtimeAdapter.create.mockImplementation(() => ({
    getStatus: () => ({ state: 'created' as const }),
    start: vi.fn(async () => ({
      state: 'ready' as const,
      backend: 'WEBGL2' as const,
    })),
    dispatch: vi.fn(() => ({ status: 'executed' as const })),
    subscribe: vi.fn(() => vi.fn()),
    resize: vi.fn(),
    dispose: vi.fn(),
  }));
}

function mockFacadeDefaults(): void {
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
  vi.mocked(api.getCommanderViewportVisits).mockResolvedValue({
    mode: 'markers',
    visits: [],
    count: 0,
    truncated: false,
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
