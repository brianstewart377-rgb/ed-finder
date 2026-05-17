# Stage 4F: Simulation Preview UI Architecture

Stage 4F decomposes the frontend Simulation Preview area so it remains maintainable before Stage 5 optimiser UI work begins. This is a **UI organisation refactor only**. It does not change simulation mechanics, backend API calls, request or response types, scoring, CP logic, economy logic, service logic, observation comparison, or the visual design language.

> Future optimiser UI should not be added back into a monolithic Simulation Preview file. Candidate generation, candidate comparison, and candidate explanation should live in optimiser-specific components or a sibling feature folder that can reuse the existing preview panels and shared atoms.

## Folder Structure

The Simulation Preview UI now lives under `frontend-v2/src/features/system-detail/simulation-preview/`. The old public entry file at `frontend-v2/src/features/system-detail/SimulationPreview.tsx` remains as a thin compatibility wrapper so existing imports continue to work.

| Path | Responsibility |
|---|---|
| `SimulationPreview.tsx` | Smaller composition component that owns the React Query fetches, derives recommended placements, wires hooks to presentational sections, and preserves the public entry point. Stage 5.9D moved plan state and preview-run state into hooks. |
| `SimulationResult.tsx` | Result layout and panel ordering for an already-returned `SimulateBuildResponse`. |
| `BuildPlanEditor.tsx` | Placement editor for facility template, body, primary-port flag, sequence movement, and removal controls. |
| `StartModes.tsx` | Start-mode cards, mode intro copy, and current plan badge. |
| `ColonyPlannerHeader.tsx` | Colony Planner heading, explanatory copy, current plan badge, and explicit Run Preview button. |
| `ColonyPlannerSectionNav.tsx` | Lightweight visible labels for Build Plan, Suggested Builds, Preview Result, Observed Evidence, and Validation. Backend/internal optimiser names remain unchanged. |
| `BuildPlanSection.tsx` | Presentational Build Plan section for start modes, optimiser-origin messaging, assumptions, target archetype selector, add button, catalogue status, empty state, and `BuildPlanEditor`. |
| `PreviewResultSection.tsx` | Presentational Preview Result section for regional context, preview errors, `SimulationResult`, and awaiting-preview ghost state. |
| `hooks/useSimulationPreviewPlan.ts` | Public plan-orchestration hook for target archetype, start mode, auto-load state, plan replacement version, initial/recommended/blank plan loading, and optimiser-candidate loading. It delegates placement editing and optimiser-origin state to focused hooks. |
| `hooks/usePlacementEditor.ts` | Focused placement editor hook for placement state, replacement/clearing, add/update/remove/move behaviour, resequencing, primary-port exclusivity, and manual-edit signalling. |
| `hooks/useOptimiserCandidateOrigin.ts` | Focused optimiser-origin hook for loaded candidate label, edited flag, clearing origin state, and marking optimiser-origin plans edited only when an origin exists. |
| `hooks/useSimulationPreviewRun.ts` | Focused preview-run hook for result, running, error, `canRun`, clearing stale preview state, and explicit `simulateBuild` execution. |
| `types.ts` | Preview-local constants and types such as archetype options and `StartMode`. |
| `components/` | One file per shared UI atom, re-exported by `components/index.ts`. |
| `panels/` | One file per major Simulation Preview result panel, re-exported by `panels/index.ts`. |
| `utils/` | Formatting, tone, and placement helper functions shared by preview components. |
| `optimiser/` | Stage 5 optimiser candidate UI, including candidate cards, details, ranking breakdown, placement list, generated-parameter stamps, stale-control warnings, and comparison utilities. |

