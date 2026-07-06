import { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import type {
  DevelopmentRerankResponse,
  DevelopmentRerankWeights,
  SystemResult,
} from '@/types/api';
import { DEFAULT_WEIGHTS } from '@/types/api';

export type SearchTuningSourceSnapshot = Record<number, {
  originalRank: number;
  name?: string | null;
}>;

export type SearchTuningState =
  | { kind: 'idle' }
  | { kind: 'busy'; sourceSnapshot: SearchTuningSourceSnapshot }
  | { kind: 'err'; message: string }
  | { kind: 'ok';  data: DevelopmentRerankResponse; queriedAt: number; sourceSnapshot: SearchTuningSourceSnapshot };

export interface UseSearchTuning {
  weights:   DevelopmentRerankWeights;
  setWeight: (k: keyof DevelopmentRerankWeights, v: number) => void;
  resetWeights: () => void;
  weightSum: number;

  state:     SearchTuningState;
  /** Run /api/archetypes/rerank against the given source list. */
  run:       (source: SystemResult[]) => Promise<void>;
  resetState: () => void;
}

/**
 * Development Tuning state. The weights are local + reactive; the source list
 * (id64s) is supplied at run() time by the caller - usually the Finder's
 * current results - so this feature doesn't have to know about /search.
 */
export function useSearchTuning(): UseSearchTuning {
  const [weights, setWeights] = useState<DevelopmentRerankWeights>(DEFAULT_WEIGHTS);
  const [state,   setState]   = useState<SearchTuningState>({ kind: 'idle' });

  const setWeight = useCallback((k: keyof DevelopmentRerankWeights, v: number) => {
    setWeights((prev) => ({
      ...prev,
      [k]: Math.max(0, Math.min(1, v)),
    }));
  }, []);

  const resetWeights = useCallback(() => setWeights(DEFAULT_WEIGHTS), []);

  const weightSum = Object.values(weights).reduce((a, b) => a + b, 0);

  const run = useCallback(async (source: SystemResult[]) => {
    if (source.length === 0) {
      setState({ kind: 'err', message: 'No source systems — run a Finder search first.' });
      return;
    }
    const sourceForRun = source.slice(0, 500);
    const sourceSnapshot: SearchTuningSourceSnapshot = Object.fromEntries(
      sourceForRun.map((system, index) => [
        system.id64,
        {
          originalRank: index + 1,
          name: system.name ?? null,
        },
      ]),
    );

    setState({ kind: 'busy', sourceSnapshot });
    try {
      const data = await api.archetypeRerank({
        id64s:   sourceForRun.map((s) => s.id64),
        weights,
      });
      setState({ kind: 'ok', data, queriedAt: Date.now(), sourceSnapshot });
    } catch (e: unknown) {
      // Keep errors simple for now; there is no tuned result list to annotate.
      setState({
        kind:    'err',
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [weights]);

  const resetState = useCallback(() => setState({ kind: 'idle' }), []);

  return {
    weights, setWeight, resetWeights, weightSum,
    state, run, resetState,
  };
}
