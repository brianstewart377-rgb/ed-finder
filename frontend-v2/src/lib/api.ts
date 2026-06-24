/**
 * Tiny fetch wrapper for the ed-finder API.
 *
 * Resolves the base URL in this order:
 *   1. import.meta.env.VITE_API_BASE  (set per environment in .env / .env.production)
 *   2. /api  — same-origin fallback when the bundle is served from the same
 *      host as the API (the production deploy via nginx).
 *
 * The wrapper is intentionally minimal — no axios, no react-query yet. We add
 * those only when we hit a real need (cancellation, retries, dedup, suspense).
 * Premature abstraction has bitten this codebase before; let's not.
 */
import type {
  AppStatus,
  AutocompleteResponse,
  CacheStats,
  EnrichmentStationStatus,
  EnrichmentWarehouseStatus,
  AdminDataStatus,
  FacilityTemplate,
  LayoutImportRequest,
  LayoutImportResponse,
  ListObservedFactsParams,
  ObservedFact,
  ObservedFactCreateRequest,
  ObservedFactDeleteResponse,
  ObservedFactListResponse,
  ObservedFactUpdateRequest,
  OptimiserCandidatesRequest,
  OptimiserCandidatesResponse,
  OperatorArtifactSummary,
  OperatorBridgeSummary,
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
  OperatorStagingImpactSummary,
  PredictionObservationCompareRequest,
  PredictionObservationCompareResponse,
  ProvenanceCockpitResponse,
  RecommendedBuildsResponse,
  RegionalAnalysisResponse,
  RerankRequest,
  RerankResponse,
  SearchResponse,
  SimulateBuildRequest,
  SimulateBuildResponse,
  SimulationSummary,
  SlotPredictionResponse,
  SystemBuildability,
  SystemDetail,
  SystemDetailResponse,
  SystemResult,
  ValidationReviewRequest,
  ValidationReviewResponse,
  WarehousePlannerEvidenceContract,
} from '@/types/api';

type LocalSearchBody = {
  reference_coords?: { x: number; y: number; z: number };
  filters?: {
    distance?:   { min?: number; max?: number };
    population?: Record<string, unknown>;
    economy?:    string;
  };
  size?:       number;
  from?:       number;
  sort_by?:    'distance' | 'rating' | 'population' | string;
  galaxy_wide?: boolean;
  min_rating?: number;
  /** Per-body-type min/max counts (server-side filter). */
  body_filters?: Record<string, { min?: number; max?: number }>;
  /** Top-level boolean toggles understood by local_search.py. */
  require_bio?:   boolean;
  require_geo?:   boolean;
  require_terra?: boolean;
};

const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, '') ??
  '/api'
);

function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  // Allow callers to force an /api-prefixed endpoint without doubling when
  // API_BASE already ends with /api.
  if (path.startsWith('/api/') && /\/api$/i.test(API_BASE)) {
    return `${API_BASE}${path.slice(4)}`;
  }
  return `${API_BASE}${path}`;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    public readonly body: string,
  ) {
    super(`API ${status} on ${path}: ${body}`);
    this.name = 'ApiError';
  }
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept:         'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    // Surface the FastAPI Problem-Details body so the caller can show a
    // useful error. The vanilla app drops the body here, which makes
    // debugging deploys painful.
    let body = '';
    try {
      body = await res.text();
    } catch { /* ignore */ }
    throw new ApiError(res.status, path, body || res.statusText);
  }
  return res.json() as Promise<T>;
}

// ── Endpoints we actually use in the POC ───────────────────────────────────
export interface EddnEvent {
  system_name: string;
  id64:        number;
  type:        string;
  timestamp:   string | null;
}

export interface RecentEventsResponse {
  events: EddnEvent[];
  jobs:   Record<string, unknown>;
}

export interface ProfileSyncPull<TBlob> {
  blob:       TBlob;
  updated_at: string;
  blob_bytes: number;
}

export interface ProfileSyncPush {
  updated_at: string;
  blob_bytes: number;
}