Stage 10B adds `BuildPlanBodyView.tsx` as a focused presentational readout for the current Build Plan grouped by body. Stage 10C evolves that readout into **Layout view**, a graphical planning foundation with a compact plan summary, body-level layout cards, CP generated/needed totals, primary-port status, Preview status, and conservative warning chips for missing templates, unassigned/unknown bodies, estimated data, sparse body metadata, surface placement risks, stale Preview, and visible CP pressure. Stage 10D adds local selected-body / selected-placement state and `BuildPlanLayoutDetailPanel.tsx`, a read-only detail panel that explains the current summary, selected body, or selected placement and gives conservative next-action guidance. Stage 10E.1 adds a manual `Import / refresh system layout` control in `BuildPlanSection.tsx` that calls the new backend layout-import contract and shows local read-only status metadata, warnings, and errors. The import control is manual only: it does not auto-import on page load, does not poll, does not mutate Build Plan placements, and only warns when current body data does not match assigned placement body IDs. Stage 11A begins the visual redesign foundation pass by strengthening workflow hierarchy, workspace/header planning identity, and later-step framing for Observed Evidence and Validation while preserving existing behaviour boundaries. `BuildPlanSection.tsx` owns the local List/Layout toggle; List view remains the default and continues to render `BuildPlanEditor`. `buildPlanLayoutUtils.ts` owns pure grouping, summary, status, and warning helpers so the React component stays focused on rendering. Layout view uses only existing placements, facility templates, system body data, and existing preview state. It does not fetch, run Preview, generate Suggested Builds, copy/load builds, mutate observations, call validation/review endpoints, persist view state, implement structure picking, or implement hauling/material logistics. Layout view is a readout; destructive move/remove/edit actions remain in List view.

Stage 11B continues this sequence with card-level and nav-level visual polish while preserving the same safety boundaries:

- `BuildPlanBodyView.tsx` gets layout-card clarity refinements (readable headers, selected states, warning/metadata grouping, and quieter unassigned treatment).
- `BuildPlanLayoutDetailPanel.tsx` receives compact grouped sections (summary/body/placement) and stronger read-only guidance.
- `ColonyPlannerSectionNav.tsx` improves Planner workflow emphasis and separates primary planning steps from later steps.
- List view remains the canonical editing surface.
- All edits remain in `BuildPlanEditor` and existing hooks; no simulator/optimiser/validation side effects are introduced.

## Shared UI Atoms

Shared visual atoms are intentionally small and boring. Each atom lives in its own file so future optimiser components can reuse them without importing an unrelated grouped implementation file.

| Component File | Export |
|---|---|
| `components/Metric.tsx` | `Metric` |
| `components/GhostMetric.tsx` | `GhostMetric` |
| `components/Message.tsx` | `Message` |
| `components/Chip.tsx` | `Chip` |
| `components/IconButton.tsx` | `IconButton` |
| `components/index.ts` | Barrel exports for the shared atoms. |

## Result Panels

Each major result panel now has a dedicated file. This makes the existing preview sections easy to find, modify, and test without having to navigate a broad grouped file.

| Panel File | Export |
|---|---|
| `panels/DataConfidencePanel.tsx` | `DataConfidencePanel` |
| `panels/ObservedVsPredictedPanel.tsx` | `ObservedVsPredictedPanel` |
| `panels/MechanicsTracePanel.tsx` | `MechanicsTracePanel` |
| `panels/EconomyBars.tsx` | `EconomyBars` |
| `panels/EconomyStackPanel.tsx` | `EconomyStackPanel` |
| `panels/PortEconomyPanel.tsx` | `PortEconomyPanel` |
| `panels/InheritedEconomyPanel.tsx` | `InheritedEconomyPanel` |
| `panels/TopologyPanel.tsx` | `TopologyPanel` |
| `panels/CpSummary.tsx` | `CpSummary` |
| `panels/CpRepairPanel.tsx` | `CpRepairPanel` |
| `panels/CpTimelinePanel.tsx` | `CpTimelinePanel` |
| `panels/ServicesPanel.tsx` | `ServicesPanel` |
| `panels/PortServicePanel.tsx` | `PortServicePanel` |
| `panels/LinkSummary.tsx` | `LinkSummary` |
| `panels/RegionalContextMini.tsx` | `RegionalContextMini` |
| `panels/index.ts` | Barrel exports for result panels. |

Tiny private helpers that are only useful to one panel stay in that panel file. For example, the CP cell rendering helper is private to `CpSummary.tsx`, and the service entry group is private to `PortServicePanel.tsx`. Shared formatting and tone helpers remain in `utils/`.

## Compatibility Boundary

The legacy wrapper `frontend-v2/src/features/system-detail/SimulationPreview.tsx` continues to export the public preview component and panel exports used by existing tests and callers. `RecommendedBuildPlan` is consistently exported from `@/types/api` through both the legacy wrapper and the new `simulation-preview/index.ts` barrel.

