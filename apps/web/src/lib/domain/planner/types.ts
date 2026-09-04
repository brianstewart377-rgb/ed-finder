/**
 * Framework-neutral planner contracts owned by the Svelte application.
 *
 * These are deliberately narrow projections for the first planner-domain
 * migration tranche. They do not depend on the legacy React API type barrel.
 */

/** Elite Dangerous id64 values stay lossless decimal strings in web code. */
export type Id64 = `${bigint}`;

export interface FacilityTemplate {
  id: string;
  name: string;
  is_port: boolean;
  allowed_location: string;
}

export interface SystemBody {
  id?: string | number | null;
  name?: string | null;
  body_type?: string | null;
  is_landable?: boolean | null;
}

export interface RecommendedStep {
  step: number;
  facility_id?: string | null;
  facility_name?: string | null;
  location?: string | null;
  notes?: string | null;
  cumulative_yellow_cp?: number | null;
  cumulative_green_cp?: number | null;
}

export interface SimulateBuildPlacement {
  facility_template_id: string;
  local_body_id?: string | null;
  is_primary_port?: boolean;
  build_order: number;
}

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

export interface SimulationServiceState {
  status: string;
  [key: string]: unknown;
}

export interface SimulationPortServiceState {
  active_services: Record<string, unknown>;
  locked_services: Record<string, unknown>;
  unknown_services: Record<string, unknown>;
}

/** The preview fields consumed by this pure-domain tranche. */
export interface SimulateBuildResponse {
  final_score: number;
  confidence: number;
  cp: SimulationCPResult;
  cp_timeline: unknown[];
  cp_repair_suggestions: unknown[];
  economy_composition: Record<string, number>;
  economy_order: string[];
  services: Record<string, SimulationServiceState | null | undefined>;
  port_service_states: SimulationPortServiceState[];
}

export type ObservedJsonValue =
  | string
  | number
  | boolean
  | { [key: string]: ObservedJsonValue }
  | ObservedJsonValue[]
  | null;

export interface PredictionObservationComparison {
  status: string;
  [key: string]: unknown;
}

export interface PlannerSystemDetail {
  id64: Id64;
  name?: string | null;
}

export interface ObservedFact {
  fact_type: string;
}

export interface RoleReviewResult {
  consistencyLabel: string;
}

export type ProvenanceCockpitState = 'available' | 'stale' | 'unknown';

export interface ProvenanceGuardrails {
  stage19_paused: boolean;
  stage19_production_activation_complete: boolean;
  next_stage19_write_lane_authorized: boolean;
  canonical_apply_complete: boolean;
  rebaseline_complete: boolean;
  scheduler_enabled: boolean;
  db_writes_authorized: boolean;
  stage19_operator_commands_authorized: boolean;
}

export interface ProvenanceCockpitResponse {
  provenance_summary?: {
    latest_source_run_key?: string | null;
  } | null;
  evidence_panels: {
    source_run?: {
      artifact_name?: string | null;
    } | null;
    warehouse: {
      state: ProvenanceCockpitState;
      report_only: boolean;
      stale_records?: number | null;
    };
  };
  guardrails: ProvenanceGuardrails;
  warnings?: string[];
}
