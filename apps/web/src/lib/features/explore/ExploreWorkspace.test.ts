import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import ExploreWorkspaceTestHost from './ExploreWorkspaceTestHost.svelte';

vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return {
    ...original,
    autocompleteSystems: vi.fn(),
    searchExploreSystems: vi.fn(),
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

describe('ExploreWorkspace density cross-fade wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
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
    vi.mocked(api.autocompleteSystems).mockResolvedValue({ results: [] });
    vi.mocked(api.searchExploreSystems).mockResolvedValue({ results: [] });
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
