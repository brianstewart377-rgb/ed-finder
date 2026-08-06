# Split api.ts Into Domain Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `frontend/src/lib/api.ts` (828 lines, one `api` object plus ~20 duplicate named wrapper functions) into `frontend/src/lib/api/` with domain-scoped files behind a compatibility barrel, with zero import-path or call-site changes anywhere else in the frontend.

**Architecture:** Pure code movement, no logic changes. `core.ts` holds the shared request plumbing; `search.ts`, `planner.ts`, `observations.ts`, `operator.ts`, `map.ts` each own one domain's methods and types; `index.ts` reassembles the exact same `api` object shape and re-exports every named wrapper function unchanged. TypeScript resolves `@/lib/api` to `@/lib/api/index.ts` automatically once the flat file is gone.

**Tech Stack:** Frontend only (Vite + React 19 + TS 5, `frontend/`).

## Global Constraints

- No method's implementation changes — every function body moves verbatim from the current `frontend/src/lib/api.ts` (read it before starting; it is the source of truth for every implementation).
- Every one of the ~20 standalone named wrapper functions (`getSlotPredictions`, `getBuildability`, `getSystemArchetype`, `getSimulationSummary`, `getRecommendedBuilds`, `getProvenanceCockpit`, `getWarehousePlannerEvidence`, `getEvidenceSystemSummary`, `importJournal`, `getJournalImportReceipt`, `getJournalTelemetry`, `fetchOptimiserCandidates`, `getRegionalAnalysis`, `getFacilityTemplates`, `simulateBuild`, `importSystemLayout`, `listObservedFacts`, `createObservedFact`, `updateObservedFact`, `deleteObservedFact`, `comparePredictionToObservations`, `reviewPredictionValidation`, `getMapRegions`, `getMapClusterHulls`, `getMapHeatmap`, `getMapTimeline`) must still be exported from `@/lib/api` (i.e. from `index.ts`) with the exact same name and signature.
- The `api` object exported from `index.ts` must have the exact same shape (same method names, same nesting — it is flat, not nested by domain) as today's `api` object.
- `export type { LocalSearchBody, SystemResult }` (currently the last line of the file) must still work from `@/lib/api`.

---

### Task 1: Create the domain module files

