# Stage 4F: Simulation Preview UI Architecture

Stage 4F decomposes the frontend Simulation Preview area so it remains maintainable before Stage 5 optimiser UI work begins. This is a **UI organisation refactor only**. It does not change simulation mechanics, backend API calls, request or response types, scoring, CP logic, economy logic, service logic, observation comparison, or the visual design language.

> Future optimiser UI should not be added back into a monolithic Simulation Preview file. Candidate generation, candidate comparison, and candidate explanation should live in optimiser-specific components or a sibling feature folder that can reuse the existing preview panels and shared atoms.

## Folder Structure

The Simulation Preview UI now lives under `frontend-v2/src/features/system-detail/simulation-preview/`. The old public entry file at `frontend-v2/src/features/system-detail/SimulationPreview.tsx` remains as a thin compatibility wrapper so existing imports continue to work.

| Path | Responsibility |
|---|---|
| `SimulationPreview.tsx` | Top-level orchestration and state for facility/template queries, build-plan state, target archetype, run action, and error/result selection. |
| `SimulationResult.tsx` | Result layout and panel ordering for an already-returned `SimulateBuildResponse`. |
| `BuildPlanEditor.tsx` | Placement editor for facility template, body, primary-port flag, sequence movement, and removal controls. |
| `StartModes.tsx` | Start-mode cards, mode intro copy, and current plan badge. |
| `types.ts` | Preview-local constants and types such as archetype options and `StartMode`. |
| `components/` | One file per shared UI atom, re-exported by `components/index.ts`. |
| `panels/` | One file per major Simulation Preview result panel, re-exported by `panels/index.ts`. |
| `utils/` | Formatting, tone, and placement helper functions shared by preview components. |
| `optimiser/` | Stage 5C read-only optimiser candidate comparison UI, including candidate cards, details, ranking breakdown, placement list, and sorting utilities. |

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

Stage 5 optimiser UI should treat this structure as the boundary for existing Simulation Preview behaviour. Candidate lists, candidate comparison, optimiser warnings, and candidate explanation should be added as optimiser-specific components rather than folded into `SimulationPreview.tsx` or `SimulationResult.tsx`. Existing panels can be reused where they present the same response shape, but optimiser-specific state should remain separate.

Stage 5C uses `simulation-preview/optimiser/` for candidate comparison. Stage 5D keeps the optimiser components grouped there and adds an opt-in load callback from `SimulationPreview.tsx`. Candidate details can show `Load into preview` only when that callback is present; otherwise the panel remains honestly read-only. Non-empty preview plans require confirmation before replacement, and loading copies placements into the existing editor without saving, committing in-game, or auto-running preview. The preview tracks optimiser-candidate origin and marks that origin as edited once the user manually changes placements.

Stage 5E adds the comparison engine under `simulation-preview/optimiser/comparison/`. It intentionally exports serialisable types, source helpers, deterministic comparison logic, and pure formatter helpers without rendering the full comparison UI. Stage 5F consumes this engine in a focused show/hide comparison panel within optimiser candidate details. The comparison panel renders candidate-vs-current-preview deltas from the latest editable preview placements and target archetype while remaining advisory and read-only; it does not run preview, mutate placements, save builds, or replace the Stage 5D load confirmation flow. Candidate-vs-candidate comparison remains engine-supported, with selector UI deferred to avoid clutter.
