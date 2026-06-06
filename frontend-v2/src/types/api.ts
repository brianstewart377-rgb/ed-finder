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

export interface EnrichmentStatusArtifact {
  file_name: string;
  exists: boolean;
  updated_at?: string | null;
  age_seconds?: number | null;
  path_visible: false;
}

export interface EnrichmentStationStatus {
  available: boolean;
  configured: boolean;
  state: string;
  message: string;
  source: 'station_enrichment_status_json';
  artifact?: EnrichmentStatusArtifact | null;
  checkpoint?: {
    exists?: boolean | null;
    valid?: boolean | null;
    processed_count?: number | null;
    last_system_id64?: number | null;
    invalid_entry_count?: number | null;
    error?: string | null;
  } | null;
  latest_run?: {
    output_root_exists?: boolean | null;
    output_dir_name?: string | null;
    latest_all_records_output_dir_name?: string | null;
    latest_any_output_dir_name?: string | null;
    latest_log_file_name?: string | null;
    latest_log_file_exists?: boolean | null;
  } | null;
  latest_batch?: {
    number?: number | null;
    state?: string | null;
    latest_phase_name?: string | null;
    latest_report_file_name?: string | null;
    latest_stderr_file_name?: string | null;
  } | null;
  latest_report?: {
    valid?: boolean | null;
    phase_name?: string | null;
    systems_processed?: number | null;
    metadata_updates?: number | null;
    confirmed_links?: number | null;
    conflicts?: number | null;
    skipped?: number | null;
    fetch_errors?: number | null;
    systems_fetch_failed?: number | null;
    suppressed_station_writes?: number | null;
    ignored_transient_non_slot?: number | null;
    dirty_marked_planned?: string | null;
    error?: string | null;
  } | null;
  latest_progress?: {
    current?: number | null;
    total?: number | null;
    batch_progress_percent?: number | null;
    latest_system_name?: string | null;
    latest_system_id64?: number | null;
    fetch_errors?: number | null;
    systems_fetch_failed?: number | null;
    all_records_aborted?: boolean | null;
  } | null;
  rate_limit?: {
    recent_429_lines?: number | null;
    max_consecutive_429_lines?: number | null;
    repeated_429_detected?: boolean | null;
    guard_warning_429_count?: number | null;
    most_recent_429_system?: string | null;
    most_recent_429_system_id64?: number | null;
    most_recent_retry_after?: string | null;
    most_recent_backoff_seconds?: number | null;
  } | null;
  warnings: string[];
}

export interface EnrichmentWarehouseStatus {
  available: boolean;
  configured: boolean;
  state: string;
  message: string;
  source: 'warehouse_reconciliation_status_json';
  artifact?: EnrichmentStatusArtifact | null;
  latest_snapshot_load?: {
    source_run_key?: string | null;
    source_file_key?: string | null;
    source?: string | null;
    source_files_considered?: number | null;
    source_type_distribution?: Record<string, number> | null;
    source_format_distribution?: Record<string, number> | null;
  } | null;
  latest_reconciliation_run?: {
    schema_version?: string | null;
    coverage_schema_version?: string | null;
    dry_run?: boolean | null;
    report_only?: boolean | null;
    canonical_writes_planned?: number | null;
    staged_station_rows_considered?: number | null;
    staged_body_rows_considered?: number | null;
    staged_ring_rows_considered?: number | null;
    canonical_matches_found?: number | null;
    canonical_misses?: number | null;
    ambiguous_matches?: number | null;
    insufficient_evidence?: number | null;
    warnings?: number | null;
    errors?: number | null;
  } | null;
  source_coverage?: {
    station_candidates?: number | null;
    body_candidates?: number | null;
    ring_candidates?: number | null;
    systems_with_station_evidence?: number | null;
    systems_missing_station_evidence?: number | null;
    trusted_ring_evidence_bodies?: number | null;
    unknown_ring_evidence_bodies?: number | null;
    explicit_no_ring_evidence_bodies?: number | null;
    staged_ring_candidates?: number | null;
    trusted_local_matched_ring_candidates?: number | null;
  } | null;
  evidence_health?: {
    unresolved_stations?: number | null;
    blocked_conflicts?: number | null;
    risky_conflicts?: number | null;
    stale_records?: number | null;
    volatile_records?: number | null;
    stale_or_undated_source_records?: number | null;
    malformed_or_skipped_rows?: number | null;
    duplicate_source_records?: number | null;
    source_identity_conflicts?: number | null;
    high_value_systems_needing_better_evidence?: number | null;
  } | null;
  canonical_safety?: {
    canonical_tables_untouched?: boolean | null;
    canonical_writes_planned?: number | null;
    dry_run?: boolean | null;
    report_only?: boolean | null;
  } | null;
  warnings: string[];
  errors: string[];
}


