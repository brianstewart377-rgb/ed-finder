import type { ObservedFact } from '@/types/api';

export type ObservedEvidenceCategoryId =
  | 'architect_primary_port'
  | 'structure_built'
  | 'body_slot'
  | 'economy'
  | 'service_population_security'
  | 'general';

export interface ObservedEvidenceCategorySummary {
  id: ObservedEvidenceCategoryId;
  label: string;
  description: string;
  count: number;
}

export const OBSERVED_EVIDENCE_CATEGORIES: readonly Omit<ObservedEvidenceCategorySummary, 'count'>[] = [
  {
    id: 'architect_primary_port',
    label: 'Primary-port / Architect observation',
    description: 'Manual notes about the in-game Architect primary-port flag or slot context.',
  },
  {
    id: 'structure_built',
    label: 'Structure actually built',
    description: 'Facility state and build outcome records that describe what was constructed.',
  },
  {
    id: 'body_slot',
    label: 'Body / slot observation',
    description: 'Evidence tied to a body, orbital slot, ground slot, or local placement context.',
  },
  {
    id: 'economy',
    label: 'Economy observation',
    description: 'Observed economy records for planned or built structures.',
  },
  {
    id: 'service_population_security',
    label: 'Service / population / security observation',
    description: 'Service observations and notes about population or security state.',
  },
  {
    id: 'general',
    label: 'General note',
    description: 'Other manual evidence that should stay distinct from planned assumptions.',
  },
];

const ARCHITECT_TERMS = ['architect', 'primary port', 'primary-port', 'flagged slot', 'flag icon'];
const BODY_SLOT_TERMS = ['body', 'orbital slot', 'ground slot', 'surface slot', 'slot'];
const SERVICE_TERMS = ['service', 'population', 'security'];

export function categorizeObservedEvidence(fact: ObservedFact): ObservedEvidenceCategoryId {
  const haystack = [
    fact.fact_type,
    fact.subject_type,
    fact.subject_id,
    fact.notes,
    fact.local_body_id,
    fact.service_id,
    fact.economy,
    ...(fact.tags ?? []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (ARCHITECT_TERMS.some((term) => haystack.includes(term))) {
    return 'architect_primary_port';
  }

  if (fact.fact_type === 'economy_presence' || fact.subject_type === 'economy' || Boolean(fact.economy)) {
    return 'economy';
  }

  if (fact.fact_type === 'service_presence' || fact.subject_type === 'service' || SERVICE_TERMS.some((term) => haystack.includes(term))) {
    return 'service_population_security';
  }

  if (fact.fact_type === 'facility_state' || fact.fact_type === 'build_outcome' || Boolean(fact.facility_template_id)) {
    return 'structure_built';
  }

  if (Boolean(fact.local_body_id) || fact.subject_type === 'body' || BODY_SLOT_TERMS.some((term) => haystack.includes(term))) {
    return 'body_slot';
  }

  return 'general';
}

export function summarizeObservedEvidenceCategories(facts: readonly ObservedFact[]): ObservedEvidenceCategorySummary[] {
  const counts = new Map<ObservedEvidenceCategoryId, number>();
  for (const fact of facts) {
    const category = categorizeObservedEvidence(fact);
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }

  return OBSERVED_EVIDENCE_CATEGORIES.map((category) => ({
    ...category,
    count: counts.get(category.id) ?? 0,
  }));
}
