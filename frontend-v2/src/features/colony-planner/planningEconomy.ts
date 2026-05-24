import type { FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';

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
    const template = templatesById.get(placement.facility_template_id);
    const economy = normalisePlanningEconomy(template?.economy);
    if (!economy) {
      if (template?.is_port) return;
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

export interface InferredEconomyShare {
  economy: PlanningEconomyName;
  share: number;
  source: 'system' | 'body';
}

const BODY_SUBTYPE_LEANS: Array<{ tokens: string[]; economies: PlanningEconomyName[] }> = [
  { tokens: ['high metal content', 'metal rich'], economies: ['Refinery', 'Extraction'] },
  { tokens: ['icy body', 'ice'], economies: ['Extraction'] },
  { tokens: ['rocky body', 'rocky ice'], economies: ['Extraction'] },
  { tokens: ['earth-like', 'earthlike', 'earth like'], economies: ['Agriculture', 'Tourism'] },
  { tokens: ['water world'], economies: ['Tourism'] },
  { tokens: ['ammonia world'], economies: ['HighTech'] },
  { tokens: ['gas giant'], economies: ['Industrial'] },
];

/**
 * Build a coarse inherited economy baseline for a station/port placed over a body
 * before any additional buildings are added. Mirrors RavenColonial's contextual
 * baseline behaviour: weighted picks from the surrounding system + body context.
 *
 * Anything more precise (final composition shares, CP, contamination) still
 * requires running Preview — this is only the inherited contextual baseline.
 */
export function inferredStationBaselineShares(
  body: SystemBody | null | undefined,
  system: Pick<SystemDetail, 'primary_economy' | 'secondary_economy'> | null | undefined,
): InferredEconomyShare[] {
  const out: InferredEconomyShare[] = [];
  const seen = new Set<PlanningEconomyName>();
  const pushShare = (
    economy: PlanningEconomyName | null,
    share: number,
    source: 'system' | 'body',
  ) => {
    if (!economy || share <= 0) return;
    if (seen.has(economy)) {
      const existing = out.find((entry) => entry.economy === economy);
      if (existing) existing.share += share;
      return;
    }
    seen.add(economy);
    out.push({ economy, share, source });
  };

  if (system) {
    pushShare(normalisePlanningEconomy(system.primary_economy), 60, 'system');
    pushShare(normalisePlanningEconomy(system.secondary_economy), 25, 'system');
  }

  if (body) {
    const subtype = `${body.subtype ?? ''} ${body.body_type ?? ''}`.toLowerCase();
    BODY_SUBTYPE_LEANS.forEach((entry) => {
      if (entry.tokens.some((token) => subtype.includes(token))) {
        entry.economies.forEach((economy) => pushShare(economy, 15, 'body'));
      }
    });
    if ((body.geo_signal_count ?? 0) > 0) pushShare('Extraction', 10, 'body');
    if ((body.bio_signal_count ?? 0) > 0) pushShare('Agriculture', 10, 'body');
    if (body.is_terraformable === true) pushShare('Agriculture', 10, 'body');
  }

  if (out.length === 0) return [];

  const total = out.reduce((sum, entry) => sum + entry.share, 0);
  return out
    .map((entry) => ({ ...entry, share: Math.round((entry.share / total) * 100) }))
    .filter((entry) => entry.share > 0);
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
