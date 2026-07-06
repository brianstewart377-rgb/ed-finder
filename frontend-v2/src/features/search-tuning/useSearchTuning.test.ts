import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSearchTuning } from './useSearchTuning';
import { api } from '@/lib/api';
import type { DevelopmentRerankResponse, SystemResult } from '@/types/api';

vi.mock('@/lib/api', () => ({
  api: {
    archetypeRerank: vi.fn(),
  },
}));

function makeSystem(id64: number, name = `System ${id64}`): SystemResult {
  return { id64, name } as SystemResult;
}

const response: DevelopmentRerankResponse = {
  weights_applied: {
    purity: 0.3,
    buildability: 0.25,
    slots: 0.2,
    expansion: 0.15,
    logistics: 0.1,
  },
  results: [],
};

describe('useSearchTuning', () => {
  beforeEach(() => {
    vi.mocked(api.archetypeRerank).mockReset();
    vi.mocked(api.archetypeRerank).mockResolvedValue(response);
  });

  it('sends current Finder result IDs to /api/archetypes/rerank through api.archetypeRerank', async () => {
    const { result } = renderHook(() => useSearchTuning());

    await act(async () => {
      await result.current.run([makeSystem(101), makeSystem(202), makeSystem(303)]);
    });

    expect(api.archetypeRerank).toHaveBeenCalledWith({
      id64s: [101, 202, 303],
      weights: result.current.weights,
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