| Public Export | Source |
|---|---|
| `SimulationPreview` | `./simulation-preview/SimulationPreview` |
| `RecommendedBuildPlan` | `@/types/api` |
| `ObservedVsPredictedPanel` | `./simulation-preview/panels/ObservedVsPredictedPanel` |
| `DataConfidencePanel` | `./simulation-preview/panels/DataConfidencePanel` |
| `MechanicsTracePanel` | `./simulation-preview/panels/MechanicsTracePanel` |
| `CpRepairPanel` | `./simulation-preview/panels/CpRepairPanel` |

## Stage 5 Guidance

Stage 5 optimiser UI should treat this structure as the boundary for existing Simulation Preview behaviour. Stage 5.9C reframes the product surface as **Colony Planner** while keeping the implementation under `simulation-preview/` to avoid churn. Stage 5.9D then extracts preview execution ownership into `hooks/useSimulationPreviewRun.ts` and Colony Planner layout into focused presentational sections. The focused 5.9D cleanup keeps `hooks/useSimulationPreviewPlan.ts` as the public plan orchestrator while splitting internal ownership into `hooks/usePlacementEditor.ts` and `hooks/useOptimiserCandidateOrigin.ts`. Candidate lists, candidate comparison, optimiser warnings, generated-parameter stamps, stale-control warnings, and candidate explanation should remain optimiser-specific components rather than being folded into `SimulationResult.tsx`.

Stage 5C uses `simulation-preview/optimiser/` for candidate comparison. Stage 5D keeps the optimiser components grouped there and adds an opt-in load callback from `SimulationPreview.tsx`. Candidate details can show `Load into preview` only when that callback is present; otherwise the panel remains honestly read-only. Non-empty preview plans require confirmation before replacement, and loading copies placements into the existing editor without saving, committing in-game, or auto-running preview. The preview tracks optimiser-candidate origin and marks that origin as edited once the user manually changes placements.

Stage 5E adds the comparison engine under `simulation-preview/optimiser/comparison/`. It intentionally exports serialisable types, source helpers, deterministic comparison logic, and pure formatter helpers without rendering the full comparison UI. Stage 5F consumes this engine in a focused show/hide comparison panel within optimiser candidate details. Stage 5.9C positions that panel inside the Colony Planner → Optimiser Candidates section and adds generated-request visibility so users can tell when target archetype, max candidate count, or estimated-data controls have changed since generation. Stage 5.9D keeps those UX behaviours intact while moving state and layout ownership out of the main composition file. Stage 5.9E hardens the workflow by keeping generated candidates visible when controls become stale, adding generated/current value detail, warning near stale candidate load/comparison controls, and requiring explicit older-candidate confirmation before stale candidates can be loaded. It also marks an existing Preview Result stale when the exact preview fingerprint changes after an explicit run; that fingerprint includes system ID, target archetype, and resequenced placements. The comparison panel remains advisory and read-only; it does not run preview, mutate placements, save builds, or replace the Stage 5D load confirmation flow. Candidate-vs-candidate comparison remains engine-supported, with selector UI deferred to avoid clutter. Stage 6 observed-vs-predicted validation remains deferred until this workflow safety is stable.

## Stage 6A Observed Facts Boundary

Stage 6A adds only a backend observed facts foundation. The `observed_facts` table and `/api/observations/facts` CRUD API store manually supplied or test-fixture evidence about services, economies, facilities, CP values, build outcomes, and prediction matches or mismatches. This backend evidence shelf is deliberately separate from the Colony Planner UI and from Simulation Preview scoring.

Stage 6A is a **passive evidence shelf**: observations are recorded separately from predictions and do not feed back into optimiser ranking, candidate generation, Simulation Preview scoring, CP / economy / service / buildability mechanics, or any existing simulation response field. A static safety test asserts the optimiser, simulation, mechanics, and their routers never import the observation store.

The Stage 6A public API accepts only `manual` and `test_fixture` observation sources; `imported` and `inferred` are reserved enum values for later ingestion/comparison stages and are rejected by Stage 6A validation. The list endpoint's `summary` field describes the full filtered result set (matching `total`), not just the paginated page. `subject_id` may be null for system/build-level notes. Legacy Stage 4D columns on `observed_facts` (`area`, `source_type`, `observed_value`, `facility_id`, `body_id`) remain populated alongside the new Stage 6A columns until a later normalisation migration removes them.

Stage 6A does **not** add frontend observation entry, automatic validation inside Simulation Preview, EDMC or journal ingestion, saved builds, account persistence, crowdsourcing, auto-learning, or mechanics mutation. Stage 6B can add manual observation entry UI, and Stage 6C can add predicted-vs-observed comparison on top of the stored facts.

