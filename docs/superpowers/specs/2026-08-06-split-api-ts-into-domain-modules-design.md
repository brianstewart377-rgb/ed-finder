# Split frontend/src/lib/api.ts into domain modules — Design

**Goal:** Break up the 828-line `api.ts` (one large `api` object covering ~50 endpoints across every feature area, plus ~20 duplicate named wrapper functions) into domain-scoped files behind a compatibility barrel, with zero call-site changes anywhere else in the frontend.

**Context:** Second sub-project from the 2026-08-05 Codex code-splitting review. First was `PlannerCanvasPreview` removal (`docs/superpowers/specs/2026-08-06-remove-unused-planner-canvas-preview-design.md`). The review suggested a shared request core plus domain clients (`searchApi`, `plannerApi`, `operatorApi`, `observationsApi`, `mapApi`), retaining compatibility re-exports during migration — this design follows that suggestion directly rather than inventing a different taxonomy, since the user asked for whatever's easiest to implement correctly rather than a novel design.

## Current structure (verified 2026-08-06)

- Lines 13-65: type imports from `@/types/api`
- Lines 106-170: request core — `API_BASE`, `resolveApiUrl()`, `ADMIN_TOKEN_SESSION_KEY`, `readSessionAdminToken()`, `operatorMutationHeaders()`, `ApiError`, `jsonFetch()`
- Lines 268-652: the `api` object, ~50 methods, already loosely grouped by comment headers (core search, watchlist, system/simulation, journal, misc, admin/ops, observed facts, comparison, validation, map layers)
- Lines 654-803: ~20 standalone named wrapper functions (`getSlotPredictions`, `getBuildability`, `importJournal`, etc.) that each just call the corresponding `api.xxx()` method — the report's flagged duplication
- Lines 805-826: `WatchlistEntry` interface, stranded at the end of the file, disconnected from the watchlist methods it describes

CLAUDE.md: "All API calls go through `src/lib/api.ts` — don't scatter raw `fetch()` calls for endpoints that already have a helper." This file is imported broadly across the frontend, both via `api.xxx()` and via the named wrappers directly.

## Design

Convert `frontend/src/lib/api.ts` into a directory `frontend/src/lib/api/`. TypeScript resolves `@/lib/api` to `@/lib/api/index.ts` automatically once the flat file is gone, so this is transparent to every existing import site.

**Files:**
- `core.ts` — `jsonFetch`, `resolveApiUrl`, `ApiError`, `readSessionAdminToken`, `operatorMutationHeaders`, `API_BASE`, `ADMIN_TOKEN_SESSION_KEY`
- `search.ts` — `health`, `autocomplete`, `localSearch`, `clusterSearch`, `watchlist`, `watchAdd`, `watchRemove`, `recentEvents`, `eliteNewsLatest`, plus `LocalSearchBody`, `ClusterSearchRequestBody`, `ClusterSearchApiResponse`, `EddnEvent`, `RecentEventsResponse`, `EliteNewsItem`, `EliteNewsResponse`, `WatchlistEntry` (moved here from its stranded location at the bottom of the original file, next to the methods that actually use it)
- `planner.ts` — `system`, `archetypeSystem`, `simulationSummary`, `slotPredictions`, `buildability`, `recommendedBuilds`, `provenanceCockpit`, `warehousePlannerEvidence`, `evidenceSystemSummary`, `regionalAnalysis`, `facilityTemplates`, `simulateBuild`, `importSystemLayout`, `optimiserCandidates`, `archetypeRerank`, `importJournal`, `journalImportReceipt`, `journalTelemetry`, `profileSyncPull`, `profileSyncPush`, plus `ProfileSyncPull`/`ProfileSyncPush` types
- `observations.ts` — `listObservedFacts`, `createObservedFact`, `updateObservedFact`, `deleteObservedFact`, `comparePredictionToObservations`, `reviewPredictionValidation`
- `operator.ts` — `status`, `cacheStats`, `cacheClear`, `rebuildClusters`, `rebuildRatings`, `enrichmentStationStatus`, `enrichmentWarehouseStatus`, `adminDataStatus`, `adminCronStatus`, `adminRunOperation`, `adminOperationHistory`, `operatorSafetyGates`, `operatorSourceRuns`, `operatorSourceRunDetail`, `operatorSourceRunArtifacts`, `operatorSourceRunBridge`, `operatorSourceRunStagingImpact`, `operatorDiagnosticRows`
- `map.ts` — `mapRegions`, `mapClusterHulls`, `mapHeatmap`, `mapTimeline`, plus `MapRegion`, `MapRegionsResponse`, `MapClusterHull`, `MapClusterHullsResponse`, `MapHeatmapCell`, `MapHeatmapResponse`, `MapTimelinePoint`, `MapTimelineResponse`
- `index.ts` — imports each domain's method-group and type re-exports, reassembles the exact same `api` object shape (`{ ...searchMethods, ...plannerMethods, ...observationsMethods, ...operatorMethods, ...mapMethods }`), and re-exports every one of the ~20 named wrapper functions unchanged

Each domain file imports only the `@/types/api` types it actually uses, plus `jsonFetch`/`resolveApiUrl`/`ApiError`/`operatorMutationHeaders` from `./core` as needed. No method's implementation changes — this is pure code movement, not a rewrite.

## Verification

- `yarn typecheck`, `yarn lint`, `yarn knip --files`, `yarn test` (full suite — this file is imported broadly, so the existing tests are the real safety net), `yarn build`
- Manual smoke check in the dev server: one call from each domain (a search, a system detail page load, the map, watchlist) — typecheck can't catch a runtime wiring mistake in the barrel reassembly

## Out of scope

- No call sites elsewhere in the frontend are touched — `api.xxx()` and every named wrapper (`getSlotPredictions`, `importJournal`, etc.) keep working exactly as today.
- No decision is made about which surface (the `api` object vs. named exports) is "the" long-term public interface going forward — both remain available, same as today.
- `frontend/src/types/api.gen.ts` is untouched (generated, never hand-edited per CLAUDE.md).