**Files:**
- Create: `frontend/src/lib/api/core.ts`
- Create: `frontend/src/lib/api/search.ts`
- Create: `frontend/src/lib/api/planner.ts`
- Create: `frontend/src/lib/api/observations.ts`
- Create: `frontend/src/lib/api/operator.ts`
- Create: `frontend/src/lib/api/map.ts`
- Reference (read, do not modify yet): `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: named exports each subsequent file in this task/Task 2 imports from `./core` (`jsonFetch`, `resolveApiUrl`, `ApiError`, `operatorMutationHeaders`, `readSessionAdminToken`, `API_BASE`, `ADMIN_TOKEN_SESSION_KEY`) and each domain file's method functions + types (named exactly as they are today, e.g. `search.ts` exports a function named `health`, not `searchHealth`)

- [ ] **Step 1: Create `core.ts`**

Move from `api.ts`, verbatim: the `import type` lines this code actually needs from `@/types/api` (none currently — core has no type-import dependency), the block comment at the top of the file (lines 1-12, the "Tiny fetch wrapper" doc comment), `API_BASE` (lines 106-109), `ADMIN_TOKEN_SESSION_KEY` (line 111), `resolveApiUrl()` (lines 113-121), `readSessionAdminToken()` (lines 123-130), `operatorMutationHeaders()` (lines 132-136), `ApiError` class (lines 138-147), `jsonFetch()` (lines 149-170). Export `API_BASE`, `ADMIN_TOKEN_SESSION_KEY`, `resolveApiUrl`, `readSessionAdminToken`, `operatorMutationHeaders`, `ApiError`, `jsonFetch` (all of these — even ones not currently `export`ed in the flat file — since other domain files now need to import them across a file boundary).

- [ ] **Step 2: Create `search.ts`**

Move from `api.ts`, verbatim, the implementations (not the `api.` prefix — each becomes a standalone exported function) of: `health`, `autocomplete`, `localSearch`, `clusterSearch`, `watchlist`, `watchAdd`, `watchRemove`, `recentEvents`, `eliteNewsLatest`. Move these types verbatim: `LocalSearchBody` (lines 67-85), `ClusterSearchRequestBody` (87-97), `ClusterSearchApiResponse` (99-104), `EddnEvent` (173-178), `RecentEventsResponse` (180-183), `EliteNewsItem` (185-189), `EliteNewsResponse` (191-196), `WatchlistEntry` (805-826 in the current file — this is its new home, next to the methods that use it). Import `jsonFetch` from `./core`. Import only the `@/types/api` types this file's functions actually reference (`AutocompleteResponse`, `SearchResponse`).

- [ ] **Step 3: Create `planner.ts`**

Move from `api.ts`, verbatim, the implementations of: `system`, `archetypeSystem`, `simulationSummary`, `slotPredictions`, `buildability`, `recommendedBuilds`, `provenanceCockpit`, `warehousePlannerEvidence`, `evidenceSystemSummary`, `importJournal`, `journalImportReceipt`, `journalTelemetry`, `regionalAnalysis`, `facilityTemplates`, `simulateBuild`, `importSystemLayout`, `optimiserCandidates`, `archetypeRerank`, `profileSyncPull`, `profileSyncPush`. Move these types verbatim: `ProfileSyncPull` (198-202), `ProfileSyncPush` (204-207). Import `jsonFetch` from `./core`. Import the `@/types/api` types this file's functions actually reference (`SystemDetailResponse`, `SystemDetail`, `SystemArchetypeResponse`, `SimulationSummary`, `SlotPredictionResponse`, `SystemBuildability`, `RecommendedBuildsResponse`, `ProvenanceCockpitResponse`, `WarehousePlannerEvidenceContract`, `EvidenceSystemSummaryResponse`, `JournalImportRequest`, `JournalImportReceipt`, `JournalTelemetrySummaryResponse`, `RegionalAnalysisResponse`, `FacilityTemplate`, `SimulateBuildRequest`, `SimulateBuildResponse`, `LayoutImportRequest`, `LayoutImportResponse`, `OptimiserCandidatesRequest`, `OptimiserCandidatesResponse`, `DevelopmentRerankRequest`, `DevelopmentRerankResponse`).

- [ ] **Step 4: Create `observations.ts`**

Move from `api.ts`, verbatim, the implementations of: `listObservedFacts`, `createObservedFact`, `updateObservedFact`, `deleteObservedFact`, `comparePredictionToObservations`, `reviewPredictionValidation` (including their explanatory comments — these document real product-behavior guarantees, e.g. "does NOT change Simulation Preview scoring", and must be preserved verbatim, not summarized). Import `jsonFetch` and `operatorMutationHeaders` from `./core`. Import the `@/types/api` types this file's functions actually reference (`ListObservedFactsParams`, `ObservedFactListResponse`, `ObservedFactCreateRequest`, `ObservedFact`, `ObservedFactUpdateRequest`, `ObservedFactDeleteResponse`, `PredictionObservationCompareRequest`, `PredictionObservationCompareResponse`, `ValidationReviewRequest`, `ValidationReviewResponse`).

- [ ] **Step 5: Create `operator.ts`**

Move from `api.ts`, verbatim, the implementations of: `status`, `cacheStats`, `cacheClear`, `rebuildClusters`, `rebuildRatings`, `enrichmentStationStatus`, `enrichmentWarehouseStatus`, `adminDataStatus`, `adminCronStatus`, `adminRunOperation`, `adminOperationHistory`, `operatorSafetyGates`, `operatorSourceRuns`, `operatorSourceRunDetail`, `operatorSourceRunArtifacts`, `operatorSourceRunBridge`, `operatorSourceRunStagingImpact`, `operatorDiagnosticRows`. Import `jsonFetch` from `./core`. Import the `@/types/api` types this file's functions actually reference (`AppStatus`, `CacheStats`, `EnrichmentStationStatus`, `EnrichmentWarehouseStatus`, `AdminDataStatus`, `AdminCronStatus`, `AdminOperationRunResponse`, `AdminOperationHistoryResponse`, `OperatorSafetyGateSummary`, `OperatorSourceRunSummary`, `OperatorSourceRunDetail`, `OperatorArtifactSummary`, `OperatorBridgeSummary`, `OperatorStagingImpactSummary`, `OperatorDiagnosticRowSummary`).

- [ ] **Step 6: Create `map.ts`**

Move from `api.ts`, verbatim, the implementations of: `mapRegions`, `mapClusterHulls`, `mapHeatmap`, `mapTimeline`. Move these types verbatim: `MapRegion`, `MapRegionsResponse`, `MapClusterHull`, `MapClusterHullsResponse`, `MapHeatmapCell`, `MapHeatmapResponse`, `MapTimelinePoint`, `MapTimelineResponse` (lines 210-266 in the current file). Import `jsonFetch` from `./core`.

- [ ] **Step 7: Verify no method or type was missed**

Run: from the repo root, `git show HEAD:frontend/src/lib/api.ts | grep -oE "^\s{2}[a-zA-Z][a-zA-Z0-9]*\(" | sort -u` to list every method name in the original `api` object, then manually confirm each one now exists as an exported function in exactly one of the 5 new domain files.
Expected: every name from the original file's method list is accounted for exactly once across `search.ts`, `planner.ts`, `observations.ts`, `operator.ts`, `map.ts`.

---

### Task 2: Create the compatibility barrel and delete the old file

**Files:**
- Create: `frontend/src/lib/api/index.ts`
- Delete: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: every named export from `./core`, `./search`, `./planner`, `./observations`, `./operator`, `./map` (Task 1)
- Produces: `export const api = {...}` (same flat shape as today), every named wrapper function, `export { ApiError }`, `export type { LocalSearchBody, SystemResult }` — this is the complete public surface every other file in the frontend imports from `@/lib/api`

- [ ] **Step 1: Write `index.ts`**

```typescript
import * as search from './search';
import * as planner from './planner';
import * as observations from './observations';
import * as operator from './operator';
import * as map from './map';

