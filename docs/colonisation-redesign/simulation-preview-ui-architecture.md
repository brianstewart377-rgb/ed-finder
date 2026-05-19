# Stage 4F: Simulation Preview UI Architecture

Stage 4F decomposes the frontend Simulation Preview area so it remains maintainable before Stage 5 optimiser UI work begins. This is a **UI organisation refactor only**. It does not change simulation mechanics, backend API calls, request or response types, scoring, CP logic, economy logic, service logic, observation comparison, or the visual design language.

> Future optimiser UI should not be added back into a monolithic Simulation Preview file. Candidate generation, candidate comparison, and candidate explanation should live in optimiser-specific components or a sibling feature folder that can reuse the existing preview panels and shared atoms.

## Folder Structure

The Simulation Preview UI now lives under `frontend-v2/src/features/system-detail/simulation-preview/`. The old public entry file at `frontend-v2/src/features/system-detail/SimulationPreview.tsx` remains as a thin compatibility wrapper so existing imports continue to work.

| Path | Responsibility |
|---|---|
| `SimulationPreview.tsx` | Smaller composition component that owns the React Query fetches, derives recommended placements, wires hooks to presentational sections, and preserves the public entry point. Stage 5.9D moved plan state and preview-run state into hooks. |
| `WorkspaceModeTabs.tsx` | Stage 16C local mode tabs for Build Plan, Suggested Builds, Preview, Evidence, and Validation. Switching modes is UI-only and does not run preview/generation/validation. |
| `BuildPlanWorkspaceView.tsx` | Stage 16C Build Plan mode wrapper with topology-aware planning focus copy around the existing editable Build Plan. |
| `SuggestedBuildsWorkspaceView.tsx` | Stage 16C Suggested Builds mode wrapper around `OptimiserCandidatePanel`, preserving explicit generation and deliberate load/review behaviour. |
| `PreviewWorkspaceView.tsx` | Stage 16C Preview mode wrapper around `PreviewResultSection`, with explicit Run Preview control and current/stale/not-run state. |
| `EvidenceWorkspaceView.tsx` | Stage 16C Evidence mode wrapper around `ObservedEvidencePanel`; evidence remains manual/passive. |
| `ValidationWorkspaceView.tsx` | Stage 16C Validation mode wrapper around `ValidationPanel`; validation remains explicit and preview-result dependent. |
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

Stage 11C is the final pre-Stage-12 polish pass for visual readability and interaction confidence across the dedicated workspace:

- Keep `BuildPlanSection` list/layout behavior unchanged (`List view` remains default and explicit, `Layout view` remains readout-only), while tightening copy and spacing for low-noise clarity.
- Make Planner workflow hierarchy in `ColonyPlannerSectionNav` consistently easy to scan (`Suggested Builds → Build Plan → Preview Result`) with subdued later steps for Observed Evidence and Validation.
- Preserve and test keyboard-visible selected-state behaviour in `BuildPlanBodyView` and `BuildPlanLayoutDetailPanel`.
- Make accessibility refinements where practical (focus-visible support for summary reset and clearer detail layout for selected states).
- Make sure layout polish changes do not introduce `simulateBuild`, optimiser-load, or validation compare side effects.

Stage 11D is a reviewer-driven visual hierarchy refinement pass:

- Keep `ColonyPlannerSectionNav` path and spacing readable so `Suggested Builds`, `Build Plan`, and `Preview Result` remain clear primary steps and `Observed Evidence` / `Validation` remain later steps.
- Keep `BuildPlanLayoutDetailPanel` and `BuildPlanBodyView` selection mechanics unchanged (`List view` remains editing, `Layout view` remains read-only).
- Preserve separate interactive targets for body and placement selection with visible and keyboard-accessible selected state.
- Reaffirm no side-effect expansion: layout interactions should not trigger preview execution, suggested-build generation, candidate load, validation compare, or automatic persistence.

Stage 11E is a micro-polish and interaction hardening pass:

- Tighten Planner context copy in `ColonyPlannerWorkspace.tsx`, `ColonyPlannerHeader.tsx`, and `ColonyPlannerSectionNav.tsx` so `Suggested Builds -> Build Plan -> Preview Result` is the clearly visible path and `Observed Evidence`, `Validation` are explicitly secondary.
- Keep `BuildPlanSection` and `BuildPlanBodyView` framing unchanged: `List view` stays canonical editing, `Layout view` stays a planning readout.
- Maintain separate interactive controls for body selection and placement selection and preserve keyboard access while avoiding nested interactive elements.
- Confirm user-visible copy avoids non-goal logistics wording and unsafe claims while remaining planning/conservative.
- Reinforce no interaction side effects: no `simulateBuild` auto-run, no Suggested Build mutation, and no automatic persistence from layout interactions.

Stage 11F is the Stage 11E follow-up micro-polish:

- `BuildPlanSection` workflow chips now surface `Suggested Builds`, `Build Plan`, `Preview Result`, `Observed Evidence`, and `Validation` with explicit step numbering and no abbreviated later-step label.
- Keep `List view` as the canonical editable surface and `Layout view` as read-only planning readout; all layout interactions remain non-mutating for preview execution and suggested-build generation.
- Copy across the planner workflow remains conservative (`Use List view to edit`, `Read-only planning readout` framing), with `Observed Evidence` and `Validation` consistently represented as later planning steps.
- Preserve separate interactive targets for body and placement selection in `BuildPlanBodyView` / `BuildPlanLayoutDetailPanel`, including keyboard-friendly selection state.
- Keep explicit no-side-effect behavior for planning interactions and no mechanics changes.
- This pass remains frontend visual/copy/accessibility hardening for planner clarity before broader picker/table work resumes.

Stage 11G is a focused label and header consistency pass after Stage 11F.

