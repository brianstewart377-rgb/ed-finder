import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useMapLayers } from './useMapLayers';
import { api } from '@/lib/api';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

describe('useMapLayers', () => {
  it('does not fetch disabled layers', () => {
    const mapRegionsSpy = vi.spyOn(api, 'mapRegions');
    const mapClusterHullsSpy = vi.spyOn(api, 'mapClusterHulls');
    const mapHeatmapSpy = vi.spyOn(api, 'mapHeatmap');
    const mapTimelineSpy = vi.spyOn(api, 'mapTimeline');

    const { result } = renderHook(() => useMapLayers(), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isError).toBe(false);
    expect(mapRegionsSpy).not.toHaveBeenCalled();
    expect(mapClusterHullsSpy).not.toHaveBeenCalled();
    expect(mapHeatmapSpy).not.toHaveBeenCalled();
    expect(mapTimelineSpy).not.toHaveBeenCalled();
  });

  it('fetches enabled regions', async () => {
    vi.spyOn(api, 'mapRegions').mockResolvedValue({
      regions: [{ id: 1, name: 'Inner Orion Spur', x: 0, y: 0, z: 0, system_count: 42 }],
      total_regions: 1,
    });

    const { result } = renderHook(
      () => useMapLayers({ regions: { enabled: true } }),
      { wrapper },
    );

    expect(result.current.regions.isLoading).toBe(true);

    await waitFor(() => expect(result.current.regions.isLoading).toBe(false));

    expect(result.current.regions.data?.total_regions).toBe(1);
    expect(result.current.regions.data?.regions[0].name).toBe('Inner Orion Spur');
    expect(result.current.regions.isError).toBe(false);
  });

  it('fetches heatmap with stable query key and options', async () => {
    vi.spyOn(api, 'mapHeatmap').mockResolvedValue({
      voxel_size: 200,
      voxel_bucket: 200,
      economy: null,
      cells: [{ cx: 0, cy: 0, cz: 0, n: 10, avg_score: 75, max_score: 90 }],
      count: 1,
    });

    const { result } = renderHook(
      () => useMapLayers({
        heatmap: { enabled: true, voxel_size: 200, min_systems: 5, economy: 'Refinery' },
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.heatmap.isLoading).toBe(false));

    expect(result.current.heatmap.data?.count).toBe(1);
    expect(result.current.heatmap.data?.cells[0].avg_score).toBe(75);
    expect(api.mapHeatmap).toHaveBeenCalledWith({
      voxel_size: 200,
      min_systems: 5,
      economy: 'Refinery',
    });
  });

  it('fetches clusters and timeline when enabled', async () => {
    vi.spyOn(api, 'mapClusterHulls').mockResolvedValue({
      clusters: [],
      count: 0,
      cached: false,
    });
    vi.spyOn(api, 'mapTimeline').mockResolvedValue({
      bucket: 'month',
      points: [{ date: '2024-01-01', count: 100 }],
      total: 100,
    });

    const { result } = renderHook(
      () => useMapLayers({
        clusters: { enabled: true, min_count: 3, max_hulls: 100 },
        timeline: { enabled: true, bucket: 'month' },
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.clusters.isLoading).toBe(false));
    await waitFor(() => expect(result.current.timeline.isLoading).toBe(false));

    expect(result.current.clusters.data?.count).toBe(0);
    expect(result.current.timeline.data?.total).toBe(100);
    expect(api.mapClusterHulls).toHaveBeenCalledWith({ min_count: 3, max_hulls: 100 });
    expect(api.mapTimeline).toHaveBeenCalledWith({ bucket: 'month' });
  });

  it('exposes error state when a layer fails', async () => {
    vi.spyOn(api, 'mapRegions').mockRejectedValue(new Error('network failure'));

    const { result } = renderHook(
      () => useMapLayers({ regions: { enabled: true } }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.regions.isError).toBe(true));

    expect(result.current.regions.error?.message).toBe('network failure');
    expect(result.current.isError).toBe(true);
  });

  it('respects custom staleTime', async () => {
    vi.spyOn(api, 'mapRegions').mockResolvedValue({
      regions: [],
      total_regions: 0,
    });

    const { result } = renderHook(
      () => useMapLayers({
        regions: { enabled: true },
        staleTimeMs: 10_000,
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.regions.isLoading).toBe(false));
    expect(result.current.regions.data).toBeTruthy();
  });
});
