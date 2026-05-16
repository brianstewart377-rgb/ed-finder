# Stage 9B - Dedicated Colony Planner Workspace Feasibility

## Executive Summary

Stage 9B recommends making Colony Planner a dedicated focused workspace in Stage 9C, without removing the embedded planner from System Detail during the first implementation.

The recommended route is `#colony-planner/system/{id64}`. It is explicit, bookmarkable, and avoids overloading the existing `#colony` route, which now means Colony Tracker. As of Stage 9C, Finder result cards and Advanced Search Tuning send `Evaluate in Colony Planner` directly to this workspace. Normal `Details` actions continue to open System Detail.

Stage 9B does not implement the workspace. It maps the current structure and defines the safest implementation plan for Stage 9C.

Stage 9C implementation note: the recommended route has now been implemented as `#colony-planner/system/{id64}`. The workspace uses separate `plannerSystemId` route state, reuses `useSystemDetail(id64)` plus `SimulationPreviewPanel`, moves Finder/Search Tuning/System Detail Evaluate handoffs to the workspace, and keeps the embedded System Detail planner for compatibility. No backend mechanics, scoring, generation, auto-run, auto-generate, or auto-load behaviour changed.

## Current Structure

| area | current behaviour | relevant files |
|---|---|---|
| App shell | `AppInner` renders a persistent `NavBar`, a route-selected page, `SystemDetailModal` when a selected system id exists, and the bottom `EddnTicker`. | `frontend-v2/src/App.tsx` |
| Hash routing | `useHashRoute` parses top-level routes plus optional `system/{id64}` modal children. Unknown routes fall back to Finder. `#optimizer` is a legacy alias for `#search-tuning`. `#system/{id64}` opens System Detail over Finder. | `frontend-v2/src/hooks/useHashRoute.ts`, `frontend-v2/src/hooks/useHashRoute.test.ts` |
| Top-level routes | Current routes are Finder, Watchlist, Pinned, Compare, Map, Advanced Search Tuning, FC Planner, Colony Tracker, and Admin. | `frontend-v2/src/components/NavBar.tsx` |
| System Detail modal | `selectedSystemId` opens the modal over the current route. Close removes the `system/{id64}` child while preserving the parent route. Escape and backdrop close the modal. | `frontend-v2/src/App.tsx`, `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` |
| System data loading | System Detail uses `useSystemDetail(id64)`, a TanStack Query wrapper around `api.system(id64)`. Query keys are system-id scoped and already suitable for reuse by a workspace. | `frontend-v2/src/features/system-detail/useSystemDetail.ts` |
| Embedded Colony Planner | System Detail renders a `Colony Planning` section containing buildability, regional context, recommended builds, the focused `SimulationPreviewPanel`, and slots. The planner focus target has `tabIndex={-1}` and highlight/focus timer cleanup. | `frontend-v2/src/features/system-detail/SystemDetailModal.tsx`, `frontend-v2/src/features/system-detail/SimulationPreviewPanel.tsx` |
| Planner internals | `SimulationPreview` owns the guided planner composition: header, section nav, Build Plan, Suggested Builds, Preview Result, Observed Evidence, and Validation. Preview, generation, and copy-to-plan actions remain explicit. | `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx` |
| Finder handoff | Expanded result cards show `Details` and `Evaluate in Colony Planner`. Details opens System Detail normally. As of Stage 9C, Evaluate routes to `#colony-planner/system/{id64}` when the app provides `onOpenColonyPlanner`, with the old focus-intent handoff retained as a component fallback. | `frontend-v2/src/components/ResultCard.tsx` |
| Search Tuning handoff | Row/open-detail actions open System Detail normally. As of Stage 9C, `Evaluate in Colony Planner` routes to the dedicated workspace when the app provides `onOpenColonyPlanner`; the old focused-detail handoff remains a fallback. | `frontend-v2/src/features/search-tuning/AdvancedSearchTuningTab.tsx` |
| Current focus intent | `App` still clears/passes `detailFocus` for compatibility. `SystemDetailModal` scrolls/focuses/highlights the embedded planner when no workspace handler is provided; the app-provided Stage 9C handler routes the top CTA to the dedicated workspace. | `frontend-v2/src/App.tsx`, `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` |