- `ColonyPlannerHeader.tsx` workflow chip labels are normalized to match the same user-facing terms used in `ColonyPlannerSectionNav` and `BuildPlanSection` (`Observed Evidence`, `Validation` without inline “Later step” suffix in chip labels).
- Accessibility intent remains explicit via screen-reader semantics on later-step chips while avoiding visual duplication in labels.
- Added a focused regression test for `ColonyPlannerHeader` to guard label consistency and ensure the Run Preview button remains an explicit, opt-in action.
- No new planner mechanics introduced; selection/edit boundaries remain unchanged (`List view` editable, `Layout view` readout-only).

## Stage 16C Workspace Modes

Stage 16C decomposes the central planner flow without changing the underlying hooks or backend contracts. `SimulationPreview.tsx` still owns facility-template and simulation-summary queries, `useSimulationPreviewPlan`, and `useSimulationPreviewRun`, but it now renders one active workspace mode at a time:

- **Build Plan** is the default mode and the only default central panel. It contains the planning focus banner, editable Build Plan, structure picker/replacement flow, import status, start options, and List/Layout editor.
- **Suggested Builds** is isolated behind a mode tab or the Build Plan start card. It preserves quality filtering, player-facing categorisation, comparison, explicit `Generate Suggested Builds`, and deliberate load into the Build Plan.
- **Preview** focuses on the current Preview Result and explicit `Run Preview` control. The mode shows not-run/current/stale state without mixing placement editing into the result surface.
- **Evidence** hosts manual Observed Evidence as a workspace mode instead of an always-visible stacked section.
- **Validation** hosts Validation as a workspace mode and still calls comparison only when a preview result exists.

The left topology rail and right summary rail remain mounted while central modes change. Topology selection updates planning focus copy and Build Plan row highlighting, but it does not filter away placements or mutate the plan. Right-rail Evidence/Validation controls map to the corresponding central modes for compatibility with the workspace shell.

This pass intentionally reduces central scroll depth by replacing the previous Build Plan + Suggested Builds + Preview + Evidence + Validation vertical stack with mode switching. It does not introduce routes, modals, nested accordions, hidden fetch loops, automatic Preview, automatic Suggested Build generation, automatic Validation, or autosave behaviour.

## Stage 16E Role-Hint Workspace Integration

Stage 16E keeps the Stage 16C workspace architecture but makes its persistent shell strategically aware at a glance.

| Surface | Stage 16E role context |
|---|---|
| `ColonyTopologyRail.tsx` | Body rows show compact inferred role badges such as Main Station Candidate, Colony Anchor Candidate, Industrial Candidate, Refinery Candidate, Tourism Pressure, Support Body, Sparse Metadata, or Unknown Role. Rows also show qualitative confidence chips. |
| `WorkspaceSummaryRail.tsx` | When a body or placement-backed body is selected, the summary rail shows inferred roles, `tentative`/`likely`/`strong` confidence, short reasoning, advisory conflicts/warnings, and Architect/primary-port context. |
| `SimulationPreview.tsx` workspace modes | Build Plan, Suggested Builds, Preview, Evidence, and Validation each receive a small mode-aware role context strip. The strip is informational only and does not duplicate the full role panel. |
| `colonyRoleHintUtils.ts` | Owns compact labels, confidence derivation, conflict detection, warning copy, and primary-port context for read-only role hints. |

The confidence model is deliberately qualitative and frontend-only. It uses existing plan shape signals: placement concentration, primary/port presence, support/economy mix, topology spread, and metadata quality. Sparse or unknown body metadata lowers confidence; no fake percentages are shown.

Role conflicts are displayed as conservative overlap indicators rather than validation errors. Rendering a role hint never runs Preview, generates Suggested Builds, saves a role, edits the Build Plan, changes scoring, changes CP/economy/service mechanics, mutates observed evidence, or triggers validation. Primary-port language remains advisory: ED-Finder can reference planned primary-port placement context, but Architect Mode observation is not recorded or editable in Stage 16E.

## Stage 16F Declared Role Assignment

Stage 16F adds explicit user-declared roles to the dedicated Colony Planner workspace. The implementation remains frontend/local-project only.

| Surface | Stage 16F role behaviour |
|---|---|
| `colonyRoles.ts` | Defines `RoleSource`, `RoleConfidence`, `ColonyBodyRole`, `DeclaredColonyRole`, supported declared-role options, normalisation helpers, conflict detection, and project summary helpers. |
| `colonyProjectStore.ts` | Persists `declared_roles` inside local Colony Projects. Old projects without the field normalise to an empty list. Save, duplicate, active-project filtering, and unsaved-change detection include declared roles. |
| `WorkspaceGrid.tsx` | Renders the selected-body strategy card in the central workspace. Users add/remove declared roles there after selecting a body; topology row clicks remain navigation/context only. |
| `ColonyTopologyRail.tsx` | Continues to be navigational and contextual. It may display compact `Declared:` badges, but it does not mutate role state. |
| `WorkspaceSummaryRail.tsx` | Shows project-level declared-role coverage, selected-body source-separated role badges, role conflicts, and primary-port/Architect advisory context. |

Role sources are deliberately separate in the UI:

- `Inferred:` means ED-Finder advisory context from current placements/body data.
- `Declared:` means user strategic intent saved locally with the project.
- `Observed:` remains evidence-backed context; Stage 16F only shows missing Architect observation context where relevant and does not create observed role facts.

Declared roles do not affect Simulation Preview calculations, CP, scoring, economy/service propagation, optimiser generation/ranking, Search Tuning, Observed Evidence semantics, Validation behaviour, imports, EDMC ingestion, or hauling/material workflows. Suggested Builds can still show inferred strategic emphasis, but loading or generating candidates never auto-assigns declared roles.

## Stage 17B Suggested Builds Rescue