## Stage 6B Manual Observed Evidence UI

Stage 6B adds a focused **Observed Evidence** panel inside Colony Planner. The panel lives under `frontend-v2/src/features/system-detail/simulation-preview/observations/` and is rendered by `SimulationPreview.tsx` after `PreviewResultSection`. `ColonyPlannerSectionNav.tsx` adds a neutral fourth section label so users can see Observed Evidence alongside Build Plan, Suggested Builds, and Preview Result without implying it feeds the predicted scoring chain.

| Path | Responsibility |
|---|---|
| `observations/ObservedEvidencePanel.tsx` | Top-level panel: lists observed facts for the current `system_id64`, renders the create form, surfaces the backend summary, applies fact-type/status/confidence filters, and exposes loading/error/empty states with a retry control. |
| `observations/ObservedEvidenceForm.tsx` | Manual create form with required Evidence type, Status, Confidence, and Notes inputs, conditional structured fields per fact type (`service_id`, `economy`, `facility_template_id`, observed value), and a collapsible advanced section for local body, target archetype, expected value, and tags. The form always sends `source: 'manual'`. |
| `observations/ObservedEvidenceList.tsx` | Renders the list of cards or the Stage 6B empty-state copy when the backend returns no facts. |
| `observations/ObservedEvidenceCard.tsx` | One evidence row with view, inline edit, and confirm-delete modes. Editable fields are status, confidence, notes, tags, and observed/expected values. |
| `observations/observationLabels.ts` | User-facing labels, passive-evidence copy, empty-state copy, delete-confirm copy, and the curated `CREATABLE_FACT_TYPES` list. `prediction_match` and `prediction_mismatch` remain in the wire vocabulary but are not offered as create options. |
| `observations/observationUtils.ts` | Pure helpers for tags parsing/formatting, observed-value JSON parsing, default form state, client-side validation, request building, and FastAPI Problem-Details error description. |
| `observations/index.ts` | Barrel exports for the panel and its supporting helpers. |

The Stage 6B panel is intentionally **passive**. It calls only the Stage 6A `/api/observations/facts` endpoints and never invokes `simulateBuild`, `fetchOptimiserCandidates`, or any prediction mechanics. Observed evidence created, edited, or deleted through the panel does not change `useSimulationPreviewRun`, `useSimulationPreviewPlan`, `OptimiserCandidatePanel`, optimiser ranking, candidate generation, or Preview Result scoring. The panel renders the visible safety copy *"Observed Evidence is passive. It does not change Simulation Preview scoring, optimiser ranking, or generated candidates."* near the top so users see the boundary without reading the docs.

The create form intentionally never exposes `imported` or `inferred` as source options; both remain reserved enum values for later ingestion/comparison stages, and the Stage 6A request validation already rejects them server-side. Tests assert that no option element with those values exists in the form.

Stage 6C will introduce the predicted-vs-observed comparison engine. Stage 6D will render validation/comparison results in the simulation surface. Stage 6B records evidence only; it does not decide what the evidence means.

## Stage 6C Predicted-vs-Observed Comparison Engine

Stage 6C adds a backend-only deterministic comparison engine plus a single new endpoint `POST /api/observations/compare`. The engine takes a Simulation Preview prediction (or any prediction-shaped object) and a list of Stage 6A persisted observed facts, and emits a structured `PredictionObservationCompareResponse` containing a per-row comparison list and a top-level summary. Stage 6C is comparison-only: it does not change predictions, optimiser ranking, candidate generation, Simulation Preview scoring, CP / economy / service / buildability mechanics, or any existing simulation response field.

Per-row `status` is one of `confirmed`, `contradicted`, `predicted_only`, `observed_only`, `unknown`, or `unverified`; `severity` is `info` / `low` / `medium` / `high` and is clamped by observation confidence so low-confidence observations cannot produce high-severity contradictions. Summary `status` is one of `no_observations`, `confirmed`, `mixed`, `needs_review`, or `insufficient_evidence`, and `confidence_impact` (`none` / `strengthened` / `weakened` / `mixed` / `insufficient_evidence`) is a UI hint only. See `docs/api-contracts.md` for the full Stage 6C request/response shape and `docs/colonisation-redesign/engine-roadmap.md` for the engine, models, matching, status, and summary rules.

