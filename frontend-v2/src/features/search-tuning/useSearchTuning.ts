import { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import type {
  DevelopmentRerankRow,
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
      const apiData = await api.archetypeRerank({
        id64s:   sourceForRun.map((s) => s.id64),
        weights,
      });
      const data = mergeWithLocalFallback(apiData, sourceForRun, weights);
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

function mergeWithLocalFallback(
  response: DevelopmentRerankResponse,
  source: SystemResult[],
  weights: DevelopmentRerankWeights,
): DevelopmentRerankResponse {
  const localRows = buildLocalFallbackRows(source, weights);
  if (localRows.length === 0) return response;

  const merged = new Map<number, DevelopmentRerankRow>();
  for (const row of localRows) {
    merged.set(row.id64, row);
  }
  for (const row of response.results) {
    merged.set(row.id64, row);
  }

  return {
    ...response,
    results: Array.from(merged.values()).sort((a, b) => b.reranked_score - a.reranked_score),
  };
}

function buildLocalFallbackRows(
  source: SystemResult[],
  weights: DevelopmentRerankWeights,
): DevelopmentRerankRow[] {
  return source.map((system) => {
    const purity = finiteNumber(system.purity_score);
    const buildability = finiteNumber(system.buildability_score);
    const slots = finiteNumber(system.est_total_slots);
    const expansion = finiteNumber(system.overall_development_potential ?? system.archetype_score);
    const logistics = scoopableLogistics(system.main_star_type);
    const contributions = {
      purity: roundContribution(purity * weights.purity),
      buildability: roundContribution(buildability * weights.buildability),
      slots: roundContribution(slots * weights.slots),
      expansion: roundContribution(expansion * weights.expansion),
      logistics: roundContribution(logistics * weights.logistics),
    };
    const rerankedScore = Math.round(
      contributions.purity
      + contributions.buildability
      + contributions.slots
      + contributions.expansion
      + contributions.logistics,
    );

    return {
      id64: system.id64,
      reranked_score: rerankedScore,
      original_score: system.archetype_score ?? system.overall_development_potential ?? null,
      confidence: system.archetype_confidence ?? null,
      rationale: {
        summary: 'Built from the current Finder snapshot because no stored archetype rerank row was available for this system.',
      },
      contributions,
    };
  });
}

function finiteNumber(value: number | null | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function roundContribution(value: number): number {
  return Math.round(value * 10) / 10;
}

function scoopableLogistics(mainStarType: string | null | undefined): number {
  return ['O', 'B', 'A', 'F', 'G', 'K', 'M'].includes((mainStarType ?? '').toUpperCase()) ? 80 : 40;
}