export interface AdminDataStatusCountRow {
  rows: number;
  [key: string]: string | number | boolean | null;
}

export interface AdminDataStatusRecentUpdate {
  canonical_station_id: number;
  canonical_station_name: string;
  system_id64: number;
  station_type: string;
  station_type_source: string | null;
  station_type_updated_at: string | null;
}

export interface AdminDataStatus {
  schema_version: 'admin_data_status/v1';
  read_only: boolean;
  transaction_read_only: string;
  station_counts: {
    total_station_rows: number;
    unknown_station_rows: number;
    coriolis_station_rows: number;
    dodec_station_rows: number;
    rows_with_station_type_source: number;
  };
  station_type_counts: AdminDataStatusCountRow[];
  station_type_source_counts: AdminDataStatusCountRow[];
  identity_counts: {
    total_identity_rows: number;
    confirmed_identity_rows: number;
    rows_with_conflict_reason: number;
    rows_with_edsm_station_id: number;
    rows_with_market_id: number;
  };
  identity_source_status_counts: AdminDataStatusCountRow[];
  unknown_station_source_counts: Array<{
    source_station_type: string | null;
    rows: number;
  }>;
  recent_station_type_updates: AdminDataStatusRecentUpdate[];
  policy_summary: {
    dodec_supported: boolean;
    fleet_carriers_remain_unknown: boolean;
    construction_depots_remain_unknown: boolean;
  };
  safety_summary: {
    db_read_only_confirmed: boolean;
    db_writes_performed: boolean;
    migrations_performed: boolean;
    station_type_writes_performed: boolean;
    canonical_apply_performed: boolean;
  };
}

export interface OperatorSourceRunSummary {
  source_run_key: string;
  source_name: string | null;
  source_category: string | null;
  domain: string | null;
  import_scope: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  rows_read: number;
  rows_staged: number;
  rows_rejected: number;
  rows_skipped: number;
  artifact_present: boolean;
  artifact_hash_present: boolean;
  bridge_present: boolean;
  staging_rows_known: boolean;
  trigger_context: string | null;
  git_commit_sha: string | null;
  error_code: string | null;
  error_summary: string | null;
}

export interface OperatorArtifactSummary {
  source_run_key: string;
  artifact_path_redacted: string | null;
  artifact_sha256: string | null;
  artifact_integrity_sha256: string | null;
  artifact_record_present: boolean;
  file_exists: boolean | null;
  file_sha256_matches: boolean | null;
  integrity_hash_matches: boolean | null;
  schema_version: string | null;
  rows_read: number;
  rows_staged: number;
  status: string | null;
  validation_note: string;
}

export interface OperatorBridgeSummary {
  bridge_key: string;
  legacy_source_run_id: number | null;
  source_run_key: string;
  bridge_present: boolean;
  dry_run: boolean | null;
  adapter_name: string | null;
  adapter_version: string | null;
  target_staging_fk: string;
  metadata_has_compatibility_bridge: boolean;
  staging_policy_blocks_source_runs_id: boolean;
}

