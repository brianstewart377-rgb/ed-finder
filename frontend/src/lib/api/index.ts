import type {
  EvidenceSystemSummaryResponse,
  ExplorationFactsResponse,
  ExplorationImportReceipt,
  ExplorationImportRequest,
  FacilityTemplate,
  JournalImportReceipt,
  JournalImportRequest,
  JournalTelemetrySummaryResponse,
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
  PredictionObservationCompareRequest,
  PredictionObservationCompareResponse,
  ProvenanceCockpitResponse,
  RecommendedBuildsResponse,
  RegionalAnalysisResponse,
  SimulateBuildRequest,
  SimulateBuildResponse,
  SimulationSummary,
  SlotPredictionResponse,
  SystemArchetypeResponse,
  SystemBuildability,
  ValidationReviewRequest,
  ValidationReviewResponse,
  WarehousePlannerEvidenceContract,
} from '@/types/api';
import * as search from './search';
import * as planner from './planner';
import * as exploration from './exploration';
import * as observations from './observations';
import * as operator from './operator';
import * as map from './map';
import * as routes from './routes';
import * as powerplay from './powerplay';
import * as auth from './auth';

export type {
  CommanderPowerplayResponse,
  PowerplayHistoryResponse,
  PowerplayImportReceipt,
  PowerplayImportRequest,
  PowerplayJournalEventInput,
  PowerplaySystemState,
  PowerplaySystemsResponse,
} from './powerplay';

export { ApiError } from './core';
export type { AuthSession, AuthUser } from './auth';

export const api = {
  frontierLoginUrl: auth.frontierLoginUrl,
  authSession: auth.authSession,
  authLogout: auth.authLogout,
  claimOwner: auth.claimOwner,
  health: search.health,
  autocomplete: search.autocomplete,
  localSearch: search.localSearch,
  clusterSearch: search.clusterSearch,
  watchlist: search.watchlist,
  watchAdd: search.watchAdd,
  watchRemove: search.watchRemove,
  recentEvents: search.recentEvents,
  eliteNewsLatest: search.eliteNewsLatest,

  system: planner.system,
  archetypeSystem: planner.archetypeSystem,
  simulationSummary: planner.simulationSummary,
  slotPredictions: planner.slotPredictions,
  buildability: planner.buildability,
  recommendedBuilds: planner.recommendedBuilds,
  provenanceCockpit: planner.provenanceCockpit,
  warehousePlannerEvidence: planner.warehousePlannerEvidence,
  evidenceSystemSummary: planner.evidenceSystemSummary,
  importJournal: planner.importJournal,
  importExploration: exploration.importExploration,
  getExplorationFacts: exploration.getExplorationFacts,
  getExplorationTrail: exploration.getExplorationTrail,
  getExplorationViewportVisits: exploration.getExplorationViewportVisits,
  getExplorationSummary: exploration.getExplorationSummary,
  getExplorationCodexByRegion: exploration.getExplorationCodexByRegion,
  journalImportReceipt: planner.journalImportReceipt,
  journalTelemetry: planner.journalTelemetry,
  regionalAnalysis: planner.regionalAnalysis,
  facilityTemplates: planner.facilityTemplates,
  simulateBuild: planner.simulateBuild,
  importSystemLayout: planner.importSystemLayout,
  optimiserCandidates: planner.optimiserCandidates,
  archetypeRerank: planner.archetypeRerank,
  profileSyncPull: planner.profileSyncPull,
  profileSyncPush: planner.profileSyncPush,

  listObservedFacts: observations.listObservedFacts,
  createObservedFact: observations.createObservedFact,
  updateObservedFact: observations.updateObservedFact,
  deleteObservedFact: observations.deleteObservedFact,
  comparePredictionToObservations: observations.comparePredictionToObservations,
  reviewPredictionValidation: observations.reviewPredictionValidation,

  status: operator.status,
  cacheStats: operator.cacheStats,
  cacheClear: operator.cacheClear,
  rebuildClusters: operator.rebuildClusters,
  rebuildRatings: operator.rebuildRatings,
  enrichmentStationStatus: operator.enrichmentStationStatus,
  enrichmentWarehouseStatus: operator.enrichmentWarehouseStatus,
  adminDataStatus: operator.adminDataStatus,
  adminCronStatus: operator.adminCronStatus,
  adminRunOperation: operator.adminRunOperation,
  adminOperationHistory: operator.adminOperationHistory,
  operatorSafetyGates: operator.operatorSafetyGates,
  operatorSourceRuns: operator.operatorSourceRuns,
  operatorSourceRunDetail: operator.operatorSourceRunDetail,
  operatorSourceRunArtifacts: operator.operatorSourceRunArtifacts,
  operatorSourceRunBridge: operator.operatorSourceRunBridge,
  operatorSourceRunStagingImpact: operator.operatorSourceRunStagingImpact,
  operatorDiagnosticRows: operator.operatorDiagnosticRows,

  mapRegions: map.mapRegions,
  mapClusterHulls: map.mapClusterHulls,
  mapHeatmap: map.mapHeatmap,
  mapTimeline: map.mapTimeline,
  mapSystems: map.mapSystems,
  importPowerplay: powerplay.importPowerplay,
  powerplaySystems: powerplay.powerplaySystems,
  powerplayCommander: powerplay.powerplayCommander,
  powerplayHistory: powerplay.powerplayHistory,
  listRoutes: routes.listRoutes,
  getRoute: routes.getRoute,
  getPersonalTrail: routes.getPersonalTrail,
  listExpeditions: routes.listExpeditions,
  importSpanshRoute: routes.importSpanshRoute,
  saveExpedition: routes.saveExpedition,
};

