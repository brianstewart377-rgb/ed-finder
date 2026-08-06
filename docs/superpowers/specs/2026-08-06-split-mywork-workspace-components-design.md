# Split MyWorkWorkspace.tsx Into Component Files — Design

## Context

`frontend/src/features/my-work/MyWorkWorkspace.tsx` is 1098 lines. It is item 3
of the ongoing code-splitting refactor series (item 1: `PlannerCanvasPreview.tsx`
removal, PR #419; item 2: `api.ts` domain-module split, PR #420).

The file already has clean internal boundaries: one orchestrator component
(`MyWorkWorkspace`, the only exported symbol) plus seven module-private
subcomponents/helpers that the orchestrator's JSX composes:

- `ContinueWhereLeftOff` (lines 632-681, ~50 lines) — presentational, used once
- `SavedSystemCard` (683-791, ~109 lines) — presentational, used once (`.map()`
  over `filteredSavedSystems`); internally uses `LabelToggle`
- `LabelToggle` (942-959, ~18 lines) — tiny, used only by `SavedSystemCard`
  (3 call sites)
- `PlanCard` (793-940, ~148 lines) — presentational, used once (`.map()` over
  grouped plans)
- `EmptyPanel` (961-968, ~8 lines) — tiny shared empty-state, used 4x directly
  in the orchestrator's JSX (saved-systems, plans, expansion-plans, my-colonies
  tabs)
- `TelemetrySection` (970-1082, ~113 lines) — presentational, used once (the
  telemetry tab); internally uses `MetricCard` and `formatCompactEventCounts`
- `MetricCard` (1084-1092, ~9 lines) — tiny, used only by `TelemetrySection`
  (4 call sites)
- `formatCompactEventCounts` (1094-1098, ~5 lines) — tiny, used only by
  `TelemetrySection` (2 call sites)

None of these seven are exported today, so nothing outside this file can
import them directly. Confirmed via grep: only two other files reference
`MyWorkWorkspace` at all — `App.tsx` (renders it) and
`MyWorkWorkspace.test.tsx` (renders it black-box via `import { MyWorkWorkspace
} from './MyWorkWorkspace'`, mocks only the already-separate
`useJournalTelemetrySummary` hook). Neither imports any of the seven
subcomponents by name.

## Decision

Extract the five composition-boundary units (`ContinueWhereLeftOff`,
`SavedSystemCard`, `PlanCard`, `EmptyPanel`, `TelemetrySection`) into their own
files under a new `frontend/src/features/my-work/components/` subfolder. Each
extracted file exports its one named component. `LabelToggle` moves with
`SavedSystemCard` and `MetricCard`/`formatCompactEventCounts` move with
`TelemetrySection`, as private (non-exported) helpers in the same file as
their sole consumer — they are not reused anywhere else, so giving them their
own files would add navigation overhead with no benefit.

`MyWorkWorkspace.tsx` stays at its current path (so `App.tsx`'s import is
unaffected) and keeps the orchestrator: all `useState`/store-subscription/
`useMemo` data plumbing, all event handlers, and the top-level JSX that
switches on `activeSection` and renders the extracted components. It shrinks
from 1098 lines to roughly 570.

**No barrel `index.ts`.** `MyWorkWorkspace.tsx` imports each component
directly from its own file path (e.g. `./components/SavedSystemCard`). Item 2
(`api.ts`) hit a real bug where TypeScript resolved an old flat file ahead of
a new barrel's `index.ts` and silently shadowed it; a barrel here is
unnecessary (nothing outside `MyWorkWorkspace.tsx` needs these components) so
this design has zero exposure to that failure class.

**No logic changes.** Every extracted component's JSX, props, and internal
logic move verbatim. No prop shape changes. No new abstractions.

## File Structure

```
frontend/src/features/my-work/
  MyWorkWorkspace.tsx                    (orchestrator; shrinks ~1098 -> ~570 lines)
  components/
    ContinueWhereLeftOff.tsx             (new, ~55 lines incl. imports/types)
    SavedSystemCard.tsx                  (new, ~135 lines incl. LabelToggle)
    PlanCard.tsx                         (new, ~150 lines incl. imports/types)
    EmptyPanel.tsx                       (new, ~12 lines)
    TelemetrySection.tsx                 (new, ~165 lines incl. MetricCard,
                                           formatCompactEventCounts)
  myWorkStore.ts                          (untouched)
  myWorkWorkspaceUtils.ts                 (untouched)
  expansionPlanStatus.ts                  (untouched)
  useJournalTelemetrySummary.ts           (untouched)
  MyWorkWorkspace.test.tsx                (untouched — black-box render test,
                                            no internal imports to update)
```

## Verification

Same safety net as item 2: `yarn typecheck`, `yarn lint`, `yarn knip --files`,
`yarn test`, `yarn build`, then a manual browser smoke check of My Work's five
tabs (saved systems, plans, expansion plans, my colonies, telemetry) against a
live local dev server + local API, confirming no new console errors and that
each tab still renders and its actions (toggle labels, rename/duplicate/
archive a plan, rename/archive an expansion plan, inspect system) still work.

## Out of scope

- `myWorkWorkspaceUtils.ts`, `myWorkStore.ts`, `expansionPlanStatus.ts`,
  `useJournalTelemetrySummary.ts` are untouched — they were not named as
  separate targets in the original code-splitting review, and are already
  reasonably sized single-purpose files.
- No behavior, styling, or copy changes.
