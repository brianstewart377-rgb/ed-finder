import type { SystemArchetypeResponse, SystemDetail } from '@/types/api';
import { archetypeTierFromScore, formatArchetypeLabel } from '@/lib/archetypes';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';

export function buildFallbackArchetype(system: SystemDetail | null): SystemArchetypeResponse | null {
  if (!system) return null;

  const primaryKey = system.primary_archetype
    ?? archetypeFromEconomy(system.primary_economy ?? null)
    ?? archetypeFromEconomy(system.secondary_economy ?? null);
  if (!primaryKey) return null;

  const developmentScore = firstFinite(
    system.overall_development_potential,
    system.buildability_score,
    system.purity_score,
    system.score,
  );
  if (developmentScore == null) return null;

  const positives: string[] = [];
  if ((system.buildability_score ?? 0) >= 70) positives.push('Strong buildability snapshot already present in system detail.');
  if ((system.purity_score ?? 0) >= 70) positives.push('High purity signal suggests a cleaner economy mix.');
  if ((system.est_total_slots ?? 0) > 0) positives.push(`Estimated slot capacity: ${system.est_total_slots}.`);

  const risks: string[] = [];
  if ((system.contamination_risk ?? 0) >= 40) risks.push('Contamination risk is elevated in the current snapshot.');
  if (system.build_complexity) risks.push(`Build complexity is currently marked ${system.build_complexity}.`);

  const summary = [
    `Development score snapshot ${Math.round(developmentScore)}.`,
    system.overall_development_potential == null && system.score != null
      ? 'Using the score already present on system detail until archetype rows refresh.'
      : null,
    system.buildability_score != null ? `Buildability ${Math.round(system.buildability_score)}.` : null,
    system.purity_score != null ? `Purity ${Math.round(system.purity_score)}.` : null,
  ].filter(Boolean).join(' ');

  return {
    id64: system.id64,
    name: system.name ?? `System ${system.id64}`,
    coords: system.coords ?? null,
    main_star_type: system.main_star_type ?? null,
    archetypes: {
      [primaryKey]: {
        score: developmentScore,
        tier: archetypeTierFromScore(developmentScore) ?? 'D',
        label: formatArchetypeLabel(primaryKey),
        rationale: {
          summary,
          positives,
          risks,
          tags: [],
        },
      },
    },
    primary_archetype: primaryKey,
    secondary_archetype: system.secondary_archetype ?? null,
    archetype_confidence: system.archetype_confidence ?? null,
    overall_development_potential: system.overall_development_potential ?? developmentScore,
    buildability_score: system.buildability_score ?? null,
    build_complexity: system.build_complexity ?? null,
    purity_score: system.purity_score ?? null,
    contamination_risk: system.contamination_risk ?? null,
    confidence: system.archetype_confidence ?? null,
    tags: [],
  };
}

function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}
