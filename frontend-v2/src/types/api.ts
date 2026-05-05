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
