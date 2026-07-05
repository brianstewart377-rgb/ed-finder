import type { SystemDetail, SystemResult } from '@/types/api';

type LegacyRatingCarrier = Partial<SystemResult & SystemDetail> & {
  _rating?: {
    score?: number | null;
    scoreAgriculture?: number | null;
    scoreRefinery?: number | null;
    scoreIndustrial?: number | null;
    scoreHightech?: number | null;
    scoreMilitary?: number | null;
    scoreTourism?: number | null;
    scoreExtraction?: number | null;
    economySuggestion?: string | null;
    terraformingPotential?: number | null;
    bodyDiversity?: number | null;
    confidence?: number | null;
    rationale?: string | null;
  } | null;
};

function coalesce<T>(...values: Array<T | null | undefined>): T | null {
  for (const value of values) {
    if (value != null) return value;
  }
  return null;
}

export function getLegacyRatingScore(system: LegacyRatingCarrier): number | null {
  return coalesce(system.score, system._rating?.score);
}

export function getLegacyRatingConfidence(system: LegacyRatingCarrier): number | null {
  return coalesce(system.confidence, system._rating?.confidence);
}

export function getLegacyRatingRationale(system: LegacyRatingCarrier): string | null {
  return coalesce(system.rationale, system._rating?.rationale);
}

export function getLegacySuggestedEconomy(system: LegacyRatingCarrier): string | null {
  return coalesce(system.economy_suggestion, system._rating?.economySuggestion);
}

export function getLegacyTerraformingPotential(system: LegacyRatingCarrier): number | null {
  return coalesce(system.terraforming_potential, system._rating?.terraformingPotential);
}

export function getLegacyBodyDiversity(system: LegacyRatingCarrier): number | null {
  return coalesce(system.body_diversity, system._rating?.bodyDiversity);
}

export function getLegacyEconomyScore(
  system: LegacyRatingCarrier,
  economy: 'agriculture' | 'refinery' | 'industrial' | 'hightech' | 'military' | 'tourism' | 'extraction',
): number | null {
  switch (economy) {
    case 'agriculture':
      return coalesce(system.score_agriculture, system._rating?.scoreAgriculture);
    case 'refinery':
      return coalesce(system.score_refinery, system._rating?.scoreRefinery);
    case 'industrial':
      return coalesce(system.score_industrial, system._rating?.scoreIndustrial);
    case 'hightech':
      return coalesce(system.score_hightech, system._rating?.scoreHightech);
    case 'military':
      return coalesce(system.score_military, system._rating?.scoreMilitary);
    case 'tourism':
      return coalesce(system.score_tourism, system._rating?.scoreTourism);
    case 'extraction':
      return coalesce(system.score_extraction, system._rating?.scoreExtraction);
  }
}
