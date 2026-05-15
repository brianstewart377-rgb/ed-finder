import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useOptimizer } from './useOptimizer';
import { api } from '@/lib/api';
import type { RerankResponse, SystemResult } from '@/types/api';

vi.mock('@/lib/api', () => ({
  api: {
    rerank: vi.fn(),
  },
}));

function makeSystem(id64: number): SystemResult {
  return { id64, name: `System ${id64}` } as SystemResult;
}

const response: RerankResponse = {
  weights_applied: {
    economy: 0.3,
    slots: 0.2,
    strategic: 0.15,
    safety: 0.15,
    terraforming: 0.1,
    diversity: 0.1,
  },
  economy_used: null,
  results: [],
};

describe('useOptimizer', () => {
  beforeEach(() => {
    vi.mocked(api.rerank).mockReset();
    vi.mocked(api.rerank).mockResolvedValue(response);
  });

  it('sends current Finder result IDs to /api/ratings/rerank through api.rerank', async () => {
    const { result } = renderHook(() => useOptimizer());

    await act(async () => {
      await result.current.run([makeSystem(101), makeSystem(202), makeSystem(303)]);
    });

    expect(api.rerank).toHaveBeenCalledWith({
      id64s: [101, 202, 303],
      weights: result.current.weights,
      economy: null,
    });
    expect(result.current.state.kind).toBe('ok');
  });
});