The current architecture is intentionally modal-centric: any parsed `selectedSystemId` means "render System Detail modal". A dedicated workspace should not reuse that same field for planner pages, or the app will risk rendering the modal over the new workspace.

## Route Options

| option | pros | cons | complexity | recommendation |
|---|---|---|---|---|
| `#colony-planner/system/{id64}` | Clear user-facing meaning; shareable/bookmarkable; avoids `#colony` ambiguity; easy to explain in tests and docs; preserves System Detail modal routes. | Adds a new route shape and a long hash segment; requires app-level workspace state separate from modal state. | Medium | Recommended. |
| `#planner/system/{id64}` | Shorter; still bookmarkable; less tied to current copy if the product name changes later. | Less specific in a multi-tool app; could be confused with FC Planner or other planning tools. | Medium | Acceptable fallback, but weaker label clarity. |
| `#colony/system/{id64}/planner` | Keeps colony-related routes grouped. | Conflicts with `#colony` meaning Colony Tracker; makes one route host two unrelated concepts; harder to keep mental models clear. | Medium-high | Not recommended. |
| `#finder/system/{id64}?focus=colony-planner` or equivalent | Minimal route model change; close to current focus-intent behaviour. | Keeps planner inside System Detail and does not solve the "buried headline feature" problem; hash-query support is currently not part of the router. | Low-medium | Not recommended for the dedicated workspace goal. |
| Workspace state inside existing `#colony` route | Avoids a new top-level route. | Reuses a route that already means Colony Tracker; likely increases Colony Tracker vs Colony Planner confusion. | Medium-high | Not recommended. |

## Recommended Route

Use `#colony-planner/system/{id64}` for the Stage 9C implementation.

Implementation detail for Stage 9C: extend routing state so planner workspace IDs are separate from System Detail modal IDs. A safe shape is:

- `route: 'colony-planner'`
- `plannerSystemId: number | null`
- `selectedSystemId: number | null` remains modal-only
- `openColonyPlanner(id64)` writes `#colony-planner/system/${id64}`
- `openSystem(id64)` keeps the existing modal route behaviour

This avoids treating every `system/{id64}` hash as a modal overlay and lets the workspace render as a full page inside the app shell.

Do not add a static top-level `Colony Planner` nav tab in the first pass. The workspace is system-specific, so a tab without a selected system would need a new chooser or empty state. Keep entry through Finder, Search Tuning, System Detail, and later secondary-system surfaces.

## Data Loading / Component Reuse Plan

Reuse the existing system-detail data path:

- `ColonyPlannerWorkspace` should call `useSystemDetail(id64)`.
- The workspace should render `SimulationPreviewPanel` or `SimulationPreview` rather than duplicate planner logic.
- TanStack Query will dedupe `['system', id64]` data between System Detail and the workspace.
- Loading, error, and retry states should be local to the workspace wrapper.

Recommended component shape:

- Add a light `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx` wrapper.
- Header shows system name, ID64, coordinates, and concise context.
- Main content reuses `SimulationPreviewPanel`.
- Add an `Open full system detail` action.
- Add a `Back to Finder` fallback action.

System context should stay light in Stage 9C:

- include name, ID64, coordinates, and a short buildability/economy summary if already present in the loaded `SystemDetail`.
- do not copy the full bodies/stations tables into the first workspace implementation.
- link to full System Detail for inspection-heavy tasks.

Keep the embedded planner in System Detail during Stage 9C. The first implementation should make the workspace primary without abruptly removing a working path or breaking existing deep links.

## Entry Point / Handoff Plan