export { ApiError } from './core';

export const api = {
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
};

// ── Compatibility named wrappers (unchanged public surface) ────────────
export function getSlotPredictions(id64: number) { return planner.slotPredictions(id64); }
export function getBuildability(id64: number, archetype?: string) { return planner.buildability(id64, archetype); }
export function getSystemArchetype(id64: number) { return planner.archetypeSystem(id64); }
export function getSimulationSummary(id64: number, archetype?: string) { return planner.simulationSummary(id64, archetype); }
export function getRecommendedBuilds(id64: number, archetype?: string) { return planner.recommendedBuilds(id64, archetype); }
export function getProvenanceCockpit(id64: number) { return planner.provenanceCockpit(id64); }
export function getWarehousePlannerEvidence(id64: number) { return planner.warehousePlannerEvidence(id64); }
export function getEvidenceSystemSummary(id64: number) { return planner.evidenceSystemSummary(id64); }
export function importJournal(request: Parameters<typeof planner.importJournal>[0]) { return planner.importJournal(request); }
export function getJournalImportReceipt(runKey: string) { return planner.journalImportReceipt(runKey); }
export function getJournalTelemetry(syncKey: string) { return planner.journalTelemetry(syncKey); }
export function fetchOptimiserCandidates(request: Parameters<typeof planner.optimiserCandidates>[0]) { return planner.optimiserCandidates(request); }
export function getRegionalAnalysis(id64: number) { return planner.regionalAnalysis(id64); }
export function getFacilityTemplates() { return planner.facilityTemplates(); }
export function simulateBuild(request: Parameters<typeof planner.simulateBuild>[0]) { return planner.simulateBuild(request); }
export function importSystemLayout(id64: number, request?: Parameters<typeof planner.importSystemLayout>[1]) { return planner.importSystemLayout(id64, request); }
export function listObservedFacts(params: Parameters<typeof observations.listObservedFacts>[0]) { return observations.listObservedFacts(params); }
export function createObservedFact(request: Parameters<typeof observations.createObservedFact>[0]) { return observations.createObservedFact(request); }
export function updateObservedFact(observationId: string, request: Parameters<typeof observations.updateObservedFact>[1]) { return observations.updateObservedFact(observationId, request); }
export function deleteObservedFact(observationId: string) { return observations.deleteObservedFact(observationId); }
export function comparePredictionToObservations(request: Parameters<typeof observations.comparePredictionToObservations>[0]) { return observations.comparePredictionToObservations(request); }
export function reviewPredictionValidation(request: Parameters<typeof observations.reviewPredictionValidation>[0]) { return observations.reviewPredictionValidation(request); }
export function getMapRegions() { return map.mapRegions(); }
export function getMapClusterHulls(opts?: Parameters<typeof map.mapClusterHulls>[0]) { return map.mapClusterHulls(opts); }
export function getMapHeatmap(opts?: Parameters<typeof map.mapHeatmap>[0]) { return map.mapHeatmap(opts); }
export function getMapTimeline(opts?: Parameters<typeof map.mapTimeline>[0]) { return map.mapTimeline(opts); }