Stage 17B keeps the Stage 16C workspace architecture intact and only rescues the Suggested Builds mode.

Frontend behaviour:

- raw API/JSON/internal error text is hidden by default
- the visible error is: `Suggested Builds are temporarily unavailable. You can still edit your Build Plan manually or try again.`
- Retry remains available
- technical details are only rendered after the user expands them
- if generated candidates are all trivial, the mode shows: `No useful suggested builds are available yet. Start manually or provide more system data.`

Candidate display now applies a usefulness floor before rendering cards. It filters colony-ship-only plans, colony ship plus generic one-structure bootstraps, one generic low-purpose port/station plans, duplicate near-identical plans, and plans without clear player-facing purpose. Candidate cards continue to explain what the plan is for, why it was suggested, tradeoffs, and the next manual review step.

This stage does not redesign the topology rail, summary rail, central workspace layout, mode tabs, role cards, project persistence, or preview result surface. It does not auto-generate Suggested Builds, auto-load a candidate, auto-run Preview, or add role-aware optimiser integration.

## Stage 16G Role Review

Stage 16G adds declared-vs-observed strategic role review without adding role mechanics.

| Surface | Stage 16G role-review behaviour |
|---|---|
| `colonyRoleReview.ts` | Derives lightweight observed role signals from existing `ObservedFact` records and compares them with local declared roles. Emits consistency labels, compact summaries, conflict counts, and coverage metrics. |
| `RoleReviewCard.tsx` | Shared compact review card for Evidence and Validation modes. Shows Declared Strategy count, Observed Colony State count, match/mismatch counts, source-labelled role chips, and short advisory summaries. |
| `EvidenceWorkspaceView.tsx` | Shows Evidence Role Review above the existing Observed Evidence panel. The panel remains the source for manual evidence; role review only reads evidence. |
| `ValidationWorkspaceView.tsx` | Shows Validation Role Review above the existing validation comparison panel. This is strategic context and does not auto-resolve validation results. |
| `SimulationPreview.tsx` | Fetches existing observed facts only while Evidence or Validation mode is active, derives observed role signals, and passes review context to the relevant mode. |
| `WorkspaceSummaryRail.tsx` | Adds a compact strategic consistency/observed-role coverage line to the persistent summary rail. |

The review model uses these terms:

- **Declared Strategy**: user-declared local project roles.
- **Observed Colony State**: role signals from existing observed evidence.
- **Inferred Planning Signals**: advisory role hints from topology and plan shape.

Strategic consistency indicators are advisory only: **Strategy aligned**, **Partially aligned**, **Strategy diverging**, and **Insufficient observed evidence**. The UI may say that declared Industrial Core diverges from observed Tourism Focus, or that no observed evidence exists yet, but it never changes the project, declared roles, observed facts, Preview, Suggested Builds, optimiser ranking, scoring, CP, economy, service propagation, imports, EDMC ingestion, or hauling/material workflows.

Stage 16G still does not add backend/cloud role persistence, observed-role editing, Architect Slot Survey storage, primary-port editing, role-aware optimiser integration, or role-aware simulation mechanics.

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

Stage 5C uses `simulation-preview/optimiser/` for candidate comparison. Stage 5D keeps the optimiser components grouped there and adds an opt-in copy callback from `SimulationPreview.tsx`. Candidate details can show `Copy to Build Plan` only when that callback is present; otherwise the panel remains honestly read-only. Non-empty preview plans require confirmation before replacement, and copying a selected candidate into the existing editor does not save, commit in-game, or auto-run preview. The preview tracks optimiser-candidate origin and marks that origin as edited once the user manually changes placements.

Stage 5E adds the comparison engine under `simulation-preview/optimiser/comparison/`. It intentionally exports serialisable types, source helpers, deterministic comparison logic, and pure formatter helpers without rendering the full comparison UI. Stage 5F consumes this engine in a focused show/hide comparison panel within optimiser candidate details. Stage 5.9C positions that panel inside the Colony Planner → Suggested Builds section and adds generated-request visibility so users can tell when target archetype, max candidate count, or estimated-data controls have changed since generation. Stage 5.9D keeps those UX behaviours intact while moving state and layout ownership out of the main composition file. Stage 5.9E hardens the workflow by keeping generated candidates visible when controls become stale, adding generated/current value detail, warning near stale candidate copy/compare controls, and requiring explicit older-candidate confirmation before stale candidates can be copied. It also marks an existing Preview Result stale when the exact preview fingerprint changes after an explicit run; that fingerprint includes system ID, target archetype, and resequenced placements. The comparison panel remains advisory and read-only; it does not run preview, mutate placements, save builds, or replace the Stage 5D copy confirmation flow. Candidate-vs-candidate comparison remains engine-supported, with selector UI deferred to avoid clutter. Stage 6 observed-vs-predicted validation remains deferred until this workflow safety is stable.

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

## Stage 11H - Layout Import Staleness Guardrail

Stage 11H is a narrow follow-up to keep the planner readout state coherent during system changes.

- `BuildPlanSection` now clears layout-import status/result/error state when `systemId64` changes.
- This prevents stale `Import / refresh system layout` banners from carrying over when users move between systems.
- It is a passive UX guardrail only: import remains manual and side-effectful only when explicitly triggered.
- No simulator/execution/mechanics behavior is changed.

Chronology note:

- Stage 11F happened before Stage 11G, and Stage 11H follows Stage 11G on this branch.

## Stage 12A - Structure Picker / Table Foundation

Stage 12A introduces a focused picker surface in List view without changing planner mechanics or introducing automatic actions.

- `BuildPlanEditor.tsx` now exposes an explicit `Browse structures` control per placement.
- `StructurePickerTable.tsx` is a dedicated presentational component for template comparison, search, location filtering, conservative validity hints, and explicit row selection.
- `structurePickerUtils.ts` owns pure helper logic for:
  - location-kind normalization (`orbital`, `surface`, `both`, `unknown`)
  - filter matching
  - selected/no-body/unknown-body context resolution
  - conservative warning and validity-label derivation

