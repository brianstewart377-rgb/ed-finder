/**
 * Wire types for the FastAPI backend.
 *
 * **Audit Phase 7 follow-up (2026-05-09)**: this module now sources types
 * from the auto-generated `api.gen.ts` for the response shapes the backend
 * declares with `response_model=…`. The CI `openapi-types` job (see
 * `.github/workflows/ci.yml`) fails on drift, so once the migration is
 * complete the only place tweaking a wire type lives is `models.py` on
 * the backend. No more "frontend says optional, backend says required"
 * silent splits.
 *
 * If you need to add a field:
 *   1. Add it to `apps/api/src/models.py` (Pydantic) AND emit it from
 *      the SQL projection / `helpers.sys_row_to_dict`.
 *   2. Locally: `cd frontend-v2 && yarn types:gen` (with the API on :8000).
 *   3. Commit the regenerated `api.gen.ts`.
 *   4. If the new field needs a friendlier camelCase alias for use in
 *      this codebase, add it to the wrapper types below.
 *
 * What is NOT yet generated (left hand-written here):
 *   - `WatchlistEntry` — the watchlist endpoint emits raw SQL rows; the
 *     Pydantic model is intentionally not declared so we can iterate on
 *     the table shape without a backend release.
 *   - `Economy` enum + default rerank weights — these are frontend-side
 *     constants, not wire types.
 *   - The `LocalSearchBody` request shape used by `lib/api.ts` — the
 *     generated `LocalSearchRequest` accepts `Record<string, never>` for
 *     filters/body_filters because they're typed `dict` in the Python
 *     model. Keeping the hand-written request shape until the Pydantic
 *     side gets stricter.
 */
import type { components } from '@/types/api.gen';

type Schemas = components['schemas'];

// ─── Generated response/sub types (single source of truth) ────────────────
export type SystemCoords = Schemas['CoordsModel'];
export type SystemRating = Schemas['RatingModel'];
export type SystemBody   = Schemas['BodyModel'];
export type SystemStation = Schemas['StationModel'];

/**
 * One row from `/api/local/search`.
 *
 * Generated from `apps/api/src/models.py::SystemRow`. Camel-case rating
 * block lives under `_rating` (Pydantic alias preserved through the
 * codegen). Field added 2026-05-09 as part of Phase 7 follow-up.
 */
export type SystemResult = Schemas['SystemRow'];

export type SearchResponse        = Schemas['SearchResponse'];
export type AutocompleteHit       = Schemas['AutocompleteHit'];
export type AutocompleteResponse  = Schemas['AutocompleteResponse'];
export type SystemDetail          = Schemas['SystemDetailRow'];
export type SystemDetailResponse  = Schemas['SystemDetailResponse'];
export type AppStatus             = Schemas['StatusResponse'];
export type CacheStats            = Schemas['CacheStatsResponse'];
export type RerankRequest         = Schemas['RerankRequest'];
export type RerankResponse        = Schemas['RerankResponse'];
export type RerankRow             = Schemas['RerankRow'];
export type RerankWeights         = Schemas['RerankWeights'];
export type BuildabilityData      = Schemas['BuildabilityData'];
export type BodySlotPrediction    = Schemas['BodySlotPrediction'];
export type SimulationSummary     = Schemas['SimulationSummaryResponse'];
export type SlotPredictionResponse = Schemas['SlotPredictionResponse'];
export type SlotReason            = Schemas['SlotReason'];
export type BuildabilityResponse  = Schemas['BuildabilityResponse'];
export type SystemBuildability    = BuildabilityResponse;

export interface FacilityTemplate {
  id: string;
  name: string;
  category: string;
  tier: number;
  economy?: string | null;
  is_port: boolean;
  is_support_facility: boolean;
  allowed_location: string;
  pad_size?: string | null;
  confidence?: string | null;
  notes?: string | null;
  yellow_cp_generated: number;
  green_cp_generated: number;
  yellow_cp_cost: number;
  green_cp_cost: number;
}

export interface SimulateBuildPlacement {
  facility_template_id: string;
  local_body_id?: string | null;
  is_primary_port?: boolean;
  build_order: number;
}

export interface SimulateBuildRequest {
  system_id64: number;
  target_archetype: string;
  placements: SimulateBuildPlacement[];
}

export interface SimulationCPResult {
  yellow_cp_final: number;
  green_cp_final: number;
  yellow_cp_generated: number;
  green_cp_generated: number;
  yellow_cp_spent: number;
  green_cp_spent: number;
  t2_ports: number;
  t3_ports: number;
  warnings: string[];
}

export interface SimulationLink {
  port_facility_id?: string | null;
  support_facility_id: string;
  local_body_id?: string | null;
  economy?: string | null;
  value: number;
  note: string;
}

export interface SimulationLinks {
  strong_links: SimulationLink[];
  weak_links: SimulationLink[];
}

export interface SimulateBuildResponse {
  system_id64: number;
  target_archetype: string;
  final_score: number;
  composition_score: number;
  buildability_score: number;
  build_complexity: 'simple' | 'moderate' | 'advanced' | 'expert';
  confidence: number;
  cp: SimulationCPResult;
  economy_composition: Record<string, number>;
  economy_order: string[];
  top_two_alignment: string;
  contamination_risk: string;
  warnings: string[];
  strengths: string[];
  recommendations: string[];
  mechanics_notes: string[];
  links: SimulationLinks;
}

// ─── Frontend-side constants ──────────────────────────────────────────────

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
