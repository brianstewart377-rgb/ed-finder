import { describe, expect, it } from 'vitest';
import type { DevelopmentRerankRow } from '@/types/api';
import {
  buildTunedResultExplanation,
  describeRankMovement,
  formatContributionValue,
  getTopContributors,
  getWeakestSignals,
  hasContributionBreakdown,
} from './searchTuningExplanation';

const row: DevelopmentRerankRow = {
  id64: 123,
  reranked_score: 82,
  original_score: 70,
  confidence: 0.92,
  rationale: { summary: 'Stored rationale' },
  contributions: {
    purity: 30,
    buildability: 24,
    slots: 20,
    expansion: 12,
    logistics: 1,
  },
};

describe('searchTuningExplanation', () => {
  it('sorts top and weakest contributors deterministically', () => {
    expect(getTopContributors(row).map((item) => item.label)).toEqual(['Purity', 'Buildability']);
    expect(getWeakestSignals(row).map((item) => item.label)).toEqual(['Logistics', 'Expansion']);
  });

  it('describes rank movement conservatively', () => {
    expect(describeRankMovement(4, 1)).toBe('Moved up 3 places.');
    expect(describeRankMovement(1, 4)).toBe('Moved down 3 places.');
    expect(describeRankMovement(2, 2)).toBe('Unchanged.');
    expect(describeRankMovement(undefined, 2)).toBe('Finder rank unavailable.');
  });

  it('builds concise explanation lines from available contribution data', () => {
    expect(buildTunedResultExplanation(row, 4, 1)).toEqual([
      'Moved up 3 places. purity and buildability helped most under the current scoring emphasis.',
      'logistics and expansion contributed less under the current weights.',
      'Final tuned score may also reflect the stored confidence adjustment.',
    ]);
  });

  it('uses neutral explanation copy when all contributions are zero', () => {
    const zeroRow: DevelopmentRerankRow = {
      ...row,
      confidence: null,
      contributions: {
        purity: 0,
        buildability: 0,
        slots: 0,
        expansion: 0,
        logistics: 0,
      },
    };

    expect(buildTunedResultExplanation(zeroRow, 2, 2)).toEqual([
      'Unchanged.',
      'Contribution values are available, but all tracked signals contributed 0.0 under the current weights.',
    ]);
    expect(buildTunedResultExplanation(zeroRow, 2, 2).join(' ')).not.toContain('helped most');
  });

  it('describes mixed positive and zero contributions without penalty language', () => {
    const mixedRow: DevelopmentRerankRow = {
      ...row,
      confidence: null,
      contributions: {
        purity: 30,
        buildability: 0,
        slots: 0,
        expansion: 12,
        logistics: 0,
      },
    };

    const explanation = buildTunedResultExplanation(mixedRow, 4, 1);
    expect(explanation).toEqual([
      'Moved up 3 places. purity and expansion helped most under the current scoring emphasis.',
      'buildability and slots contributed less under the current weights.',
    ]);
    expect(explanation.join(' ')).not.toContain('held this tuned position back');
  });

  it('returns a fallback when contribution data is unavailable', () => {
    const fallbackRow: DevelopmentRerankRow = { id64: 456, reranked_score: 60 };

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
