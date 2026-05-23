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
export type SimulationSummary     = Schemas['SimulationSummaryResponse'] & { regional_context?: RegionalAnalysisResponse | null };
export type BuildabilityResponse  = Schemas['BuildabilityResponse'];
export type SystemBuildability    = BuildabilityResponse;

export interface SlotReason {
  factor: string;
  delta?: number | null;
  note?: string | null;
}

export interface BodySlotPrediction {
  system_address: number;
  body_id: number;
  body_name?: string | null;
  planet_class?: string | null;
  predicted_orbital_slots?: number | null;
  predicted_ground_slots?: number | null;
  prediction_status: 'predicted' | 'unknown' | 'observed';
  confidence_label?: string | null;
  prediction_version?: string | null;
  validation_note?: string | null;
  required_input_missing?: string[];
  missing_inputs?: string[];
  source_label?: string | null;
  estimated_orbital_slots?: number | null;
  estimated_surface_slots?: number | null;
  slot_confidence?: number | null;
  slot_source?: string | null;
  reasons?: SlotReason[];
  is_ringed?: boolean | null;
  is_landable?: boolean | null;
  radius?: number | null;
}

export interface SlotPredictionResponse {
  system_id64: number;
  data_source: 'eddn' | 'spansh' | 'none';
  body_count: number;
  predicted_orbital_slots_total?: number | null;
  predicted_ground_slots_total?: number | null;
  prediction_status: 'predicted' | 'unknown' | 'observed';
  prediction_version: string;
  confidence_label?: string | null;
  disclaimer: string;
  validation_note: string;
  required_input_missing?: string[];
  missing_inputs?: string[];
  source_label?: string | null;
  estimated_orbital_slots?: number | null;
  estimated_ground_slots?: number | null;
  slot_confidence?: number | null;
  slot_confidence_label?: string | null;
  predictions: BodySlotPrediction[];
  note?: string | null;
}

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
  prerequisites?: Array<Record<string, unknown>> | null;
  economy_effects?: Record<string, unknown> | null;
  yellow_cp_generated: number;
  green_cp_generated: number;
  yellow_cp_cost: number;
  green_cp_cost: number;
  stat_effects?: Record<string, unknown>;
  population?: number | null;
  max_population?: number | null;
  security?: number | null;
  tech_level?: number | null;
  wealth?: number | null;
  standard_of_living?: number | null;
  development_level?: number | null;
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

export interface LayoutImportRequest {
  source?: 'spansh';
}

export interface LayoutImportSummary {
  bodies_found: number;
  stations_found: number;
  bodies_upserted: number;
  stations_upserted: number;
  warnings_count: number;
}