export interface OperatorDiagnosticRowSummary {
  row_id: number;
  legacy_source_run_id: number | null;
  station_name: string | null;
  station_type: string | null;
  system_name: string | null;
  source_class: string | null;
  confidence: string | null;
  marker_keys: string[];
  canonical_write_allowed: boolean | null;
}

export interface OperatorStagingImpactSummary {
  source_run_key: string | null;
  bridge_key: string | null;
  legacy_source_run_id: number;
  staging_table: string;
  rows_total: number;
  rows_diagnostic_only: number;
  rows_canonical_write_blocked: number;
  rows_with_stage_markers: number;
  rows_using_legacy_bridge_id: number;
  rows_using_source_runs_id: number;
  sample_rows: OperatorDiagnosticRowSummary[];
  warnings: string[];
}

export interface OperatorSourceRunDetail {
  summary: OperatorSourceRunSummary;
  importer_name: string | null;
  importer_version: string | null;
  source_uri_redacted: string | null;
  source_input_sha256: string | null;
  source_manifest_sha256: string | null;
  safety_boundary: Record<string, unknown>;
  metadata_summary: Record<string, unknown>;
  artifact_summary: OperatorArtifactSummary;
  bridge_summary: OperatorBridgeSummary;
  staging_impact_summary: OperatorStagingImpactSummary | null;
  validation_warnings: string[];
  operator_notes: string[];
}

export interface OperatorSafetyGateSummary {
  no_running_source_runs: boolean;
  latest_artifacts_present: boolean;
  bridge_fk_path_verified: boolean;
  diagnostic_rows_isolated: boolean;
  no_failed_unrecovered_source_runs: boolean;
  scheduler_assumed_disabled: boolean;
  canonical_apply_assumed_disabled: boolean;
  safe_to_proceed: boolean;
  blockers: string[];
  latest_source_run_key: string | null;
  notes: string[];
}


// ─── Stage 18H Warehouse-to-Planner Evidence Bridge (read-only) ───────────
//
// A typed, read-only model for surfacing carefully selected warehouse /
// report-only evidence context in planner-facing UI. It is EVIDENCE, NOT
// TRUTH. It must never mutate planner state, Build Plans, roles, observed
// evidence, validation, scoring, Simulation Preview, optimiser output, or
// canonical data. See
// `docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md`.
//
// Stage 18H ships the model plus a safe, source-labelled placeholder card.
// The current Stage 18G warehouse artifact is admin-gated and aggregate-only
// (no per-system linkage), so the planner card defaults to the `unavailable`
// (unknown) state rather than guessing. Missing evidence stays unknown — it
// never means false / no evidence.

/** Where a piece of planner evidence comes from. Always shown to the user. */
export type WarehouseEvidenceSource =
  | 'canonical'              // ED-Finder canonical app data (the planner's truth)
  | 'observed'               // user/imported observed evidence
  | 'warehouse_report_only'  // offline warehouse reconciliation report evidence
  | 'unknown';               // source not established / not safely linkable

/** Whether any warehouse evidence summary is available for display. */
export type WarehouseEvidenceAvailability =
  | 'unavailable'   // no artifact / not safely linkable -> remains unknown
  | 'report_only';  // a report-only evidence summary is present

/** Conservative, source-labelled finding wording. No promotion language. */
export type WarehouseEvidenceLabel =
  | 'report_only'
  | 'needs_review'
  | 'verify'
  | 'unresolved'
  | 'stale'
  | 'blocked'
  | 'unknown';

export interface PlannerWarehouseEvidenceItem {
  label:   WarehouseEvidenceLabel;
  source:  WarehouseEvidenceSource;
  /** Short, human-readable summary. Must not contain secrets, DSNs, or paths. */
  summary: string;
}

export interface PlannerWarehouseEvidence {
  availability: WarehouseEvidenceAvailability;
  /**
   * Always true in Stage 18H: warehouse-derived evidence is report-only and is
   * never canonical truth. Typed as the literal `true` so callers cannot mark
   * warehouse evidence as canonical.
   */
  reportOnly:   true;
  items:        PlannerWarehouseEvidenceItem[];
}

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