Safety boundaries in Stage 12A:

- List view remains the canonical editable path.
- Layout view remains read-only planning output.
- Picker selection updates only the current placement template through the existing `onUpdate` callback.
- No automatic preview execution, no Suggested Build generation/load, no persistence, and no backend mutation are introduced.
- No scoring, mechanics, optimiser ranking/generation, Search Tuning, Observed Evidence, or Validation behavior changes are introduced.

Test coverage added in Stage 12A:

- `StructurePickerTable.test.tsx` for rendering, search/filter behavior, context/warning labels, and explicit selection callback behavior.
- `structurePickerUtils.test.ts` for deterministic helper behavior and conservative warning labels.
- `SimulationPreview.optimiser.test.tsx` coverage for opening/using picker controls without preview or suggested-build side effects.

Deferred to Stage 12B:

- Variant/family grouping, richer compare layouts, and broader replacement flows.
- Any layout-view-side picker action (Layout remains read-only).
- Backend catalogue enrichment and non-frontend planner mechanics work.

## Stage 12B - Replacement Review and Architect Context

Stage 12B keeps List view as the editing surface while making picker-driven replacements explicit and reversible until confirmed.

- `StructureReplacementComparison.tsx` provides a focused current/proposed comparison panel for structure replacement.
- Selecting a row in `StructurePickerTable` now opens replacement review. It does not mutate the placement until the user chooses `Apply replacement`.
- `Apply replacement` calls the existing Build Plan `onUpdate` path with the proposed facility template only. `Cancel replacement` closes the panel with no placement change.
- The comparison is read-only and includes structure name, tier, allowed location, pad size, economy, role/category, CP gives/needs, confidence, compatibility labels, warning chips, and body context.
- List view shows read-only Architect primary-port planning context. The copy frames Architect Mode as something to check before final station placement, notes that an inconvenient flagged slot can be used for a lighter outpost, and states that primary-port location is not a Build Point source.
- Existing primary-port flags are displayed as read-only state. Stage 12B does not add `make primary`, `remove primary`, arbitrary slot assignment, or predicted-slot logic.

Safety boundaries in Stage 12B:

- Layout view remains read-only.
- No automatic preview execution, Suggested Build generation/load, validation, persistence, import, or backend mutation is introduced by comparison or apply/cancel.
- No scoring, CP formulas, economy logic, buildability rules, service unlock rules, optimiser ranking/generation, Search Tuning, Observed Evidence, or Validation behavior changes are introduced.

Test coverage added in Stage 12B:

- `BuildPlanEditor.test.tsx` for replacement review opening, rendered comparison values, cancel/apply behavior, and read-only primary-port wording.
- `SimulationPreview.optimiser.test.tsx` coverage updated so picker selection opens comparison first and still avoids preview/optimiser side effects.

Deferred to Stage 12C:

- Architect Slot Survey data entry/import and confirmed primary-port slot evidence handling.
- Any Layout-view action surface beyond read-only planning explanation.

## Stage 12C - Picker Grouping and Replacement Delta Polish

Stage 12C improves the List-view picker and replacement review without changing planner mechanics.

- `structurePickerGroupingUtils.ts` derives frontend-only group labels from existing facility-template fields. The grouping is conservative: ports are separated by allowed location when possible, support facilities use existing economy/category hints, and anything uncertain falls back to support facilities or unknown/other.
- `StructurePickerTable.tsx` renders grouped catalogue sections while retaining search, location filtering, validity chips, body-context warnings, and explicit `Select structure` controls.
- Picker rows now distinguish the current structure from the proposed replacement while replacement review is open. This is display state only.
- `structureReplacementDeltaUtils.ts` builds replacement field deltas and warning deltas for the review panel.
- `StructureReplacementComparison.tsx` now emphasizes changed fields, keeps unchanged fields subdued but readable, and separates warnings into added, removed, and unchanged buckets.
- Architect primary-port copy remains read-only and points users back to System Map and Architect Mode for confirmation before final major station placement. It states that primary-port location is placement guidance, not a Build Point source, and still suggests an outpost on an inconvenient flagged slot with the main station placed elsewhere.

Safety boundaries in Stage 12C:

- List view remains the canonical editable surface; Layout view remains read-only planning output.
- Apply and cancel remain explicit. No replacement is applied until `Apply replacement` calls the existing placement update callback.
- No backend mutation, import/storage, persistence, automatic preview, Suggested Build generation/load, validation call, polling, or silent mutation is introduced.
- No scoring, CP formulas, economy logic, buildability rules, service unlock logic, optimiser ranking/generation, Search Tuning, Observed Evidence, or Validation behavior changes are introduced.
- No primary-port editing controls, make/remove primary actions, arbitrary slot assignment, or full Architect Slot Survey are introduced.

Test coverage added in Stage 12C:

- `structurePickerGroupingUtils.test.ts` for group-label derivation and stable grouped ordering.
- `StructurePickerTable.test.tsx` for grouped headings, search/filter behavior across grouped data, current/proposed highlighting, and explicit selection behavior.
- `StructureReplacementComparison.test.tsx` for changed vs unchanged field display and warning added/removed/unchanged deltas.
- Existing `BuildPlanEditor.test.tsx` and `SimulationPreview.optimiser.test.tsx` continue to cover apply/cancel behavior, no preview/optimiser side effects, and absence of primary-port editing controls.

Deferred to Stage 12D:

- Architect Slot Survey data entry/import and confirmed primary-port slot evidence handling.
- Better body/orbit recommendation context once confirmed Architect-slot data exists.
- Backend catalogue enrichment, saved-build persistence, logistics/material planning, and any Layout-view action surface.

