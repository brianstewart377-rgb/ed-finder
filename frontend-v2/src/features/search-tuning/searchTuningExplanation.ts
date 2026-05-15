import type { RerankRow } from '@/types/api';

export interface ContributionLabel {
  key: keyof NonNullable<RerankRow['contributions']>;
  label: string;
  value: number;
}

const LABELS: Record<ContributionLabel['key'], string> = {
  economy:      'Economy',
  slots:        'Slots',
  strategic:    'Strategic',
  safety:       'Safety',
  terraforming: 'Terraforming',
  diversity:    'Diversity',
};

const CONTRIBUTION_KEYS = Object.keys(LABELS) as ContributionLabel['key'][];
const EFFECTIVELY_ZERO = 0.05;

export function getTopContributors(row: RerankRow, limit = 2): ContributionLabel[] {
  const labels = contributionLabels(row);
  const positiveLabels = labels.filter((item) => item.value >= EFFECTIVELY_ZERO);

  return (positiveLabels.length > 0 ? positiveLabels : labels)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

export function getWeakestSignals(row: RerankRow, limit = 2): ContributionLabel[] {
  return contributionLabels(row)
    .sort((a, b) => a.value - b.value)
    .slice(0, limit);
}

export function hasContributionBreakdown(row: RerankRow): boolean {
  return contributionLabels(row).length > 0;
}

export function describeRankMovement(originalRank: number | undefined, tunedRank: number): string {
  if (originalRank == null) return 'Finder rank unavailable.';

  const places = originalRank - tunedRank;
  if (places > 0) return `Moved up ${places} place${places === 1 ? '' : 's'}.`;
  if (places < 0) {
    const down = Math.abs(places);
    return `Moved down ${down} place${down === 1 ? '' : 's'}.`;
  }
  return 'Unchanged.';
}

export function buildTunedResultExplanation(
  row: RerankRow,
  originalRank: number | undefined,
  tunedRank: number,
): string[] {
  const movement = describeRankMovement(originalRank, tunedRank);
  const top = getTopContributors(row);
  const weakest = getWeakestSignals(row);

  if (top.length === 0) {
    return [movement];
  }

  const hasPositiveContribution = top.some((item) => item.value >= EFFECTIVELY_ZERO);
  if (!hasPositiveContribution) {
    const lines = [
      movement,
      'Contribution values are available, but all tracked signals contributed 0.0 under the current weights.',
    ];

    if (row.confidence != null) {
      lines.push('Final tuned score may also reflect the stored confidence adjustment.');
    }

    return lines;
  }

  const topLabels = top.map((item) => item.label.toLowerCase()).join(' and ');
  const weakLabels = weakest.map((item) => item.label.toLowerCase()).join(' and ');

  const lines = [
    `${movement} ${topLabels} helped most under the current scoring emphasis.`,
  ];

  if (weakLabels) {
    lines.push(`${weakLabels} contributed less under the current weights.`);
  }

  if (row.confidence != null) {
    lines.push('Final tuned score may also reflect the stored confidence adjustment.');
  }

  return lines;
}

export function formatContributionValue(value: number): string {
  return `+${value.toFixed(1)}`;
}

function contributionLabels(row: RerankRow): ContributionLabel[] {
  if (!row.contributions) return [];

  return CONTRIBUTION_KEYS
    .map((key) => ({
      key,
      label: LABELS[key],
      value: Number(row.contributions?.[key] ?? 0),
    }))
    .filter((item) => Number.isFinite(item.value));
}
