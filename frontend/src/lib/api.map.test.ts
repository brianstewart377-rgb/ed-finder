import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  getMapRegions,
  getMapClusterHulls,
  getMapHeatmap,
  getMapTimeline,
} from './api';

describe('map API helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('api.mapRegions calls /api/map/regions', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          regions: [{ id: 1, name: 'Inner Orion Spur', x: 0, y: 0, z: 0, system_count: 42 }],
          total_regions: 1,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const res = await api.mapRegions();
    expect(res.total_regions).toBe(1);
    expect(res.regions[0].name).toBe('Inner Orion Spur');
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/regions',
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'application/json',
          'Content-Type': 'application/json',
        }),
      }),
    );
  });

  it('api.mapClusterHulls calls /api/map/clusters/hulls with query params', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ clusters: [], count: 0, cached: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapClusterHulls({ min_count: 5, max_hulls: 100 });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/clusters/hulls?min_count=5&max_hulls=100',
      expect.anything(),
    );
  });

  it('api.mapClusterHulls omits empty query string', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ clusters: [], count: 0, cached: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapClusterHulls();
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/clusters/hulls',
      expect.anything(),
    );
  });

  it('api.mapHeatmap calls /api/map/heatmap with query params', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          voxel_size: 200,
          voxel_bucket: 200,
          economy: null,
          cells: [{ cx: 0, cy: 0, cz: 0, n: 10, avg_score: 75, max_score: 90 }],
          count: 1,
          max_cells: 50_000,
          truncated: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapHeatmap({ voxel_size: 200, min_systems: 5, max_cells: 500, economy: 'Refinery' });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/heatmap?voxel_size=200&min_systems=5&max_cells=500&economy=Refinery',
      expect.anything(),
    );
  });

  it('api.mapHeatmap omits null economy', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          voxel_size: 200,
          voxel_bucket: 200,
          economy: null,
          cells: [],
          count: 0,
          max_cells: 50_000,
          truncated: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapHeatmap({ voxel_size: 200 });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/heatmap?voxel_size=200',
      expect.anything(),
    );
  });

  it('api.mapTimeline calls /api/map/timeline with bucket param', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          bucket: 'month',
          points: [{ date: '2024-01-01', count: 100 }],
          total: 100,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapTimeline({ bucket: 'month' });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/timeline?bucket=month',
      expect.anything(),
    );
  });

  it('api.mapTimeline omits empty query string', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ bucket: 'month', points: [], total: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await api.mapTimeline();
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/timeline',
      expect.anything(),
    );
  });

  it('standalone getMapRegions delegates to api.mapRegions', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ regions: [], total_regions: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const res = await getMapRegions();
    expect(res.total_regions).toBe(0);
    expect(fetchSpy).toHaveBeenCalledWith('/api/map/regions', expect.anything());
  });

  it('standalone getMapClusterHulls delegates to api.mapClusterHulls', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ clusters: [], count: 0, cached: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await getMapClusterHulls({ min_count: 3 });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/clusters/hulls?min_count=3',
      expect.anything(),
    );
  });

  it('standalone getMapHeatmap delegates to api.mapHeatmap', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          voxel_size: 500,
          voxel_bucket: 500,
          economy: null,
          cells: [],
          count: 0,
          max_cells: 50_000,
          truncated: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await getMapHeatmap({ voxel_size: 500, min_systems: 10 });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/heatmap?voxel_size=500&min_systems=10',
      expect.anything(),
    );
  });

  it('standalone getMapTimeline delegates to api.mapTimeline', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ bucket: 'year', points: [], total: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await getMapTimeline({ bucket: 'year' });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/map/timeline?bucket=year',
      expect.anything(),
    );
  });
});
