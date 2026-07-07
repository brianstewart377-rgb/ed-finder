import type { SystemArchetypeResponse, SystemDetail, SystemResult } from '@/types/api';

export function toCompareSnapshot(sys: SystemDetail, archetype: SystemArchetypeResponse | null): SystemResult {
  const developmentScore = archetype?.overall_development_potential
    ?? sys.overall_development_potential
    ?? sys.score
    ?? null;
  return {
    id64:               sys.id64,
    name:               sys.name,
    coords:             { x: sys.x, y: sys.y, z: sys.z },
    distance:           null,
    population:         sys.population ?? null,
    primaryEconomy:     sys.primary_economy ?? null,
    secondaryEconomy:   sys.secondary_economy ?? null,
    security:           sys.security ?? null,
    allegiance:         sys.allegiance ?? null,
    government:         sys.government ?? null,
    is_colonised:       !!sys.is_colonised,
    main_star_type:     sys.main_star_type ?? null,
    main_star_subtype:  sys.main_star_subtype ?? null,
    archetype_score:    developmentScore,
    archetype_tier:     null,
    primary_archetype:  archetype?.primary_archetype ?? sys.primary_archetype ?? null,
    secondary_archetype: archetype?.secondary_archetype ?? sys.secondary_archetype ?? null,
    archetype_confidence: archetype?.archetype_confidence ?? archetype?.confidence ?? null,
    overall_development_potential: developmentScore,
    buildability_score: archetype?.buildability_score ?? sys.buildability_score ?? null,
    purity_score:       archetype?.purity_score ?? sys.purity_score ?? null,
    elw_count:           sys.elw_count ?? null,
    ww_count:            sys.ww_count ?? null,
    ammonia_count:       sys.ammonia_count ?? null,
    gas_giant_count:     sys.gas_giant_count ?? null,
    landable_count:      sys.landable_count ?? null,
    terraformable_count: sys.terraformable_count ?? null,
    bio_signal_total:    sys.bio_signal_total ?? null,
    geo_signal_total:    sys.geo_signal_total ?? null,
    neutron_count:       sys.neutron_count ?? null,
    black_hole_count:    sys.black_hole_count ?? null,
    white_dwarf_count:   sys.white_dwarf_count ?? null,
  };
}