## Stage 12D - Planner Guidance Foundation

Stage 12D keeps the planner deterministic and frontend-only while making existing placement risks easier to interpret.

- `plannerGuidanceUtils.ts` maps existing warning strings and body/template facts into `info`, `advisory`, `caution`, `high-risk`, and `incompatible` guidance. The helper does not alter warnings, scoring, preview results, or optimiser ranking.
- `PlannerGuidanceList.tsx` renders compact guidance rows in the List editor and read-only Layout surfaces.
- List view guidance explains estimated template data, sparse body metadata, unknown or missing body context, and Architect primary-port checks without blocking replacement Apply/Cancel.
- Layout view guidance repeats only high-signal body/placement context so the readout advises without becoming an editing surface.
- Architect copy remains read-only: primary-port location should be checked in System Map -> Architect Mode before final major station placement, it is not a Build Point source, and an inconvenient flagged slot can be treated as an outpost candidate while the main station goes elsewhere.

Safety boundaries in Stage 12D:

- No backend mutation, persistence, import/storage, auto-preview, auto-generation, auto-load/save, polling, or silent mutation is introduced.
- No scoring, CP formulas, economy mechanics, buildability rules, service unlock logic, optimiser ranking/generation, Search Tuning, Observed Evidence, or Validation behavior changes are introduced.
- No primary-port editing controls, make/remove primary actions, arbitrary slot assignment, or Architect Slot Survey storage are introduced.

Test coverage added in Stage 12D:

- `plannerGuidanceUtils.test.ts` covers severity mapping and deterministic guidance generation.
- `BuildPlanEditor.test.tsx` covers guidance rendering while preserving explicit replacement cancel/apply behavior.
- `BuildPlanBodyView.test.tsx` covers Layout guidance rendering and confirms primary-port guidance remains read-only.

Deferred to Stage 13:

- Architect observation status and unknown/observed survey concepts.
- Topology-aware Layout readout beyond guidance rows.
- Any persistent Architect survey data, imports, or primary-port observation workflows.

## Stage 13A - Architect Observation Foundation

Stage 13A adds a display-only Architect observation layer to the planner UI. It does not add persistence, imports, scoring, or editing flows.

- `architectObservationUtils.ts` normalizes optional frontend Architect observation context into `not_observed`/`observed` survey state, unknown/observed primary-port flag state, and optional orbital/ground slot counts.
- `ArchitectObservationPanel.tsx` renders the status in the List editor and read-only Layout detail panel. The default state is deliberately unknown: `Architect survey: not observed`, `Primary-port flag: unknown`, and unknown slot counts.
- When tests or future callers provide observed mock context, the panel can render `Architect survey: observed` and `Primary-port flag: observed on ...` without treating it as backend-confirmed truth.
- Existing primary-port guidance remains conservative: check System Map -> Architect Mode before final major station placement, primary-port location is placement guidance rather than a Build Point source, and an inconvenient flagged primary-port slot can be used for an outpost while the main station is placed elsewhere.

Safety boundaries in Stage 13A:

- No primary-port editing controls, make/remove primary actions, arbitrary slot assignment, Architect Slot Survey storage, backend imports, EDMC ingestion, auto-preview, auto-generation, auto-load/save, polling, or silent mutation are introduced.
- No Simulation Preview scoring, optimiser ranking/generation, CP formulas, economy mechanics, service unlock logic, buildability rules, Observed Evidence, or Validation behavior changes are introduced.
- Unknown Architect context remains unknown unless explicit observed context is supplied to the frontend component.

Test coverage added in Stage 13A:

- `architectObservationUtils.test.ts` covers unknown defaults and observed mock context.
- `ArchitectObservationPanel.test.tsx` covers read-only unknown/observed rendering and absence of primary-port controls.
- Existing Build Plan tests cover the integrated read-only wording in List/Layout surfaces.

Deferred to later Stage 13 work:

- Storage/import decisions for Architect surveys.
- Full Architect Slot Survey UI and exact topology capture.
- Topology-aware Layout grouping beyond the current read-only observation panel.

## Stage 13B - Layout Topology Readout

Stage 13B adds read-only topology readouts to Layout view without turning Layout into an editor or map engine.

- `layoutTopologyUtils.ts` derives per-body topology context from existing Build Plan placements, facility templates, body metadata, and optional frontend Architect observation context. It counts planned orbital, ground, and unknown-location structures without inventing slot capacity.
- `LayoutTopologyReadout.tsx` renders compact chips for body state, planned orbital/ground counts, conservative ground capability, Architect survey status, unknown/observed slot counts, and primary-port context.
- `BuildPlanBodyView.tsx` shows compact topology context on each body group. `BuildPlanLayoutDetailPanel.tsx` shows the fuller readout for a selected body and keeps placement detail read-only.

Safety boundaries in Stage 13B:

- Layout view remains read-only. No placement mutation, primary-port setting/unsetting, slot editing, import/storage, polling, auto-preview, auto-generation, or silent mutation is introduced.
- Unknown Architect slot counts stay unknown by default. Observed slot labels render only when explicit frontend observation context is supplied to helpers/components.
- The readout does not change Simulation Preview scoring, optimiser ranking/generation, CP formulas, economy mechanics, service unlock logic, buildability rules, Observed Evidence behavior, Validation behavior, or persistence.

Deferred to later Stage 13 work:

- Strategic body relationship guidance and candidate labels.
- Persistent Architect survey capture and import/storage decisions.
- Full Architect Slot Survey UI and exact map/topology rendering.

## Stage 13C - Strategic Topology Guidance

Stage 13C layers conservative strategic guidance onto the Stage 13B Layout readout without changing planner mechanics.

