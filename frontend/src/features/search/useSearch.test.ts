import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { DEFAULT_FILTERS, useSearch } from './useSearch';

vi.mock('@/lib/api', () => ({
  api: {
    localSearch: vi.fn(),
  },
}));

describe('useSearch', () => {
  beforeEach(() => {
    vi.mocked(api.localSearch).mockReset();
    vi.mocked(api.localSearch).mockResolvedValue({
      results: [],
      total: 0,
      count: 0,
    } as never);
  });

  it('serializes quick-pill exclude filters into body_filters max=0 constraints', async () => {
    const { result } = renderHook(() => useSearch());

    act(() => {
      result.current.setFilters({
        ...DEFAULT_FILTERS,
        bodyFilters: {
          ...DEFAULT_FILTERS.bodyFilters,
          elw: 'excluded',
          bio: 'excluded',
          terra: 'required',
        },
      });
    });

    await act(async () => {
      await result.current.run();
    });

    expect(api.localSearch).toHaveBeenCalledWith(expect.objectContaining({
      body_filters: expect.objectContaining({
        elw: { max: 0 },
        bio: { max: 0 },
        terraformable: { min: 1 },
      }),
    }));
  });
});