// ── Map layer types (backend returns `unknown` in generated OpenAPI) ────
export interface MapRegion {
  id: number;
  name: string;
  x: number | null;
  y: number | null;
  z: number | null;
  system_count: number | null;
}
export interface MapRegionsResponse {
  regions: MapRegion[];
  total_regions: number;
}

export interface MapClusterHull {
  anchor_id64: number;
  anchor_name: string;
  x: number | null;
  y: number | null;
  z: number | null;
  radius_ly: number;
  system_count: number;
  top_economy: string | null;
  top_score: number | null;
}
export interface MapClusterHullsResponse {
  clusters: MapClusterHull[];
  count: number;
  cached: boolean;
}

export interface MapHeatmapCell {
  cx: number;
  cy: number;
  cz: number;
  n: number;
  avg_score: number | null;
  max_score: number | null;
}
export interface MapHeatmapResponse {
  voxel_size: number;
  voxel_bucket: number;
  economy: string | null;
  cells: MapHeatmapCell[];
  count: number;
}

export interface MapTimelinePoint {
  date: string | null;
  count: number;
}
export interface MapTimelineResponse {
  bucket: string;
  points: MapTimelinePoint[];
  total: number;
}

export const api = {
  health(): Promise<{ status: string; database: string; version: string }> {
    return jsonFetch('/api/health');
  },

  autocomplete(q: string, limit = 10): Promise<AutocompleteResponse> {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return jsonFetch(`/local/autocomplete?${params.toString()}`);
  },

  localSearch(body: LocalSearchBody): Promise<SearchResponse> {
    return jsonFetch<SearchResponse>('/local/search', {
      method: 'POST',
      body:   JSON.stringify(body),
    });
  },

  // ── Watchlist ─────────────────────────────────────────────────────────
  watchlist(syncKey: string): Promise<{ sync_key?: string; watchlist: WatchlistEntry[] }> {
    return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}`);
  },
  watchAdd(syncKey: string, id64: number): Promise<{ ok: boolean; sync_key?: string }> {
    return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, { method: 'POST' });
  },
  watchRemove(syncKey: string, id64: number): Promise<{ ok: boolean; sync_key?: string }> {
    return jsonFetch(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, { method: 'DELETE' });
  },

  /** Full system detail (joins ratings + bodies + stations). Cached
   *  server-side via Redis under the `sys:{id64}` key, so calling this
   *  multiple times in a row is cheap. */
  async system(id64: number): Promise<SystemDetail> {
    const res = await jsonFetch<SystemDetailResponse>(`/system/${id64}`);
    // Endpoint returns {record, system} — same data twice for legacy compat.
    return res.record ?? res.system;
  },

  simulationSummary(id64: number, archetype?: string): Promise<SimulationSummary> {
    const params = archetype ? `?${new URLSearchParams({ archetype }).toString()}` : '';
    return jsonFetch(`/systems/${id64}/simulation-summary${params}`);
  },

  slotPredictions(id64: number): Promise<SlotPredictionResponse> {
    return jsonFetch(`/systems/${id64}/slot-predictions`);
  },

  buildability(id64: number, archetype?: string): Promise<SystemBuildability> {
    const params = archetype ? `?${new URLSearchParams({ archetype }).toString()}` : '';
    return jsonFetch(`/systems/${id64}/buildability${params}`);
  },

  recommendedBuilds(id64: number, archetype?: string): Promise<RecommendedBuildsResponse> {
    const params = archetype ? `?${new URLSearchParams({ archetype }).toString()}` : '';
    return jsonFetch(`/systems/${id64}/recommended-builds${params}`);
  },

  provenanceCockpit(id64: number): Promise<ProvenanceCockpitResponse> {
    return jsonFetch(`/colony-planner/system/${id64}/provenance-cockpit`);
  },

  warehousePlannerEvidence(id64: number): Promise<WarehousePlannerEvidenceContract> {
    return jsonFetch(`/colony-planner/system/${id64}/warehouse-planner-evidence`);
  },

  regionalAnalysis(id64: number): Promise<RegionalAnalysisResponse> {
    return jsonFetch(`/systems/${id64}/regional-analysis`);
  },

  facilityTemplates(): Promise<FacilityTemplate[]> {
    return jsonFetch('/facility-templates');
  },

  simulateBuild(body: SimulateBuildRequest): Promise<SimulateBuildResponse> {
    return jsonFetch('/simulate/build', {
      method: 'POST',
      body:   JSON.stringify(body),
    });
  },

  importSystemLayout(id64: number, body: LayoutImportRequest = { source: 'spansh' }): Promise<LayoutImportResponse> {
    return jsonFetch(`/colony-planner/system/${id64}/import-layout`, {
      method: 'POST',
      body:   JSON.stringify(body),
    });
  },

  optimiserCandidates(body: OptimiserCandidatesRequest): Promise<OptimiserCandidatesResponse> {
    return jsonFetch('/optimiser/candidates', {
      method: 'POST',
      body:   JSON.stringify({
        max_candidates: 5,
        allow_estimated_data: true,
        run_preview: true,
        include_ranking: true,
        ...body,
      }),
    });
  },

  recentEvents(limit = 20): Promise<RecentEventsResponse> {
    const params = new URLSearchParams({ limit: String(limit) });
    return jsonFetch(`/events/recent?${params.toString()}`, { cache: 'no-store' });
  },

  profileSyncPull<TBlob>(syncKey: string): Promise<ProfileSyncPull<TBlob>> {
    return jsonFetch(`/profile/sync/${encodeURIComponent(syncKey)}`);
  },

  profileSyncPush<TBlob>(syncKey: string, blob: TBlob): Promise<ProfileSyncPush> {
    return jsonFetch(`/profile/sync/${encodeURIComponent(syncKey)}`, {
      method: 'PUT',
      body:   JSON.stringify({ blob }),
    });
  },

  // ── Advanced Search Tuning / ratings rerank ──────────────────────────
  // This endpoint only reorders supplied Finder result IDs; it is separate
  // from Colony Planner optimiser candidates.
  rerank(body: RerankRequest): Promise<RerankResponse> {
    return jsonFetch('/ratings/rerank', {
      method: 'POST',
      body:   JSON.stringify(body),
    });
  },

  // ── Admin / ops ──────────────────────────────────────────────────────
  status(): Promise<AppStatus> {
    return jsonFetch('/status');
  },
  cacheStats(): Promise<CacheStats> {
    return jsonFetch('/cache/stats');
  },
  cacheClear(token: string): Promise<{ ok: boolean; message: string }> {
    return jsonFetch('/cache/clear', {
      method:  'POST',
      headers: { 'X-Admin-Token': token },
    });
  },
  rebuildClusters(token: string): Promise<{ message: string; job_id: string }> {
    return jsonFetch('/admin/rebuild-clusters', {
      method:  'POST',
      headers: { 'X-Admin-Token': token },
    });
  },
  rebuildRatings(token: string): Promise<{
    ok: boolean;
    message: string;
    dirty_before: number;
    cleared: number;
  }> {
    return jsonFetch('/admin/rebuild-ratings', {
      method:  'POST',
      headers: { 'X-Admin-Token': token },
    });
  },
  enrichmentStationStatus(token: string): Promise<EnrichmentStationStatus> {
    return jsonFetch('/admin/enrichment/station-status', {
      headers: { 'X-Admin-Token': token },
    });
  },
  enrichmentWarehouseStatus(token: string): Promise<EnrichmentWarehouseStatus> {
    return jsonFetch('/admin/enrichment/warehouse-status', {
      headers: { 'X-Admin-Token': token },
    });
  },
  adminDataStatus(token: string): Promise<AdminDataStatus> {
    return jsonFetch('/admin/data-status', {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSafetyGates(token: string): Promise<OperatorSafetyGateSummary> {
    return jsonFetch('/api/operator/safety-gates', {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSourceRuns(token: string, limit = 25): Promise<OperatorSourceRunSummary[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return jsonFetch(`/api/operator/source-runs?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSourceRunDetail(token: string, sourceRunKey: string): Promise<OperatorSourceRunDetail> {
    const params = new URLSearchParams({ source_run_key: sourceRunKey });
    return jsonFetch(`/api/operator/source-run-detail?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSourceRunArtifacts(token: string, sourceRunKey: string): Promise<OperatorArtifactSummary> {
    const params = new URLSearchParams({ source_run_key: sourceRunKey });
    return jsonFetch(`/api/operator/source-run-artifacts?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSourceRunBridge(token: string, sourceRunKey: string): Promise<OperatorBridgeSummary> {
    const params = new URLSearchParams({ source_run_key: sourceRunKey });
    return jsonFetch(`/api/operator/source-run-bridge?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorSourceRunStagingImpact(
    token: string,
    sourceRunKey: string,
    limit = 100,
  ): Promise<{
    source_run_key: string;
    bridge_present: boolean;
    staging_impact: OperatorStagingImpactSummary | null;
  }> {
    const params = new URLSearchParams({ source_run_key: sourceRunKey, limit: String(limit) });
    return jsonFetch(`/api/operator/source-run-staging-impact?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },
  operatorDiagnosticRows(
    token: string,
    options: { sourceRunKey?: string | null; limit?: number } = {},
  ): Promise<OperatorDiagnosticRowSummary[]> {
    const params = new URLSearchParams({ limit: String(options.limit ?? 25) });
    if (options.sourceRunKey) params.set('source_run_key', options.sourceRunKey);
    return jsonFetch(`/api/operator/diagnostic-staging-rows?${params.toString()}`, {
      headers: { 'X-Admin-Token': token },
    });
  },

  // ── Stage 6B Observed Evidence (Observed Facts) ────────────────────────
  // Passive evidence: records what a user actually saw in-game for a system
  // or build. These calls do NOT change Simulation Preview scoring, optimiser
  // ranking, or generated candidates. They are also not consumed by the
  // simulation/optimiser modules — see api-contracts.md "Stage 6A Observed
  // Facts API" for the contract details.
  listObservedFacts(params: ListObservedFactsParams): Promise<ObservedFactListResponse> {
    const usp = new URLSearchParams();
    usp.set('system_id64', String(params.system_id64));
    if (params.fact_type)              usp.set('fact_type',              params.fact_type);
    if (params.subject_type)           usp.set('subject_type',           params.subject_type);
    if (params.status)                 usp.set('status',                 params.status);
    if (params.target_archetype)       usp.set('target_archetype',       params.target_archetype);
    if (params.build_fingerprint)      usp.set('build_fingerprint',      params.build_fingerprint);
    if (params.simulation_fingerprint) usp.set('simulation_fingerprint', params.simulation_fingerprint);
    if (params.limit  !== undefined)   usp.set('limit',  String(params.limit));
    if (params.offset !== undefined)   usp.set('offset', String(params.offset));
    return jsonFetch(`/observations/facts?${usp.toString()}`);
  },

  createObservedFact(request: ObservedFactCreateRequest): Promise<ObservedFact> {
    return jsonFetch('/observations/facts', {
      method: 'POST',
      body:   JSON.stringify(request),
    });
  },

  updateObservedFact(observationId: string, request: ObservedFactUpdateRequest): Promise<ObservedFact> {
    return jsonFetch(`/observations/facts/${encodeURIComponent(observationId)}`, {
      method: 'PATCH',
      body:   JSON.stringify(request),
    });
  },

  deleteObservedFact(observationId: string): Promise<ObservedFactDeleteResponse> {
    return jsonFetch(`/observations/facts/${encodeURIComponent(observationId)}`, {
      method: 'DELETE',
    });
  },

  // ── Stage 6C Predicted-vs-Observed Comparison ──────────────────────────
  // Read-only comparison: takes a current prediction (a
  // SimulateBuildResponse, in practice) and asks the backend to compare
  // it against persisted observed evidence for the same system. Stage 6D
  // renders the result inside Colony Planner. This call does NOT mutate
  // any prediction, optimiser candidate, optimiser ranking, or persisted
  // observation. The backend operates in Mode A by default (it loads
  // persisted facts itself); Stage 6D never sends `observed_facts`.
  comparePredictionToObservations(
    request: PredictionObservationCompareRequest,
  ): Promise<PredictionObservationCompareResponse> {
    return jsonFetch('/observations/compare', {
      method: 'POST',
      body:   JSON.stringify(request),
    });
  },

  // ── Stage 6E Validation Review Guidance ─────────────────────────────
  // Read-only advisory guidance built from the Stage 6C comparison
  // result. This helper only calls the review endpoint; it does not run
  // Simulation Preview, optimiser candidate generation, or observation
  // mutations.
  reviewPredictionValidation(
    request: ValidationReviewRequest,
  ): Promise<ValidationReviewResponse> {
    return jsonFetch('/observations/review', {
      method: 'POST',
      body:   JSON.stringify(request),
    });
  },

  // ── Map layers ────────────────────────────────────────────────────────
  mapRegions(): Promise<MapRegionsResponse> {
    return jsonFetch('/map/regions');
  },

  mapClusterHulls(opts?: { min_count?: number; max_hulls?: number }): Promise<MapClusterHullsResponse> {
    const params = new URLSearchParams();
    if (opts?.min_count !== undefined) params.set('min_count', String(opts.min_count));
    if (opts?.max_hulls !== undefined) params.set('max_hulls', String(opts.max_hulls));
    const qs = params.toString();
    return jsonFetch(`/map/clusters/hulls${qs ? `?${qs}` : ''}`);
  },

  mapHeatmap(opts?: { voxel_size?: number; min_systems?: number; economy?: string | null }): Promise<MapHeatmapResponse> {
    const params = new URLSearchParams();
    if (opts?.voxel_size !== undefined) params.set('voxel_size', String(opts.voxel_size));
    if (opts?.min_systems !== undefined) params.set('min_systems', String(opts.min_systems));
    if (opts?.economy != null) params.set('economy', opts.economy);
    const qs = params.toString();
    return jsonFetch(`/map/heatmap${qs ? `?${qs}` : ''}`);
  },

  mapTimeline(opts?: { bucket?: 'day' | 'week' | 'month' | 'quarter' | 'year' }): Promise<MapTimelineResponse> {
    const params = new URLSearchParams();
    if (opts?.bucket) params.set('bucket', opts.bucket);
    const qs = params.toString();
    return jsonFetch(`/map/timeline${qs ? `?${qs}` : ''}`);
  },
};

export function getSlotPredictions(id64: number): Promise<SlotPredictionResponse> {
  return api.slotPredictions(id64);
}

export function getBuildability(id64: number, archetype?: string): Promise<SystemBuildability> {
  return api.buildability(id64, archetype);
}

export function getSimulationSummary(id64: number, archetype?: string): Promise<SimulationSummary> {
  return api.simulationSummary(id64, archetype);
}

export function getRecommendedBuilds(id64: number, archetype?: string): Promise<RecommendedBuildsResponse> {
  return api.recommendedBuilds(id64, archetype);
}

export function getProvenanceCockpit(id64: number): Promise<ProvenanceCockpitResponse> {
  return api.provenanceCockpit(id64);
}

export function getWarehousePlannerEvidence(id64: number): Promise<WarehousePlannerEvidenceContract> {
  return api.warehousePlannerEvidence(id64);
}

export function fetchOptimiserCandidates(request: OptimiserCandidatesRequest): Promise<OptimiserCandidatesResponse> {
  return api.optimiserCandidates(request);
}

export function getRegionalAnalysis(id64: number): Promise<RegionalAnalysisResponse> {
  return api.regionalAnalysis(id64);
}

export function getFacilityTemplates(): Promise<FacilityTemplate[]> {
  return api.facilityTemplates();
}

export function simulateBuild(request: SimulateBuildRequest): Promise<SimulateBuildResponse> {
  return api.simulateBuild(request);
}

// ── Stage 10E.1 Layout Import helper ─────────────────────────────────
//
// Manual refresh only. This helper only calls the layout-import endpoint;
// it does NOT run Simulation Preview, generate/load Suggested Builds, or
// mutate the in-memory Build Plan.
export function importSystemLayout(
  id64: number,
  request: LayoutImportRequest = { source: 'spansh' },
): Promise<LayoutImportResponse> {
  return api.importSystemLayout(id64, request);
}

// ── Stage 6B Observed Evidence helpers ──────────────────────────────────
//
// These are thin re-exports so feature modules can import named helpers
// rather than passing the whole `api` object around. The same passivity
// note applies: observed evidence does NOT affect predictions, optimiser
// ranking, candidate generation, or Simulation Preview scoring.
export function listObservedFacts(
  params: ListObservedFactsParams,
): Promise<ObservedFactListResponse> {
  return api.listObservedFacts(params);
}

export function createObservedFact(
  request: ObservedFactCreateRequest,
): Promise<ObservedFact> {
  return api.createObservedFact(request);
}

export function updateObservedFact(
  observationId: string,
  request: ObservedFactUpdateRequest,
): Promise<ObservedFact> {
  return api.updateObservedFact(observationId, request);
}

export function deleteObservedFact(
  observationId: string,
): Promise<ObservedFactDeleteResponse> {
  return api.deleteObservedFact(observationId);
}

// ── Stage 6C Predicted-vs-Observed Comparison helper ────────────────────
//
// Stage 6D renders the response of this call inside the Colony Planner
// Validation section. The helper is intentionally narrow: it only calls
// the compare endpoint and does NOT call `simulateBuild` or
// `fetchOptimiserCandidates`. Predictions are passed in by the caller so
// the Validation panel can compare against the *current* preview result
// rather than re-running simulation.
export function comparePredictionToObservations(
  request: PredictionObservationCompareRequest,
): Promise<PredictionObservationCompareResponse> {
  return api.comparePredictionToObservations(request);
}

// ── Stage 6E Validation Review helper ─────────────────────────────────
//
// The helper is intentionally narrow: it only calls the review endpoint
// and does NOT call `simulateBuild`, `fetchOptimiserCandidates`, or any
// observation mutation helper.
export function reviewPredictionValidation(
  request: ValidationReviewRequest,
): Promise<ValidationReviewResponse> {
  return api.reviewPredictionValidation(request);
}

// ── Map layer helpers ─────────────────────────────────────────────────
export function getMapRegions(): Promise<MapRegionsResponse> {
  return api.mapRegions();
}

export function getMapClusterHulls(
  opts?: Parameters<typeof api.mapClusterHulls>[0],
): Promise<MapClusterHullsResponse> {
  return api.mapClusterHulls(opts);
}

export function getMapHeatmap(
  opts?: Parameters<typeof api.mapHeatmap>[0],
): Promise<MapHeatmapResponse> {
  return api.mapHeatmap(opts);
}

export function getMapTimeline(
  opts?: Parameters<typeof api.mapTimeline>[0],
): Promise<MapTimelineResponse> {
  return api.mapTimeline(opts);
}

/** Shape of one row from the scoped Watchlist API. */
export interface WatchlistEntry {
  system_id64:        number;
  name:               string;
  x:                  number | null;
  y:                  number | null;
  z:                  number | null;
  population:         number | null;
  is_colonised:       boolean;
  added_at:           string;
  /** Latest rating (joined server-side). */
  score?:             number | null;
  economy_suggestion?: string | null;
  alert_min_score?:   number | null;
  alert_economy?:     string | null;
}

export type { LocalSearchBody, SystemResult };