export * from './routes';

export function getSlotPredictions(id64: number): Promise<SlotPredictionResponse> {
  return api.slotPredictions(id64);
}

export function getBuildability(id64: number, archetype?: string): Promise<SystemBuildability> {
  return api.buildability(id64, archetype);
}

export function getSystemArchetype(id64: number): Promise<SystemArchetypeResponse> {
  return api.archetypeSystem(id64);
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

export function getEvidenceSystemSummary(id64: number): Promise<EvidenceSystemSummaryResponse> {
  return api.evidenceSystemSummary(id64);
}

export function importJournal(request: JournalImportRequest): Promise<JournalImportReceipt> {
  return api.importJournal(request);
}

export function getJournalImportReceipt(runKey: string): Promise<JournalImportReceipt> {
  return api.journalImportReceipt(runKey);
}

export function importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt> {
  return api.importExploration(request);
}

export function getExplorationFacts(syncKey: string): Promise<ExplorationFactsResponse> {
  return api.getExplorationFacts(syncKey);
}

export function getJournalTelemetry(syncKey: string): Promise<JournalTelemetrySummaryResponse> {
  return api.journalTelemetry(syncKey);
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

// ── Stage 10E.1 Layout Import helper ──────────────────────────────────
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

// ── Stage 6B Observed Evidence helpers ────────────────────────────────
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

// ── Stage 6C Predicted-vs-Observed Comparison helper ──────────────────
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
export function getMapRegions(): Promise<map.MapRegionsResponse> {
  return api.mapRegions();
}

export function getMapClusterHulls(
  opts?: Parameters<typeof api.mapClusterHulls>[0],
): Promise<map.MapClusterHullsResponse> {
  return api.mapClusterHulls(opts);
}

export function getMapHeatmap(
  opts?: Parameters<typeof api.mapHeatmap>[0],
): Promise<map.MapHeatmapResponse> {
  return api.mapHeatmap(opts);
}

export function getMapTimeline(
  opts?: Parameters<typeof api.mapTimeline>[0],
): Promise<map.MapTimelineResponse> {
  return api.mapTimeline(opts);
}

export type { SystemResult } from '@/types/api';
export type {
  ClusterSearchApiResponse,
  ClusterSearchRequestBody,
  EddnEvent,
  EliteNewsItem,
  EliteNewsResponse,
  LocalSearchBody,
  RecentEventsResponse,
  WatchlistEntry,
} from './search';
export type { ProfileSyncPull, ProfileSyncPush } from './planner';
export type {
  MapClusterHull,
  MapClusterHullsResponse,
  MapHeatmapCell,
  MapHeatmapResponse,
  MapRegion,
  MapRegionsResponse,
  MapTimelinePoint,
  MapTimelineResponse,
  MapViewportSystem,
  MapViewportResponse,
  MapViewportBox,
} from './map';
export type {
  ExplorationCodexByRegionResponse,
  ExplorationSystemSummaryResponse,
  ExplorationTrailPoint,
  ExplorationTrailResponse,
  ExplorationViewportVisit,
  ExplorationViewportVisitsResponse,
} from './exploration';
