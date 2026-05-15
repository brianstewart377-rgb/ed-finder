import { describe, expect, it } from 'vitest';
import type { RerankRow } from '@/types/api';
import {
  buildTunedResultExplanation,
  describeRankMovement,
  formatContributionValue,
  getTopContributors,
  getWeakestSignals,
  hasContributionBreakdown,
} from './searchTuningExplanation';

const row: RerankRow = {
  id64: 123,
  reranked_score: 82,
  original_score: 70,
  confidence: 0.92,
  rationale: 'Stored rationale',
  economy_used: 'Tourism',
  contributions: {
    economy: 30,
    slots: 20,
    strategic: 12,
    safety: 8,
    terraforming: 1,
    diversity: 0.5,
  },
};

describe('searchTuningExplanation', () => {
  it('sorts top and weakest contributors deterministically', () => {
    expect(getTopContributors(row).map((item) => item.label)).toEqual(['Economy', 'Slots']);
    expect(getWeakestSignals(row).map((item) => item.label)).toEqual(['Diversity', 'Terraforming']);
  });

  it('describes rank movement conservatively', () => {
    expect(describeRankMovement(4, 1)).toBe('Moved up 3 places.');
    expect(describeRankMovement(1, 4)).toBe('Moved down 3 places.');
    expect(describeRankMovement(2, 2)).toBe('Unchanged.');
    expect(describeRankMovement(undefined, 2)).toBe('Finder rank unavailable.');
  });

  it('builds concise explanation lines from available contribution data', () => {
    expect(buildTunedResultExplanation(row, 4, 1)).toEqual([
      'Moved up 3 places. economy and slots helped most under the current scoring emphasis.',
      'diversity and terraforming contributed less and may have held this tuned position back.',
      'Final tuned score may also reflect the stored confidence adjustment.',
    ]);
  });

  it('returns a fallback when contribution data is unavailable', () => {
    const fallbackRow: RerankRow = { id64: 456, reranked_score: 60 };

    expect(hasContributionBreakdown(fallbackRow)).toBe(false);
    expect(buildTunedResultExplanation(fallbackRow, 2, 2)).toEqual([
      'Unchanged.',
    ]);
  });

  it('formats contribution values for compact row display', () => {
    expect(formatContributionValue(12)).toBe('+12.0');
    expect(formatContributionValue(0.25)).toBe('+0.3');
  });
});
