import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSearchTuning } from './useSearchTuning';
import { api } from '@/lib/api';
import type { RerankResponse, SystemResult } from '@/types/api';

vi.mock('@/lib/api', () => ({
  api: {
    rerank: vi.fn(),
  },
}));

function makeSystem(id64: number, name = `System ${id64}`): SystemResult {
  return { id64, name } as SystemResult;
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

describe('useSearchTuning', () => {
  beforeEach(() => {
    vi.mocked(api.rerank).mockReset();
    vi.mocked(api.rerank).mockResolvedValue(response);
  });

  it('sends current Finder result IDs to /api/ratings/rerank through api.rerank', async () => {
    const { result } = renderHook(() => useSearchTuning());

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

  it('stores original Finder rank and names in the tuning-run source snapshot', async () => {
    const { result } = renderHook(() => useSearchTuning());

    await act(async () => {
      await result.current.run([
        makeSystem(101, 'Alpha'),
        makeSystem(202, 'Beta'),
        makeSystem(303, 'Gamma'),
      ]);
    });

    expect(result.current.state.kind).toBe('ok');
    if (result.current.state.kind !== 'ok') return;

    expect(result.current.state.sourceSnapshot).toEqual({
      101: { originalRank: 1, name: 'Alpha' },
      202: { originalRank: 2, name: 'Beta' },
      303: { originalRank: 3, name: 'Gamma' },
    });
  });
});