- `strategicTopologyGuidanceUtils.ts` derives deterministic body-group guidance from existing placements, templates, body metadata, and optional frontend Architect observation context.
- `BuildPlanBodyView.tsx` and `BuildPlanLayoutDetailPanel.tsx` render this guidance under a compact **Strategic topology** heading on read-only Layout body surfaces.
- Labels include main-station candidate, good support body, likely tourism/agriculture pressure, sparse metadata confirmation, unknown Architect primary-port flag checks, and the outpost option for inconvenient flagged primary-port slots.

Safety boundaries:

- The guidance does not call `simulateBuild`, optimiser generation, validation compare/review, observation mutation, persistence, import, polling, or any backend endpoint.
- It does not change scoring, CP formulas, economy mechanics, service unlock logic, buildability checks, optimiser ranking, Simulation Preview scoring, Observed Evidence, or Validation behavior.
- It does not add primary-port editing, slot editing, Architect Slot Survey storage, or map-like spatial rendering. Unknown Architect context remains unknown until future stages provide observed data.

## Stage 14A - Observed Evidence Planning Expansion

Stage 14A improves the existing Observed Evidence panel as a planning review surface without changing the observed-facts backend contract.

- `observedEvidencePlanningUtils.ts` derives conservative frontend-only categories from existing observed-fact fields: primary-port / Architect observation, structure actually built, body / slot observation, economy observation, service / population / security observation, and general note.
- `ObservedEvidencePlanningSummary.tsx` renders the planned / observed / unknown distinction above the manual entry form and shows category counts for the visible evidence list.
- `ObservedEvidencePanel.tsx` keeps the existing manual create/edit/delete flows and inserts the summary as passive context only.

Safety boundaries:

- The panel still calls only observed-facts list/create/update/delete endpoints through explicit user actions already present in the UI.
- Viewing Observed Evidence does not call `simulateBuild`, optimiser generation, Validation compare/review, persistence/import, polling, auto-preview, or any planner mutation.
- The new primary-port / Architect category is a label for manually recorded evidence only. It does not add primary-port editing, Architect Slot Survey storage, slot editing, or confirmed primary-port truth.

Deferred:

- Dedicated Architect survey evidence input/storage, richer slot evidence fields, and import/EDMC ingestion.

## Stage 14B - Validation Review Clarity

Stage 14B keeps the existing Validation data flow and improves the readout language around mismatches.

- `validationReviewCategoryUtils.ts` maps existing comparison row statuses into frontend-only review categories: Matches plan, Differs from plan, Missing observation, Unknown / not checked, and Needs manual review.
- `ValidationComparisonCard.tsx` renders the category chip and short category explanation beside the existing status, severity, and confidence labels. The raw compare status is still preserved for filters and tests.
- `ValidationPanel.tsx` adds a compact reminder strip: Preview assumes the current plan and should be confirmed in-game; Architect primary-port context is not a dedicated validation field and should be checked in System Map -> Architect Mode before final major station placement.
- Copy remains conservative: differing rows say `Observed value differs from preview.` Unknown or missing rows do not imply the plan is wrong, and no row auto-resolves a mismatch.

Safety boundaries:

- No compare/review endpoint, backend validation engine, Observed Evidence semantics, Simulation Preview scoring, optimiser behavior, CP/economy/buildability/service mechanics, persistence, imports, EDMC ingestion, or planner state mutation changed.
- Validation remains an explicit review surface. It does not auto-run Preview, auto-generate, auto-save, poll, mutate evidence, or write back to the Build Plan.
- Architect/primary-port wording is read-only. Stage 14B does not add Architect survey storage, slot editing, or primary-port editing controls.

Deferred:

- Dedicated Architect survey validation once a later stage adds observed Architect data storage/input.
- Higher-level mismatch grouping, review workflows, and any automatic resolution.

## Stage 15 - Planner Workspace Architecture Direction

Stage 15A documents the next architecture turn in `docs/colonisation-redesign/stage-15-planner-workspace-redesign-plan.md`. The important conclusion for this file is that `simulation-preview/` should no longer be treated as the long-term owner of the whole Colony Planner workspace. It remains the existing preview/planning implementation boundary, but the next product shape belongs under the dedicated `features/colony-planner/` workspace.

Current architecture reality:

- `#colony-planner/system/{id64}` already exists.
- `ColonyPlannerWorkspace.tsx` currently loads system detail and renders `SimulationPreviewPanel`.
- `SimulationPreview.tsx` still owns the vertical workflow: Build Plan, Suggested Builds, Preview Result, Observed Evidence, and Validation.
- The Build Plan has both List view editing and read-only Layout view, but the body/topology readout is not yet the primary navigation model.

Stage 15 target architecture:

- Keep Simulation Preview execution, preview-result rendering, and compatibility exports stable while a new topology-first workspace shell grows around them.
- Introduce a `features/colony-planner/` ownership boundary for project state, body tree navigation, persistent summary, drawer modes, and saved project lifecycle.
- Reuse existing `simulation-preview` utilities and components where safe, especially placement editing hooks, structure picker/replacement logic, preview execution, Observed Evidence, and Validation panels.
- Move Observed Evidence and Validation presentation out of the always-visible vertical stack and into workspace drawers/modes once the workspace shell supports them.
- Keep all side effects explicit: no auto-preview, no auto-generation, no auto-validation, no auto-save, and no primary-port truth editing.

Implementation guidance for later stages:

- Do not add more workspace-level state to `SimulationPreview.tsx` if it belongs to saved projects, route/workspace layout, body tree selection, or drawer mode.
- New topology tree and project persistence code should live under `frontend-v2/src/features/colony-planner/` and call into existing preview components through narrow props.
- If existing `simulation-preview` helpers become generally useful to the workspace, move or re-export them deliberately rather than duplicating logic.
- Keep `SimulationPreviewPanel` as the compatibility adapter for the dedicated Planner Workspace while topology-first workspace pieces grow around it.