export type { LocalSearchBody, SystemResult } from '@/types/api';
export type { ClusterSearchRequestBody, ClusterSearchApiResponse, WatchlistEntry } from './search';
```

Note: the exact parameter types above use `Parameters<typeof ...>` to avoid re-declaring every request type in this file — adjust only if this causes a real type error `yarn typecheck` reports; the goal is identical runtime behavior and identical exported signatures, not identical syntax to this sketch. `LocalSearchBody` currently comes from `@/types/api` re-exported by the original file — verify in Task 1 Step 7 which module actually defines it and import accordingly; if it's actually defined locally in the original `api.ts` (not `@/types/api`), it now lives in `search.ts` per Task 1 Step 2 and this import line must say `from './search'` instead.

- [ ] **Step 2: Delete the old flat file**

Run: `git rm frontend/src/lib/api.ts`

- [ ] **Step 3: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors. This is the primary safety net for this task — a missed export, wrong import path, or type mismatch surfaces here.

- [ ] **Step 4: Lint**

Run: `cd frontend && yarn lint`
Expected: passes (0 errors; pre-existing unrelated warnings are fine).

- [ ] **Step 5: Knip unused-file/export check**

Run: `cd frontend && yarn knip --files`
Expected: passes — no new unused-export warnings (would indicate something got moved but never wired into `index.ts`).

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && yarn test`
Expected: passes in full — this file is imported broadly, so this is the real functional safety net.

- [ ] **Step 7: Production build**

Run: `cd frontend && yarn build`
Expected: succeeds with no errors.

- [ ] **Step 8: Manual smoke check**

Start the dev server (`yarn dev`) and in a browser: run a search (search.ts), open a system detail page (planner.ts), open the map (map.ts), add/remove a watchlist entry (search.ts). Confirm no console errors and each returns real data. This catches a runtime wiring mistake in the `index.ts` barrel that `typecheck` cannot — TypeScript can confirm shapes match but not that a barrel re-export points at the correct underlying function.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Split api.ts into domain modules behind a compatibility barrel

frontend/src/lib/api.ts (828 lines) becomes frontend/src/lib/api/ -
core.ts (shared request plumbing) plus search.ts, planner.ts,
observations.ts, operator.ts, map.ts (one domain each), reassembled
by index.ts into the exact same api object shape and the same ~20
named wrapper exports. Every existing call site in the frontend keeps
working unchanged - @/lib/api resolves to @/lib/api/index.ts
automatically. See docs/superpowers/specs/2026-08-06-split-api-ts-into-domain-modules-design.md."
```

---

## Self-Review

**Spec coverage:** All 57 methods and all ~20 wrapper functions from the design spec's enumeration are named explicitly in Task 1 and Task 2. `WatchlistEntry`'s relocation (from stranded-at-the-bottom to living in `search.ts`) is called out explicitly in Task 1 Step 2.

**Placeholder scan:** No TBD/TODO. Task 2 Step 1's `index.ts` sketch has one explicit caveat (the `LocalSearchBody` source-module uncertainty) rather than a silent gap — flagged so whoever executes this resolves it against the real file rather than guessing.

**Type consistency:** Function names in Task 2's `index.ts` sketch match the names Task 1 specifies for each domain file exactly (e.g. `planner.slotPredictions`, not `planner.getSlotPredictions`).