export interface LayoutImportResponse {
  system_id64: number;
  source: 'spansh';
  status: 'success' | 'partial' | 'failed';
  fetched_at: string;
  summary: LayoutImportSummary;
  warnings: string[];
  errors: string[];
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

export interface CPRepairAction {
  action_type: string;
  facility_template_id?: string | null;
  facility_name?: string | null;
  from_step?: number | null;
  to_step?: number | null;
  target_step?: number | null;
  set_primary_port?: boolean | null;
  notes: string[];
}

export interface CPRepairSuggestion {
  suggestion_id: string;
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info' | string;
  summary: string;
  reason: string;
  affected_steps: number[];
  expected_effect: string;
  action: string;
  suggested_action?: CPRepairAction | null;
  confidence: string;
  caveats: string[];
}

export interface SimulationTimelineStep {
  step: number;
  facility_template_id: string;
  facility_name: string;
  yellow_before: number;
  yellow_after: number;
  green_before: number;
  green_after: number;
  yellow_delta: number;
  green_delta: number;
  warnings: string[];
  notes?: string[];
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

export interface EconomyInfluence {
  source_id: string;
  source_name: string;
  source_type: string;
  target_port_id: string;
  target_port_name: string;
  local_body_id?: string | null;
  economy: string;
  value: number;
  influence_type: string;
  link_type?: string | null;
  confidence: string;
  reason: string;
  caveats: string[];
}

export interface PortEconomyState {
  port_id: string;
  port_name: string;
  local_body_id?: string | null;
  body_name?: string | null;
  location_type: string;
  effective_role: string;
  inherited_economies: Record<string, number>;
  direct_economies: Record<string, number>;
  strong_link_economies: Record<string, number>;
  weak_link_economies: Record<string, number>;
  pass_through_economies: Record<string, number>;
  converted_port_economies: Record<string, number>;
  final_economy_strengths: Record<string, number>;
  final_economy_composition: Record<string, number>;
  economy_order: string[];
  top_two: string[];
  tertiary_economies: string[];
  purity_score: number;
  contamination_risk: string;
  contamination_sources: EconomyInfluence[];
  influences: EconomyInfluence[];
  warnings: string[];
  strengths: string[];
  recommendations: string[];
}

export interface ServiceUnlockEntry {
  service: string;
  status: 'active' | 'locked' | 'unknown' | string;
  source_id?: string | null;
  source_name?: string | null;
  source_type?: string | null;
  target_port_id: string;
  target_port_name: string;
  local_body_id?: string | null;
  unlock_type: string;
  link_type?: string | null;
  confidence: string;
  reason: string;
  requirements: string[];
  caveats: string[];
}

export interface PortServiceState {
  port_id: string;
  port_name: string;
  local_body_id?: string | null;
  body_name?: string | null;
  location_type: string;
  effective_role: string;
  active_services: Record<string, ServiceUnlockEntry>;
  locked_services: Record<string, ServiceUnlockEntry>;
  unknown_services: Record<string, ServiceUnlockEntry>;
  service_sources: ServiceUnlockEntry[];
  warnings: string[];
  recommendations: string[];
}

export interface ObservationSummary {
  status: string;
  observed_facts_count: number;
  confirmed_count: number;
  mismatch_count: number;
  observed_only_count: number;
  predicted_only_count: number;
  unknown_count: number;
  confidence_impact: string;
  summary: string;
}

export interface PredictionObservationDiff {
  area: string;
  subject_id: string;
  subject_type: string;
  predicted_value: unknown;
  observed_value: unknown;
  status: string;
  severity: string;
  confidence: string;
  reason: string;
  recommended_action?: string | null;
  source_type?: string | null;
  observed_at?: string | null;
}

export interface SimulationInheritedEconomy {
  source_body_id?: string | null;
  source_body_name?: string | null;
  base_economies: string[];
  modifier_economies: string[];
  weights: Record<string, number>;
  purity: number;
  confidence: number;
  caveats: string[];
  strategic_tags: string[];
}

export interface SimulateBuildResponse {
  system_id64: number;
  mechanics_version: string;
  target_archetype: string;
  final_score: number;
  composition_score: number;
  buildability_score: number;
  build_complexity: 'simple' | 'moderate' | 'advanced' | 'expert';
  confidence: number;
  cp: SimulationCPResult;
  cp_timeline: SimulationTimelineStep[];
  cp_repair_suggestions: CPRepairSuggestion[];
  observation_summary: ObservationSummary;
  prediction_observation_diffs: PredictionObservationDiff[];
  economy_composition: Record<string, number>;
  economy_order: string[];
  economy_stack: Record<string, unknown>;
  port_economy_states: PortEconomyState[];
  influence_ledger: EconomyInfluence[];
  inherited_economies: SimulationInheritedEconomy[];
  topology: Record<string, unknown>;
  services: Record<string, { status: string; reason: string; requirements: string[] }>;
  port_service_states: PortServiceState[];
  service_unlock_ledger: ServiceUnlockEntry[];
  data_quality: Record<string, string>;
  confidence_signals: Array<{ area: string; level: string; reason: string; impact?: number | null }>;
  mechanics_trace: Record<string, Array<{
    category: string;
    label: string;
    description: string;
    value_before?: number | null;
    value_after?: number | null;
    delta?: number | null;
    confidence: string;
    source?: string | null;
  }>>;
  top_two_alignment: string;
  contamination_risk: string;
  warnings: string[];
  strengths: string[];
  recommendations: string[];
  mechanics_notes: string[];
  links: SimulationLinks;
}

export interface RecommendedBuildPlan {
  id: string;
  label: string;
  summary: string;
  complexity: 'simple' | 'moderate' | 'advanced' | 'expert';
  confidence: number;
  final_score: number;
  composition_score: number;
  buildability_score: number;
  economy_result: Record<string, number>;
  port_economy_summary: string[];
  cp_result: SimulationCPResult;
  build_order: SimulateBuildPlacement[];
  strengths: string[];
  warnings: string[];
  tradeoffs: string[];
  next_actions: string[];
  selected_body_id?: string | null;
  selected_body_name?: string | null;
  body_selection_reason: string;
  mechanics_basis: string[];
  economy_caveats: string[];
  assumptions: string[];
  regional_role?: string | null;
  nearest_colony_distance?: number | null;
  archetype_regional_fit?: number | null;
  regional_rationale: Record<string, unknown>;
  decision_explanation: {
    why_this_plan_won?: string[];
    why_not_simpler?: string[];
    why_not_more_advanced?: string[];
    main_tradeoffs?: string[];
    sensitive_assumptions?: string[];
    confidence_summary?: string;
  };
  rank_breakdown: Record<string, number>;
  simulation_request: SimulateBuildRequest;
  is_default: boolean;
}

export interface RecommendedBuildsResponse {
  system_id64: number;
  mechanics_version: string;
  target_archetype: string;
  best_suggested_archetype: string;
  recommended_next_action: string;
  plans: RecommendedBuildPlan[];
  warnings: string[];
}

export interface RegionalAnalysisResponse {
  system_id64: number;
  mechanics_version: string;
  nearest_colonised_system?: {
    id64?: number | null;
    name?: string | null;
    distance_ly?: number | null;
  } | null;
  counts: {
    within_25ly: number;
    within_50ly: number;
    within_100ly: number;
    within_250ly: number;
  };
  scores: {
    isolation: number;
    density: number;
    expansion: number;
    competition: number;
  };
  regional_role: string;
  archetype_regional_fit: Record<string, number>;
  rationale: {
    summary?: string;
    strengths?: string[];
    warnings?: string[];
    archetype_notes?: Record<string, string>;
  };
  data_quality: Record<string, string>;
  confidence_signals: Array<{ area: string; level: string; reason: string; impact?: number | null }>;
  computed_at?: string | null;
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

// ─── Optimiser Candidate Generation / Ranking (Stages 5A-5C) ────────────────
export interface OptimiserCandidatePlacement {
  facility_template_id: string;
  local_body_id?: string | null;
  is_primary_port: boolean;
  build_order: number;
}

export interface OptimiserCandidatePreviewSummary {
  final_score?: number | null;
  composition_score?: number | null;
  buildability_score?: number | null;
  confidence?: number | null;
  build_complexity?: string | null;
  warnings_count: number;
  cp_negative?: boolean | null;
  top_two_alignment?: string | null;
}

export interface OptimiserCandidate {
  candidate_id: string;
  label: string;
  target_archetype: string;
  strategy: string;
  placements: OptimiserCandidatePlacement[];
  rationale: string[];
  warnings: string[];
  assumptions: string[];
  tags: string[];
  preview_summary?: OptimiserCandidatePreviewSummary | null;
}

export interface OptimiserRankBreakdown {
  preview_score_component: number;
  composition_component: number;
  buildability_component: number;
  confidence_component: number;
  alignment_component: number;
  warning_penalty: number;
  cp_penalty: number;
  strategy_modifier: number;
  total_score: number;
  reasons: string[];
}

export interface RankedOptimiserCandidate {
  candidate_id: string;
  rank: number;
  rank_score: number;
  rank_tier: string;
  rank_breakdown: OptimiserRankBreakdown;
}

export interface OptimiserRanking {
  target_archetype: string;
  ranked_candidates: RankedOptimiserCandidate[];
  warnings: string[];
  assumptions: string[];
}

export interface OptimiserCandidatesRequest {
  system_id64: number;
  target_archetype?: string;
  target_archetype_key?: string;
  max_candidates?: number;
  preferred_body_ids?: string[];
  allow_estimated_data?: boolean;
  run_preview?: boolean;
  include_ranking?: boolean;
}

export interface OptimiserCandidatesResponse {
  system_id64: number;
  target_archetype: string;
  candidate_count: number;
  candidates: OptimiserCandidate[];
  warnings: string[];
  assumptions: string[];
  ranking?: OptimiserRanking | null;
}

// ─── Stage 6B Observed Evidence (Observed Facts) ──────────────────────────
//
// Wire types matching the Stage 6A backend observed-facts CRUD API. These
// model passive evidence — what a user actually saw in-game — and are
// recorded entirely separately from predictions. They MUST NOT change
// optimiser ranking, candidate generation, Simulation Preview scoring,
// or any simulation mechanics. See `apps/api/src/observations/api_models.py`
// for the source of truth.
//
// The full backend vocabulary for `ObservationSource` includes `imported`
// and `inferred`, but they are reserved for later stages. The Stage 6B
// manual-entry UI only creates observations with `source: 'manual'`.
export type ObservationSource =
  | 'manual'
  | 'test_fixture'
  | 'imported'
  | 'inferred';

export type ObservedFactType =
  | 'service_presence'
  | 'economy_presence'
  | 'facility_state'
  | 'cp_value'
  | 'build_outcome'
  | 'prediction_match'
  | 'prediction_mismatch'
  | 'note';

export type ObservedSubjectType =
  | 'system'
  | 'body'
  | 'facility'
  | 'service'
  | 'economy'
  | 'build'
  | 'simulation'
  | 'cp';

export type ObservedStatus =
  | 'observed_present'
  | 'observed_absent'
  | 'confirmed'
  | 'contradicted'
  | 'unknown'
  | 'unverified';

export type ObservedConfidence = 'low' | 'medium' | 'high';

/** Any JSON value (matches backend `JsonValue`). */
export type ObservedJsonValue =
  | string
  | number
  | boolean
  | { [key: string]: ObservedJsonValue }
  | ObservedJsonValue[]
  | null;

export interface ObservedFact {
  observation_id: string;
  system_id64: number;
  created_at: string;
  updated_at: string | null;
  source: ObservationSource | string;
  fact_type: ObservedFactType | string;
  subject_type: ObservedSubjectType | string;
  subject_id: string | null;
  status: ObservedStatus | string;
  observed_value?: ObservedJsonValue;
  expected_value?: ObservedJsonValue;
  confidence: ObservedConfidence | string;
  notes?: string | null;
  build_fingerprint?: string | null;
  simulation_fingerprint?: string | null;
  target_archetype?: string | null;
  facility_template_id?: string | null;
  local_body_id?: string | null;
  service_id?: string | null;
  economy?: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
}

export interface ObservedFactCreateRequest {
  system_id64: number;
  // The UI only ever sends 'manual', but the backend accepts 'test_fixture'
  // for tests. 'imported' and 'inferred' are intentionally not part of the
  // create-form options exposed in Stage 6B.
  source: 'manual' | 'test_fixture';
  fact_type: ObservedFactType;
  subject_type: ObservedSubjectType;
  subject_id?: string | null;
  status: ObservedStatus;
  observed_value?: ObservedJsonValue;
  expected_value?: ObservedJsonValue;
  confidence?: ObservedConfidence;
  notes?: string | null;
  build_fingerprint?: string | null;
  simulation_fingerprint?: string | null;
  target_archetype?: string | null;
  facility_template_id?: string | null;
  local_body_id?: string | null;
  service_id?: string | null;
  economy?: string | null;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface ObservedFactUpdateRequest {
  source?: 'manual' | 'test_fixture';
  fact_type?: ObservedFactType;
  subject_type?: ObservedSubjectType;
  subject_id?: string | null;
  status?: ObservedStatus;
  observed_value?: ObservedJsonValue;
  expected_value?: ObservedJsonValue;
  confidence?: ObservedConfidence;
  notes?: string | null;
  build_fingerprint?: string | null;
  simulation_fingerprint?: string | null;
  target_archetype?: string | null;
  facility_template_id?: string | null;
  local_body_id?: string | null;
  service_id?: string | null;
  economy?: string | null;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface ObservationFactSummary {
  total_count: number;
  by_fact_type: Record<string, number>;
  by_status: Record<string, number>;
  by_confidence: Record<string, number>;
  latest_observed_at: string | null;
}

export interface ObservedFactListResponse {
  facts: ObservedFact[];
  total: number;
  limit: number;
  offset: number;
  summary: ObservationFactSummary;
}

export interface ObservedFactDeleteResponse {
  observation_id: string;
  deleted: boolean;
}

export interface ListObservedFactsParams {
  system_id64: number;
  fact_type?: ObservedFactType | string;
  subject_type?: ObservedSubjectType | string;
  status?: ObservedStatus | string;
  target_archetype?: string;
  build_fingerprint?: string;
  simulation_fingerprint?: string;
  limit?: number;
  offset?: number;
}

// ─── Stage 6D Predicted-vs-Observed Validation (Stage 6C compare API) ─────
//
// Wire types matching the Stage 6C `POST /api/observations/compare`
// response. Stage 6D renders these in the Colony Planner Validation
// section. The compare API is read-only; nothing the Validation UI does
// changes Simulation Preview scoring, optimiser ranking, generated
// candidates, or persisted observed evidence. See
// `apps/api/src/observations/comparison_models.py` for the backend
// source of truth.
export type ComparisonStatus =
  | 'confirmed'
  | 'contradicted'
  | 'predicted_only'
  | 'observed_only'
  | 'unknown'
  | 'unverified';

export type ComparisonSeverity = 'info' | 'low' | 'medium' | 'high';

export type ComparisonOverallStatus =
  | 'no_observations'
  | 'confirmed'
  | 'mixed'
  | 'needs_review'
  | 'insufficient_evidence';

export type ComparisonConfidenceImpact =
  | 'none'
  | 'strengthened'
  | 'weakened'
  | 'mixed'
  | 'insufficient_evidence';

export interface ObservationEvidenceMatch {
  observation_id: string;
  fact_type: string;
  subject_type: string;
  subject_id: string | null;
  status: string;
  confidence: string;
  observed_value?: ObservedJsonValue | null;
  expected_value?: ObservedJsonValue | null;
  notes?: string | null;
}

export interface PredictionObservationComparison {
  comparison_id: string;
  area: string;
  subject_type: string;
  subject_id: string | null;
  predicted_value: ObservedJsonValue | null;
  observed_value: ObservedJsonValue | null;
  status: ComparisonStatus | string;
  severity: ComparisonSeverity | string;
  confidence: string;
  reason: string;
  recommended_action?: string | null;
  evidence: ObservationEvidenceMatch[];
  prediction_source?: string | null;
}

export interface PredictionObservationComparisonSummary {
  status: ComparisonOverallStatus | string;
  observed_facts_count: number;
  compared_predictions_count: number;
  confirmed_count: number;
  contradicted_count: number;
  observed_only_count: number;
  predicted_only_count: number;
  unknown_count: number;
  unverified_count: number;
  confidence_impact: ComparisonConfidenceImpact | string;
  summary: string;
}

export interface PredictionObservationCompareRequest {
  system_id64: number;
  target_archetype: string | null;
  /**
   * Current Simulation Preview prediction. Stage 6D passes the full
   * `SimulateBuildResponse` verbatim — the backend treats `prediction`
   * as an opaque JSON object and only requires it to be object-shaped.
   */
  prediction: Record<string, unknown>;
  /**
   * Mode B override: when supplied, the backend uses this list verbatim
   * and skips loading persisted facts. Stage 6D never sets this; the
   * Validation panel relies on Mode A so the backend can serve
   * authoritative persisted evidence for the system.
   */
  observed_facts?: ObservedFactCreateRequest[];
  fact_load_limit?: number;
}

export interface PredictionObservationCompareResponse {
  system_id64: number;
  target_archetype: string | null;
  generated_at: string;
  summary: PredictionObservationComparisonSummary;
  comparisons: PredictionObservationComparison[];
  warnings: string[];
  assumptions: string[];
}

// ─── Stage 6E Validation Review Guidance ───────────────────────────────
//
// Advisory review guidance built from the Stage 6C comparison result. It
// identifies areas to investigate next and does not change mechanics,
// scoring, optimiser ranking, generated candidates, predictions, or
// persisted observations.
export type ValidationReviewStatus =
  | 'no_action'
  | 'monitor'
  | 'review_recommended'
  | 'review_high_priority'
  | 'insufficient_evidence'
  | 'mixed_evidence';

export type ValidationReviewArea =
  | 'service_rules'
  | 'economy_rules'
  | 'cp_rules'
  | 'facility_rules'
  | 'build_outcome'
  | 'prediction_claims'
  | 'evidence_quality'
  | 'general';

export type ValidationEvidenceStrength =
  | 'none'
  | 'weak'
  | 'moderate'
  | 'strong'
  | 'mixed';

export interface ValidationReviewSignal {
  signal_id: string;
  area: ValidationReviewArea | string;
  severity: ComparisonSeverity | 'none' | string;
  confidence: string;
  status: ValidationReviewStatus | string;
  title: string;
  message: string;
  recommended_action?: string | null;
  comparison_ids: string[];
}

export interface ValidationReviewSummary {
  overall_review_status: ValidationReviewStatus | string;
  confidence_impact: ComparisonConfidenceImpact | string;
  highest_severity: ComparisonSeverity | 'none' | string;
  review_needed_count: number;
  evidence_strength: ValidationEvidenceStrength | string;
  primary_review_areas: string[];
  summary: string;
}

export interface ValidationReviewRequest extends PredictionObservationCompareRequest {}

export interface ValidationReviewResponse {
  system_id64: number;
  target_archetype: string | null;
  generated_at: string;
  summary: ValidationReviewSummary;
  signals: ValidationReviewSignal[];
  warnings: string[];
  assumptions: string[];
}