Stage 6C does **not** touch the frontend. The Stage 6B Observed Evidence panel, `SimulationPreview.tsx`, `useSimulationPreviewRun`, `useSimulationPreviewPlan`, `OptimiserCandidatePanel`, `ColonyPlannerSectionNav.tsx`, and every Preview Result rendering component remain unchanged. Stage 6D adds the frontend validation UI that calls `POST /api/observations/compare` from inside Simulation Preview and renders the comparison summary, per-row statuses, severities, evidence shelf, and recommended actions returned by the Stage 6C engine.

## Stage 6D Validation Display in Colony Planner

Stage 6D adds an **in-page Validation section** inside Colony Planner that renders the Stage 6C `/api/observations/compare` response. The section lives directly under `frontend-v2/src/features/system-detail/simulation-preview/validation/` and is rendered by `SimulationPreview.tsx` **after** `ObservedEvidencePanel`. `ColonyPlannerSectionNav.tsx` adds a fifth chip ("Validation") so users can see the section alongside Build Plan, Suggested Builds, Preview Result, and Observed Evidence. There is no popout, no modal, and no new top-level app tab - the placement decision is deliberate so validation reads as part of the Colony Planner flow rather than a separate experience. A future expansion may move large comparison sets into a drawer/popout while keeping the in-page placement as the default.

| Stage 6D module | Responsibility |
|---|---|
| `validation/ValidationPanel.tsx` | Top-level panel. Owns the compare query, no-preview/loading/error/stale states, and the manual **Refresh validation** button. Receives `systemId64`, `targetArchetype`, `previewResult` (current Simulation Preview result), and `isPreviewResultStale`. |
| `validation/ValidationSummary.tsx` | Renders overall status (`no_observations`/`confirmed`/`mixed`/`needs_review`/`insufficient_evidence`), confidence impact (`none`/`strengthened`/`weakened`/`mixed`/`insufficient_evidence`), per-bucket counts, and the backend `summary` text using conservative labels. |
| `validation/ValidationComparisonList.tsx` | Renders the comparison rows with a status filter; surfaces empty-state and filter-empty-state copy. |
| `validation/ValidationComparisonCard.tsx` | Renders a single comparison row including evidence details (`observation_id`, `fact_type`, `status`, `confidence`, `observed_value`, `expected_value`, `notes`). Contradicted rows are labelled **Needs review**; `predicted_only`/`observed_only` rows use neutral wording. |
| `validation/validationLabels.ts` | Centralised user-facing copy and label maps. Enforces conservative wording: "Needs review", "Predicted only" / "Observed only" instead of correctness claims, top-of-panel advisory banner. |
| `validation/validationUtils.ts` | Pure helpers: stable preview-result fingerprint for the compare query key, value formatter, status filter. |

The Stage 6D panel is intentionally **passive**. It calls only `comparePredictionToObservations(...)` against `POST /api/observations/compare` in Mode A (no `observed_facts` in the request, so the backend serves authoritative persisted evidence). It never calls `simulateBuild`, never calls `fetchOptimiserCandidates`, never mutates persisted observations, never feeds confidence impact into Simulation Preview scoring or optimiser ranking, and never auto-runs Simulation Preview. The query key includes `systemId64`, `targetArchetype`, and a stable preview-result fingerprint so a new preview run triggers a fresh comparison while an unchanged preview reuses the cached compare response. When `runState.isResultStale` is true, the panel renders a stale warning; the user re-runs Preview themselves. The Observed Evidence panel invalidates `observation-compare` queries on create/update/delete so newly recorded evidence is reflected on the next refresh without changing the build plan or scoring.

Stage 6E will introduce the confidence/mechanics review loop on top of this display; Stage 6D itself is a display layer only. Tests under `validation/ValidationPanel.test.tsx` and the updated `SimulationPreview.optimiser.test.tsx` cover advisory copy, no-preview empty state, compare API call shape, summary rendering, per-status labels, evidence detail rendering, status filtering, loading state, error/retry, stale warning, refresh, in-page ordering after Observed Evidence, and passivity (no `simulateBuild`, no `fetchOptimiserCandidates`, no observation mutations during rendering).

## Stage 8A/8B/8C Colony Planner UX Hardening

Stage 8A reframed the embedded Simulation Preview surface as the user-facing **Colony Planner** path:

