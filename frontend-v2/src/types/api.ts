/**
 * Wire types for the FastAPI backend.
 *
 * Hand-maintained for the POC. Once we want full coverage we can switch to
 * `openapi-typescript-codegen` against `https://ed-finder.app/openapi.json`,
 * which the modular backend already publishes. For now we only model the
 * fields that the result-card POC needs to render.
 */

export interface SystemRating {
  score:                   number | null;
  scoreAgriculture?:       number | null;
  scoreRefinery?:          number | null;
  scoreIndustrial?:        number | null;
  scoreHightech?:          number | null;
  scoreMilitary?:          number | null;
  scoreTourism?:           number | null;
  scoreExtraction?:        number | null;
  economySuggestion?:      string | null;
  breakdown?:              Record<string, unknown> | null;
  /** v3.1 fields */
  terraformingPotential?:  number | null;
  bodyDiversity?:          number | null;
  confidence?:             number | null;
  rationale?:              string | null;
}

export interface SystemCoords {
  x: number;
  y: number;
  z: number;
}

export interface SystemResult {
  id64:                  number;
  name:                  string;
  coords?:               SystemCoords;
  /** Only populated for distance searches. */
  distance?:             number | null;
  population:            number;
  primaryEconomy?:       string | null;
  secondaryEconomy?:     string | null;
  security?:             string | null;
  allegiance?:           string | null;
  government?:           string | null;
  is_colonised?:         boolean;
  is_being_colonised?:   boolean;
  main_star_type?:       string | null;
  main_star_subtype?:    string | null;
  _rating?:              SystemRating | null;
  /** Body counts on the rating row, surfaced for filter pills. */
  elw_count?:            number | null;
  ww_count?:             number | null;
  ammonia_count?:        number | null;
  gas_giant_count?:      number | null;
  landable_count?:       number | null;
  terraformable_count?:  number | null;
  bio_signal_total?:     number | null;
  geo_signal_total?:     number | null;
  neutron_count?:        number | null;
  black_hole_count?:     number | null;
  white_dwarf_count?:    number | null;
}

export interface SearchResponse {
  results: SystemResult[];
  total:   number;
  count:   number;
}

export interface AutocompleteHit {
  id64:           number;
  name:           string;
  x:              number;
  y:              number;
  z:              number;
  population:     number;
  primaryEconomy: string | null;
}

export interface AutocompleteResponse {
  results: AutocompleteHit[];
  source?: string;
}

// ─── /api/system/{id64} — full detail ────────────────────────────────────
//
// Endpoint returns snake_case (joins systems + ratings + bodies + stations).
// Wire types mirror that — we don't camelCase-rewrite at the boundary
// because the modal renders strings directly.

export interface SystemBody {
  id:                       number;
  name:                     string;
  subtype:                  string | null;
  body_type:                string | null;   // 'Star' | 'Planet' | 'Moon' | 'Belt' | …
  distance_from_star:       number | null;   // ls
  is_landable:              boolean | null;
  is_terraformable:         boolean | null;
  is_earth_like:            boolean | null;
  is_water_world:           boolean | null;
  is_ammonia_world:         boolean | null;
  bio_signal_count:         number | null;
  geo_signal_count:         number | null;
  surface_temp:             number | null;
  radius:                   number | null;
  mass:                     number | null;
  gravity:                  number | null;
  estimated_mapping_value:  number | null;
  estimated_scan_value:     number | null;
  is_main_star:             boolean | null;
  spectral_class:           string | null;
  is_scoopable:             boolean | null;
}

export interface SystemStation {
  id:                  number;
  name:                string;
  station_type:        string | null;
  distance_from_star:  number | null;
  landing_pad_size:    'L' | 'M' | 'S' | null;
  has_market:          boolean | null;
  has_shipyard:        boolean | null;
  has_outfitting:      boolean | null;
}

export interface SystemDetail {
  id64:               number;
  name:               string;
  x:                  number;
  y:                  number;
  z:                  number;
  population:         number;
  primary_economy?:   string | null;
  secondary_economy?: string | null;
  security?:          string | null;
  allegiance?:        string | null;
  government?:        string | null;
  is_colonised?:      boolean | null;
  main_star_type?:    string | null;
  main_star_subtype?: string | null;

  // Flat rating fields (joined from ratings table)
  score?:                  number | null;
  score_agriculture?:      number | null;
  score_refinery?:         number | null;
  score_industrial?:       number | null;
  score_hightech?:         number | null;
  score_military?:         number | null;
  score_tourism?:          number | null;
  score_extraction?:       number | null;
  economy_suggestion?:     string | null;
  elw_count?:              number | null;
  ww_count?:               number | null;
  ammonia_count?:          number | null;
  gas_giant_count?:        number | null;
  landable_count?:         number | null;
  terraformable_count?:    number | null;
  bio_signal_total?:       number | null;
  geo_signal_total?:       number | null;
  neutron_count?:          number | null;
  black_hole_count?:       number | null;
  white_dwarf_count?:      number | null;
  terraforming_potential?: number | null;
  body_diversity?:         number | null;
  confidence?:             number | null;
  rationale?:              string | null;

  bodies?:   SystemBody[];
  stations?: SystemStation[];

  exploration_value?: {
    total_scan_value:    number;
    total_mapping_value: number;
    combined_value:      number;
  };
}

/** Backend returns {record, system} — same data twice. */
export interface SystemDetailResponse {
  record: SystemDetail;
  system: SystemDetail;
}

// ─── /api/status — system meta + counts ───────────────────────────────────

export interface AppStatus {
  available:           boolean;
  systems_count:       number;
  body_count:          number;
  rated_count:         number;
  clustered_count:     number;
  import_complete:     boolean;
  ratings_built:       boolean;
  grid_built:          boolean;
  clusters_built:      boolean;
  eddn_enabled:        boolean;
  last_nightly_update: string;
  schema_version:      string;
  max_search_radius_ly: number;
  has_body_data:       boolean;
  version:             string;
}

// ─── /api/cache/stats ─────────────────────────────────────────────────────

export interface CacheStats {
  cache_hits:       number;
  cache_misses:     number;
  redis_hits?:      number;
  redis_misses?:    number;
  redis_memory_mb?: number;
  db_cache_rows:    number;
}

// ─── /api/ratings/rerank ──────────────────────────────────────────────────

export interface RerankWeights {
  economy:      number;
  slots:        number;
  strategic:    number;
  safety:       number;
  terraforming: number;
  diversity:    number;
}

export const DEFAULT_WEIGHTS: RerankWeights = {
  economy:      0.42,
  slots:        0.23,
  strategic:    0.18,
  safety:       0.10,
  terraforming: 0.05,
  diversity:    0.02,
};

export type Economy =
  | 'Agriculture' | 'Refinery' | 'Industrial'
  | 'HighTech'    | 'Military' | 'Tourism' | 'Extraction';

export interface RerankRequest {
  id64s:    number[];
  weights?: Partial<RerankWeights>;
  /** null/undefined = use each row's stored economy_suggestion. */
  economy?: Economy | null;
}

export interface RerankRow {
  id64:           number;
  reranked_score: number;
  original_score: number | null;
  confidence:     number | null;
  rationale:      string | null;
  economy_used:   string | null;
}

export interface RerankResponse {
  weights_applied: RerankWeights;
  economy_used:    Economy | null;
  results:         RerankRow[];
}
