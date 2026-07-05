import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import type { SystemResult } from '@/types/api';

export type ArchetypeTier = 'S' | 'A' | 'B' | 'C' | 'D';

const ARCHETYPE_LABELS: Record<string, string> = {
  refinery_industrial: 'Refinery / Industrial Megacomplex',
  extraction_refinery: 'Extraction / Refinery Mining Hub',
  agriculture_terraforming: 'Agriculture / Terraforming Colony',
  hitech_tourism: 'High Tech / Tourism Prestige Colony',
  expansion_capital: 'Expansion Capital',
  trade_logistics: 'Trade / Logistics Hub',
  population_capital: 'Population Capital',
  ax_forward_base: 'AX Forward Operating Base',
  military_industrial: 'Military / Industrial Complex',
  flexible_multirole: 'Flexible Multi-Role Colony',
};

export function formatArchetypeLabel(value: string | null | undefined): string {
  if (!value) return 'Unknown archetype';
  if (ARCHETYPE_LABELS[value]) return ARCHETYPE_LABELS[value];
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function archetypeTierFromScore(score: number | null | undefined): ArchetypeTier | null {
  if (typeof score !== 'number' || !Number.isFinite(score)) return null;
  if (score >= 88) return 'S';
  if (score >= 76) return 'A';
  if (score >= 60) return 'B';
  if (score >= 45) return 'C';
  return 'D';
}

export function getFinderArchetypeSummary(system: Pick<
  SystemResult,
  'primary_archetype' | 'secondary_archetype' | 'primaryEconomy' | 'secondaryEconomy' | '_rating'
>): { key: string; label: string; source: 'archetype' | 'economy' } | null {
  if (system.primary_archetype) {
    return {
      key: system.primary_archetype,
      label: formatArchetypeLabel(system.primary_archetype),
      source: 'archetype',
    };
  }

  const suggestedEconomy = system._rating?.economySuggestion ?? system.primaryEconomy ?? system.secondaryEconomy ?? null;
  const fallback = archetypeFromEconomy(suggestedEconomy);
  if (!fallback) return null;
  return {
    key: fallback,
    label: formatArchetypeLabel(fallback),
    source: 'economy',
  };
}
