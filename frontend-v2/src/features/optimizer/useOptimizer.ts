import { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import type {
  Economy,
  RerankResponse,
  RerankWeights,
  SystemResult,
} from '@/types/api';
import { DEFAULT_WEIGHTS } from '@/types/api';

export const ECONOMIES: Economy[] = [
  'Agriculture', 'Refinery', 'Industrial',
  'HighTech',    'Military', 'Tourism', 'Extraction',
];

export type OptimizerState =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'err'; message: string }
  | { kind: 'ok';  data: RerankResponse; queriedAt: number };

export interface UseOptimizer {
  weights:   RerankWeights;
  setWeight: (k: keyof RerankWeights, v: number) => void;
  resetWeights: () => void;
  weightSum: number;

  economy:   Economy | null;
  setEconomy: (e: Economy | null) => void;

  state:     OptimizerState;
  /** Run /api/ratings/rerank against the given source list. */
  run:       (source: SystemResult[]) => Promise<void>;
  resetState: () => void;
}

/**
 * Optimizer state. The weights are local + reactive; the source list
 * (id64s) is supplied at run() time by the caller — usually the Finder's
 * current results — so the optimizer doesn't have to know about /search.
 */
export function useOptimizer(): UseOptimizer {
  const [weights, setWeights] = useState<RerankWeights>(DEFAULT_WEIGHTS);
  const [economy, setEconomy] = useState<Economy | null>(null);
  const [state,   setState]   = useState<OptimizerState>({ kind: 'idle' });

  const setWeight = useCallback((k: keyof RerankWeights, v: number) => {
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
    setState({ kind: 'busy' });
    try {
      const data = await api.rerank({
        id64s:   source.map((s) => s.id64).slice(0, 500),
        weights,
        economy: economy ?? null,
      });
      setState({ kind: 'ok', data, queriedAt: Date.now() });
    } catch (e: unknown) {
      setState({
        kind:    'err',
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [weights, economy]);

  const resetState = useCallback(() => setState({ kind: 'idle' }), []);

  return {
    weights, setWeight, resetWeights, weightSum,
    economy, setEconomy,
    state, run, resetState,
  };
}
