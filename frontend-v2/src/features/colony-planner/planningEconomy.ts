import type { FacilityTemplate, SimulateBuildPlacement } from '@/types/api';

export const PLANNING_ECONOMY_NOTE = 'Planning economy mix — run Preview for validated outcome.';

export type PlanningEconomyName =
  | 'Agriculture'
  | 'Refinery'
  | 'Industrial'
  | 'HighTech'
  | 'Military'
  | 'Tourism'
  | 'Extraction';

export interface PlanningEconomyEntry {
  economy: PlanningEconomyName;
  planned: number;
  projected: number;
  total: number;
}

export interface PlanningEconomyLedger {
  entries: PlanningEconomyEntry[];
  plannedCount: number;
  projectedCount: number;
  unknownCount: number;
  total: number;
}

interface LedgerInput {
  placements?: SimulateBuildPlacement[];
  projectedPlacements?: SimulateBuildPlacement[];
  templates?: FacilityTemplate[];
}

const ECONOMY_ORDER: PlanningEconomyName[] = [
  'Refinery',
  'Industrial',
  'Extraction',
  'Agriculture',
  'Military',
  'HighTech',
  'Tourism',
];

const ECONOMY_ALIASES: Record<string, PlanningEconomyName> = {
  agriculture: 'Agriculture',
  refinery: 'Refinery',
  industrial: 'Industrial',
  hightech: 'HighTech',
  high_tech: 'HighTech',
  'high tech': 'HighTech',
  military: 'Military',
  tourism: 'Tourism',
  extraction: 'Extraction',
};

export function buildPlanningEconomyLedger({
  placements = [],
  projectedPlacements = [],
  templates = [],
}: LedgerInput): PlanningEconomyLedger {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const counts = new Map<PlanningEconomyName, { planned: number; projected: number }>();
  let unknownCount = 0;

  const add = (placement: SimulateBuildPlacement, kind: 'planned' | 'projected') => {
    const economy = normalisePlanningEconomy(templatesById.get(placement.facility_template_id)?.economy);
    if (!economy) {
      unknownCount += 1;
      return;
    }
    const current = counts.get(economy) ?? { planned: 0, projected: 0 };
    current[kind] += 1;
    counts.set(economy, current);
  };

  placements.forEach((placement) => add(placement, 'planned'));
  projectedPlacements.forEach((placement) => add(placement, 'projected'));

  const entries = ECONOMY_ORDER
    .map((economy) => {
      const current = counts.get(economy) ?? { planned: 0, projected: 0 };
      return {
        economy,
        planned: current.planned,
        projected: current.projected,
        total: current.planned + current.projected,
      };
    })
    .filter((entry) => entry.total > 0);

  const plannedCount = entries.reduce((sum, entry) => sum + entry.planned, 0);
  const projectedCount = entries.reduce((sum, entry) => sum + entry.projected, 0);

  return {
    entries,
    plannedCount,
    projectedCount,
    unknownCount,
    total: plannedCount + projectedCount,
  };
}

export function normalisePlanningEconomy(value?: string | null): PlanningEconomyName | null {
  if (!value) return null;
  const normalised = value.trim().replace(/[-\s]+/g, ' ').toLowerCase();
  if (!normalised) return null;
  return ECONOMY_ALIASES[normalised] ?? ECONOMY_ALIASES[normalised.replace(/\s+/g, '')] ?? null;
}

export function compactEconomyLabel(economy: PlanningEconomyName): string {
  if (economy === 'Agriculture') return 'Agri';
  if (economy === 'Industrial') return 'Ind';
  if (economy === 'Extraction') return 'Ext';
  if (economy === 'HighTech') return 'HiTech';
  return economy.slice(0, 4);
}

export function economyToneClass(economy: PlanningEconomyName): string {
  switch (economy) {
    case 'Agriculture':
      return 'bg-green/70';
    case 'Refinery':
      return 'bg-orange/75';
    case 'Industrial':
      return 'bg-silver/70';
    case 'HighTech':
      return 'bg-cyan/75';
    case 'Military':
      return 'bg-gold/75';
    case 'Tourism':
      return 'bg-pink-300/70';
    case 'Extraction':
      return 'bg-amber-700/75';
    default:
      return 'bg-border';
  }
}
