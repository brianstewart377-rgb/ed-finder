import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { useClusterSearch } from './useClusterSearch';

vi.mock('@/lib/api', () => ({
  api: {
    clusterSearch: vi.fn(),
  },
}));

const clusterSearchMock = vi.mocked(api.clusterSearch);

describe('useClusterSearch', () => {
  beforeEach(() => {
    clusterSearchMock.mockReset();
  });

  it('runs cluster search through the shared API client', async () => {
    const cluster = {
      anchor_id64: 42,
      anchor_name: 'Test Anchor',
      anchor_coords: { x: 1, y: 2, z: 3 },
      galaxy_region: null,
      coverage_score: 90,
      economy_diversity: 2,
      total_viable: 4,
      agriculture_count: 0,
      agriculture_best: 0,
      refinery_count: 2,
      refinery_best: 80,
      industrial_count: 2,
      industrial_best: 75,
      hightech_count: 0,
      hightech_best: 0,
      military_count: 0,
      military_best: 0,
      tourism_count: 0,
      tourism_best: 0,
      distance_ly: 12,
      cluster_radius_ly: 15,
    };
    clusterSearchMock.mockResolvedValue({ clusters: [cluster], count: 1, query_ms: 7 });
    const { result } = renderHook(() => useClusterSearch());

    await act(async () => {
      await result.current.run();
    });

    expect(clusterSearchMock).toHaveBeenCalledWith({
      slots: [{
        archetype_key: 'refinery_industrial',
        economies: [],
        label: 'Refinery + Industrial',
        min_score: undefined,
      }],
      limit: 50,
      reference_coords: { x: 0, y: 0, z: 0 },
    });
    expect(result.current.results).toEqual([cluster]);
    expect(result.current.state.kind).toBe('ok');
  });

  it('exposes shared API errors and clears stale results', async () => {
    clusterSearchMock
      .mockResolvedValueOnce({ clusters: [], count: 0, query_ms: 1 })
      .mockRejectedValueOnce(new Error('API 503 on /search/cluster'));
    const { result } = renderHook(() => useClusterSearch());

    await act(async () => {
      await result.current.run();
      await result.current.run();
    });

    expect(result.current.results).toEqual([]);
    expect(result.current.state).toEqual({
      kind: 'err',
      message: 'API 503 on /search/cluster',
    });
  });
});
