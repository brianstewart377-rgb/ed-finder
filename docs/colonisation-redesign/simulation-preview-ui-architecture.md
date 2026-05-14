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
| `ColonyPlannerSectionNav.tsx` | Lightweight visible labels for Build Plan, Optimiser Candidates, and Preview Result. |
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

Stage 6A does **not** add frontend observation entry, automatic validation inside Simulation Preview, EDMC or journal ingestion, saved builds, account persistence, crowdsourcing, auto-learning, or mechanics mutation. Stage 6B can add manual observation entry UI, and Stage 6C can add predicted-vs-observed comparison on top of the stored facts.