- System detail exposes an `Open Colony Planner` CTA near the top of the modal.
- Finder result cards and Advanced Search Tuning can open system detail focused on Colony Planner.
- The generated-plan panel is labelled **Suggested Builds** in user-facing UI while backend/API/type names keep optimiser/candidate vocabulary.
- The first-run `Show Suggested Builds` card focuses the Suggested Builds panel; users still explicitly click `Generate Suggested Builds`.
- Build Plan status shows placement count, Preview not-run/stale/running/current-match state, and next-step copy.
- Preview Result starts with cautious verdict guidance before detailed mechanics panels.
- Observed Evidence and Validation remain later-step panels after planning and in-game checking.

Stage 8B hardens that path for real use. Focus-highlight timers are cleaned up on repeated clicks and unmount. Result-card action tests cover propagation and double-call risks. Suggested Builds focus tests cover the no-auto-generation boundary. Preview guidance uses estimate/comparison wording and avoids optimality or truth claims.

Stage 8C is the final forensic pass over the guided workflow. It keeps the older Recommended Builds bridge aligned with Colony Planner terminology, keeps blank/manual planning framed as an editable Build Plan path, and preserves the rule that Evaluate/Open/Show actions focus or navigate only. Suggested Builds generation, Build Plan copying, and Preview execution remain explicit user actions. This remains frontend UX/test/docs work only; no scoring, generation, ranking, validation, or backend mechanics changed.

## Stage 9C Dedicated Colony Planner Workspace

Stage 9C adds a dedicated Colony Planner workspace route while keeping the existing planner implementation reusable:

- `#colony-planner/system/{id64}` renders `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`.
- The route parser keeps `plannerSystemId` separate from System Detail modal `selectedSystemId`.
- `ColonyPlannerWorkspace` uses `useSystemDetail(id64)` for data loading and renders `SimulationPreviewPanel` in the loaded state.
- Finder and Advanced Search Tuning `Evaluate in Colony Planner` actions navigate to the workspace.
- Details/Open system detail actions continue to open `SystemDetailModal`.
- The System Detail top CTA opens the workspace when the app provides `onOpenColonyPlanner`; without that prop it still falls back to the Stage 8 embedded focus/highlight behaviour.
- The embedded planner remains inside System Detail for compatibility.

The workspace wrapper owns no Simulation Preview mechanics. It does not call `simulateBuild`, does not call `fetchOptimiserCandidates`, does not copy or load Suggested Builds, and does not change scoring, generation, ranking, Observed Evidence, or Validation behaviour. It provides only no-system/loading/error/loaded shell states, compact system context, Back to Finder, and Open full system detail actions around the existing planner panel.

Stage 9D adds final route/workspace passivity hardening around this boundary. Workspace load may fetch system detail, facility templates, simulation summary, and observed-evidence list data through existing passive planner queries. It still does not run Preview, generate Suggested Builds, copy/load builds, mutate evidence, or call validation compare/review before the user runs Preview.

## Stage 6E Validation Review Guidance

Stage 6E extends the Validation section with a structured advisory layer from `POST /api/observations/review`. The panel still starts from a user-run Simulation Preview result; it does not run preview itself, generate optimiser candidates, mutate the build plan, create/update/delete observations, or change mechanics.

The review endpoint first produces the Stage 6C comparison result, then derives conservative review guidance: service contradictions may point to service unlock assumptions, economy contradictions may point to economy inheritance/composition, CP contradictions may point to CP source/final calculation, facility observed-only evidence points to validation coverage, and low-confidence contradictions remain monitor-level evidence-quality guidance. Missing evidence is insufficient evidence, not a prediction failure.

`ValidationPanel` now issues two read-only queries keyed by system, target archetype, and preview fingerprint:

- `observation-compare` for Stage 6C comparison rows.
- `observation-review` for Stage 6E review summary/signals.

The review block renders after the Stage 6C summary and before comparison rows. It shows overall review status, evidence strength, highest severity, primary areas, summary text, and signals. User-facing copy says: "Review guidance is advisory", "This does not change mechanics or scoring", and "Use this to decide what to investigate next." If review guidance fails to load, comparison rows remain visible.

Observed evidence create/update/delete invalidates both compare and review query namespaces. Low-confidence evidence cannot trigger high-priority review, and contradicted rows remain framed as needs-review leads rather than final mechanics verdicts. Stage 6F will harden the Stage 6 workflow; EDMC/journal ingestion is still not implemented.