Stage 15B implementation note:

- `ColonyPlannerWorkspace.tsx` now owns the workspace shell around `SimulationPreviewPanel`: compact header, left topology placeholder rail, central contained planner content, and right summary/context rail.
- The `simulation-preview/` folder still owns the existing planner internals and preview/evidence/validation behavior. Stage 15B intentionally does not move those internals yet.
- The topology rail and summary rail are placeholders for Stage 15D and later project-persistence work. They must remain read-only until those stages explicitly add selection/edit/save behavior. Stage 15D later replaced the topology placeholder with read-only body-tree selection, while still deferring edit/save behavior.
- Stage 15C removes the System Detail embedded planner path. From Stage 15C onward, System Detail is an overview/discovery modal with a compact Colony Planner entry card, and `#colony-planner/system/{id64}` owns the full planning workflow.

Stage 15C implementation note:

- `SystemDetailModal.tsx` no longer imports or renders buildability, regional position, Recommended Builds, `SimulationPreviewPanel`, slot prediction, Observed Evidence, or Validation surfaces inline.
- Recommended Builds and Suggested Builds are workspace-first. System Detail only tells users that suggested builds can be reviewed in the Colony Planner, and does not fetch or generate candidates for the overview card.
- The System Detail CTA routes through the existing app handler to `#colony-planner/system/{id64}`; the Planner Workspace `Back to system detail` action remains the return path.
- The old `simulation-preview/` internals remain intact and available inside the dedicated workspace. Stage 15C does not change preview execution, optimiser calls, validation/evidence behavior, imports, persistence, or scoring.
- Stage 15D completed the next architecture step by replacing the placeholder topology rail with a real body/topology tree MVP while keeping editing and persistence deferred until their scoped stages.

Stage 15D implementation note:

- `frontend-v2/src/features/colony-planner/ColonyTopologyRail.tsx` owns the read-only body-tree/navigation MVP for the workspace. It uses loaded `SystemDetail` bodies plus a one-way planner snapshot to show body rows, child indentation where parent metadata exists, placement counts, orbital/surface/flex chips, unknown/unmatched body groups, and unassigned placements.
- `SimulationPreviewPanel` and `SimulationPreview` now accept an optional `onPlanSnapshotChange` callback. This is a narrow read-only bridge from the existing central planner state back to the workspace shell; it does not move editing ownership out of `simulation-preview/`.
- `ColonyPlannerWorkspace` owns only local read-only selection state for topology navigation. Selection updates the rail highlight and right summary context, but never mutates placements, never runs Preview, never generates Suggested Builds, never imports layout, and never touches Observed Evidence or Validation.
- Stage 15E should build on this by moving add/replace/move interactions toward selected body/slot context. Stage 15D deliberately leaves all editing inside the central planner content.

Stage 15E implementation note:

- `ColonyPlannerWorkspace` now passes topology selection into `SimulationPreviewPanel` as coordination context. This remains local workspace UI state, not persisted project state.
- `SimulationPreviewPanel`, `SimulationPreview`, and `BuildPlanSection` forward that context to the central Build Plan editor through narrow optional props.
- `BuildPlanSection` renders compact `Currently viewing` context for selected topology bodies/placements and adds an explicit `Add to selected body` control when the selected body exists in the loaded body list.
- `BuildPlanEditor` highlights placement rows related to the selected topology body and focuses/highlights a selected topology placement. Structure picker receives selected topology body context for unassigned rows so warnings can be evaluated without changing the placement.
- The ownership line remains unchanged: topology rail selection is navigation/context only, while placement mutation still happens through central planner buttons/selects and the existing placement editor hook.

Stage 15F implementation note:

- `optimiserQualityUtils.ts` adds a frontend display gate for Suggested Builds. It filters trivial and duplicate candidates after the existing optimiser response is sorted for display, so backend generation/ranking remains unchanged.
- `OptimiserCandidatePanel` renders the useful-build empty state when all returned candidates are filtered out.
- `OptimiserCandidateCard` and `OptimiserCandidateDetails` now present a player-facing category, purpose, reason, tradeoff, and next action for each visible candidate.
- Raw optimiser tags are translated before display. Internal tags remain available in the response/comparison data, but the UI avoids exposing raw labels like `body_diversity`.
- Loading a suggested build remains an explicit workspace action through the existing candidate load path. It still does not run the main Preview, save, import, validate, or mutate observed evidence.

Stage 15G implementation note:

- Saved Colony Projects use localStorage through `features/colony-planner/colonyProjectStore.ts`. This matches existing frontend persistence patterns while avoiding premature backend schema work.
- `ColonyPlannerWorkspace` owns project selection and notes state in the workspace shell. It passes a saved project into `SimulationPreviewPanel` as an `initialRequest`, reusing the existing plan replacement path rather than adding a second editor.
- Project save captures the current one-way planner snapshot: placements, selected body assignments derived from placement body IDs, target archetype, notes, and local status.
- Project load/restore does not run Preview, generation, import, evidence, or validation. It only replaces the editable Build Plan through the same request shape already used for selected recommended plans.
- Delete is implemented as local archive with confirmation so the MVP can hide projects without destructive backend semantics.

Stage 15H implementation note:

- `SimulationPreview` now owns a small `workspaceDrawer` state for Evidence and Validation drawers.
- Observed Evidence and Validation remain existing components; Stage 15H changes presentation and mount timing, not evidence/compare/review behavior.
- Drawer status badges live near the central planner flow. They are intentionally compact until Stage 15I decides whether any status should move into the right workspace summary rail.
- Validation is not mounted until the user opens the Validation drawer. This keeps compare/review advisory and explicit, and avoids the old always-visible stacked panel behavior.

Stage 15I implementation note:

- Stage 15I does not move ownership boundaries again. `features/colony-planner/` remains the workspace shell, and `simulation-preview/` remains the existing planner/editor/preview implementation boundary.
- The hardening pass focused on copy and default visibility: missing body metadata should produce compact fallback labels, not raw body IDs, unless a future technical-details surface explicitly asks for those IDs.
- Optimiser comparison copy now describes body assignment changes in player-facing terms. It still compares only the existing frontend candidate data and does not change optimiser generation, ranking, or scoring.
- The next architecture step is Stage 16A documentation for colony roles and colony planet modelling, not another broad Stage 15 UI rewrite.

## Stage 16 - Colony Role Model Direction

Stage 16A documents the role-model direction in `docs/colonisation-redesign/stage-16-colony-role-model-plan.md`. This is a product and architecture planning layer, not a mechanics implementation.

Architecture direction:

- `features/colony-planner/` should own role intent because roles are workspace/project state tied to topology bodies.
- `simulation-preview/` should continue to own existing Build Plan editing, preview execution, optimiser display, Observed Evidence, and Validation internals until a later stage deliberately moves a boundary.
- Roles should be passed into existing planner/editor components through narrow optional props when they affect copy, filtering, badges, or context.
- Planned roles, observed roles, user-declared roles, and inferred roles must stay distinguishable in the model and UI.
- Primary-port role must be evidence-backed only. It is placement guidance, not a Build Point source, and not arbitrary user truth.

Stage 16A implementation note:

- No code changes are included in Stage 16A.
- The role plan defines the first target roles: Colony Anchor, Colony Planet / Core Body, Main Station Body, Primary Port Body, Industrial Core, Extraction Body, Tourism/Agriculture Body, Military/Security Body, Support Body, and Expansion Reserve.
- Future role UI should start in the topology workspace as read-only badges and explicit central-planner controls, not topology-row click mutations.
- Future optimiser integration should begin as display-only role explanation. Role-aware generation or ranking would require a separate mechanics and scoring review.

Stage 16B implementation note:

- `ColonyPlannerWorkspace.tsx` is now the route container only. It owns system loading, empty state, retry/error state, and hands loaded systems to the workspace shell.
- `WorkspaceGrid.tsx` owns topology selection, the one-way plan snapshot, the controlled Evidence/Validation drawer mode, and planner mounting.
- `useWorkspaceProjectState.ts` owns local-only saved project lifecycle state and wraps the existing `colonyProjectStore`.
- `WorkspaceSummaryRail.tsx` composes compact Project, Plan Health, Selection, Architect, Workspace Modes, and save-state cards.
- `SimulationPreviewPanel` and `SimulationPreview` accept optional controlled drawer props so workspace mode buttons can live in the summary rail while drawer content remains in the existing central planner boundary.
- This stage intentionally leaves Build Plan editing, preview execution, optimiser display, Observed Evidence, and Validation internals inside `simulation-preview/`.
- Suggested Build usefulness filtering remains frontend-only display filtering. Backend candidate generation, ranking, and scoring are unchanged.
- Durable/backend project persistence is deferred to a later persistence stage; local-only browser storage remains the current behavior.

Stage 16D implementation note:

- `simulation-preview/colonyRoleHintUtils.ts` derives read-only colony role hints from existing placement, template, and body topology context.
- `ColonyRoleHints.tsx` renders inferred role hints in the Build Plan Layout body cards and the selected-body detail panel.
- Hints are advisory player-facing context only. They do not introduce editable roles, role persistence, backend role models, automatic role assignment, Preview execution, Suggested Build generation, primary-port editing, or Architect Slot Survey storage.
- Inferred, observed, and future editable role sources remain separate. Stage 16D only emits inferred hints; observed roles require evidence-backed workflows later, and editable roles remain deferred.
- Sparse, unknown, and unassigned bodies render conservative pending/limited hints. Main-station candidate hints appear only from current primary/port/major-tier placement context.
- Backend mechanics, CP formulas, scoring, economy/service logic, optimiser generation/ranking, Simulation Preview calculations, Observed Evidence semantics, Validation behavior, imports, EDMC ingestion, and hauling/material workflows remain unchanged.

## Stage 17C Body-First Planner Rescue

Stage 17C keeps the same ownership boundaries but changes the default interaction shape inside the dedicated workspace.

Workspace shell:

- `ColonyTopologyRail.tsx` renders compact button-like body rows with strong selected/hover/focus states.
- Row content is intentionally limited to body marker, name, short type hint, one planned count, and tiny status markers.
- Unknown and unassigned placement groups remain compact navigation groups.
- Role badges, confidence clusters, raw IDs, and long explanation text are not rendered in the rail by default.

Central body surface:

- `WorkspaceGrid.tsx` now renders a body planning surface above the existing `SimulationPreviewPanel`.
- No body selected shows a short start panel.
- A selected body shows body facts, planned structures on that body, compact warnings, and explicit Add structure here / Review structures actions.
- Add structure here focuses the existing safe body-scoped Build Plan add path; it does not mutate on body click.

Build Plan:

- `BuildPlanSection.tsx` defaults to body view so the first editing surface is body-grouped rather than list-first.
- List view remains available as the advanced editor and continues to own ordered placement editing.
- Navigation clicks do not run Preview, generate Suggested Builds, import layout, validate evidence, or save projects.

Summary rail:

- `WorkspaceSummaryRail.tsx` is reduced to project controls, plan health, current focus, a compact body hint when available, and Evidence/Validation mode controls.
- Local save copy is concise and avoids cloud/persistence essays in the default rail.

EDDN:

- `useEddnFeed.ts` clears transient SSE errors on open/message and clears pending flush timers on cleanup.
- `EddnTicker.tsx` renders a compact reconnecting state instead of raw SSE error text.