| entry point | Stage 9C behaviour | reason |
|---|---|---|
| Finder ResultCard `Details` | Keep opening System Detail modal. | Details means inspection, not planning. |
| Finder ResultCard `Evaluate in Colony Planner` | Navigate to `#colony-planner/system/{id64}`. | This is the clearest direct path to the dedicated workspace. |
| Advanced Search Tuning row click | Keep opening System Detail modal. | Row click is a general inspection action. |
| Advanced Search Tuning `Open system detail` | Keep opening System Detail modal. | Explicit detail action should remain unchanged. |
| Advanced Search Tuning `Evaluate in Colony Planner` | Navigate to `#colony-planner/system/{id64}`. | Tuning handoff should land in the same planner workspace as Finder. |
| System Detail `Open Colony Planner` | Navigate to `#colony-planner/system/{id64}` after Stage 9C chooses the workspace as primary. | Makes the headline action behave like a workspace transition, while the embedded planner remains below for compatibility. |
| Watchlist, Pinned, Compare rows | Keep opening System Detail for now; consider a separate Evaluate action later. | Avoid broadening Stage 9C across every secondary surface. |
| EDDN ticker | Keep opening System Detail. | Ticker is an activity/inspection affordance, not a planning entry point. |
| Top-level `Colony Tracker` | Keep unchanged. | It is a separate local tracker workflow. |

No proposed handoff should auto-run Preview, auto-generate Suggested Builds, copy builds, or load a suggested build.

## Navigation / Back Behaviour

The workspace should be a full page inside the existing app shell, not a modal-like overlay. The persistent `NavBar` should remain visible.

Recommended first-pass navigation:

- Browser Back should work naturally because entry actions write a new hash.
- Workspace header should include `Back to Finder` as a deterministic fallback.
- Workspace header should include `Open full system detail`.
- Do not add hidden source tracking in Stage 9C. If a user came from Advanced Search Tuning, browser Back handles that path; the visible fallback can still be Finder.
- Closing the System Detail modal should continue to preserve the current parent route.

EDDN ticker can remain visible in Stage 9C for consistency with the rest of the app. If it overlaps the workspace footer or distracts on mobile, hide/collapse it in a later targeted layout pass.

Mobile should use the existing vertical planner workflow. Do not introduce complex tabs, split panes, or side rails in the first implementation.

## Workspace UI Structure

Recommended Stage 9C structure:

1. Workspace header
   - System name
   - ID64
   - coordinates
   - compact context such as economy/buildability summary when available
   - actions: Back to Finder, Open full system detail
2. Colony Planner intro
   - concise framing that this evaluates the selected system and current Build Plan
3. Main vertical workflow
   - Suggested Builds
   - Build Plan
   - Preview Result
   - Observed Evidence
   - Validation / Review Guidance

The first implementation should keep the Stage 8 vertical workflow rather than adding tabs or accordions. A side rail for system context can be deferred until the page proves stable on desktop and mobile.

## Embedded Planner Migration Plan

| option | pros | cons | risk | recommendation |
|---|---|---|---|---|
| Keep embedded planner indefinitely | Maximum compatibility; no user loses the in-modal path. | Two equally important planner surfaces could drift. | Medium | Not ideal long term. |
| Keep embedded planner for compatibility, make workspace primary | Safe migration; Evaluate actions can move to workspace while detail users still have local access. | Requires discipline to reuse components and keep copy aligned. | Low-medium | Recommended for Stage 9C. |
| Replace embedded planner with CTA only | Simplifies System Detail and reinforces workspace. | Abrupt removal; may break current detail-centric workflows. | Medium-high | Consider only after workspace stabilises. |
| Remove embedded planner | Reduces duplication. | Too disruptive and unnecessary for first implementation. | High | Not recommended. |

Recommended migration: Stage 9C keeps the embedded planner but routes primary Evaluate/Open actions to the workspace. A later stage can replace the embedded planner with a summary/CTA if the workspace is stable and tests cover the direct route.

## Test Plan For Stage 9C

Route tests:

- parse `#colony-planner/system/{id64}` into the workspace route and planner system id.
- reject invalid/missing IDs without opening the modal unexpectedly.
- preserve existing `#finder/system/{id64}`, `#search-tuning/system/{id64}`, `#optimizer/system/{id64}`, and `#system/{id64}` modal behaviour.
- closing System Detail still preserves the parent route.

Workspace tests:

- renders loading state for a valid planner route.
- renders error/retry state when system detail loading fails.
- renders system context and Colony Planner after data loads.
- does not call `simulateBuild` on load.
- does not call `fetchOptimiserCandidates` on load.
- does not copy or load any suggested build automatically.

Entry point tests:

- Finder `Evaluate in Colony Planner` navigates to `#colony-planner/system/{id64}`.
- Finder `Details` still opens System Detail with no planner workspace route.
- Search Tuning `Evaluate in Colony Planner` navigates to the workspace.
- Search Tuning row/open-detail actions still open System Detail.
- System Detail `Open Colony Planner` follows the chosen Stage 9C behaviour.

Regression tests:

- embedded planner still renders in System Detail if kept.
- full System Detail still handles close, Escape, backdrop, and focus cleanup.
- `Colony Tracker` route remains separate from `Colony Planner`.
- no auto-run, auto-generate, auto-load, scoring, ranking, or validation side effects are introduced.

## Risks And Mitigations

| risk | severity | mitigation |
|---|---|---|
| Modal and workspace state conflict | High | Keep `plannerSystemId` separate from modal `selectedSystemId`. Do not reuse the current selected-system field for workspace pages. |
| `#colony` route confusion | High | Use `#colony-planner/system/{id64}` and keep `#colony` as Colony Tracker. |
| Duplicate planner surfaces drift | Medium | Reuse `SimulationPreviewPanel` / `SimulationPreview`; do not fork planner components. |
| Back navigation expectations | Medium | Use real hash navigation, browser Back, and explicit `Back to Finder`; defer source-aware back labels. |
| System Detail remains dense | Medium | Keep workspace primary, then later consider replacing embedded planner with CTA/summary. |
| EDDN ticker overlaps focused workspace | Low-medium | Keep for first pass; audit responsive layout after implementation. |
| Mobile layout complexity | Medium | Keep vertical workflow and avoid side rails/tabs in Stage 9C. |
| Accidental auto-run/generation | High | Add tests asserting no `simulateBuild` or candidate fetch on workspace load and handoff. |
| Route parser complexity | Medium | Add focused parser tests before app-level tests. |
| Top-level navigation overcrowding | Medium | Do not add a static planner tab until there is a system chooser or recent-plans concept. |

## Recommended Stage 9C Implementation Scope

Must do:

- add `#colony-planner/system/{id64}` route support.
- keep planner workspace ID separate from System Detail modal ID.
- add `ColonyPlannerWorkspace` wrapper that reuses `useSystemDetail` and `SimulationPreviewPanel`.
- route Finder and Advanced Search Tuning `Evaluate in Colony Planner` actions to the workspace.
- keep normal Details/Open System Detail actions unchanged.
- keep embedded planner in System Detail for compatibility.
- add route, workspace, handoff, and no-auto-run/no-auto-generate tests.
- update docs and roadmap.

Should do:

- add a compact workspace header with system context.
- add `Back to Finder` and `Open full system detail` actions.
- make System Detail `Open Colony Planner` navigate to the workspace once that workspace is stable in the same Stage 9C patch.

Could do:

- add a `Show on map` action if an existing navigation helper makes it trivial.
- add a compact system-summary side rail after responsive layout is checked.
- add source-aware return labels in a later route-state pass.

Explicitly not now:

- remove the embedded planner.
- add saved builds, accounts, journals, EDMC ingestion, automatic learning, or LLM suggestions.
- change Simulation Preview scoring, CP formulas, economy/service/buildability mechanics, optimiser generation/ranking, Search Tuning scoring, Observed Evidence behaviour, or Validation behaviour.
- migrate to React Router.
- create a broad app navigation redesign.

## Final Recommendation

Implement a dedicated Colony Planner workspace in Stage 9C using `#colony-planner/system/{id64}`. Make it a full-page app-shell workspace that reuses the existing system-detail query and planner components. Move primary Evaluate/Open Colony Planner handoffs to the workspace, keep Details actions on System Detail, and keep the embedded planner until the new route has proven stable.

This gives Colony Planner the focused surface it now deserves without changing mechanics, scoring, generation, validation, or the working modal inspection path.

Stage 9C followed this recommendation, and Stage 9D hardens the route/workspace passivity tests. Deferred work remains: replacing the embedded planner with a summary/CTA, adding a top-level planner chooser or recent-plans concept, source-aware back labels, saved builds, and richer workspace side-rail context. Material/hauling planning remains explicitly deferred; ED-Finder should not duplicate RavenColonial-style hauling/material tooling unless a later product stage identifies a distinct value-add.
