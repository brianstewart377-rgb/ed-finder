# Stage 20D - Planner Sequence And CP Curve Cockpit

## Purpose

Stage 20D turns build order and CP tradeoffs into a dedicated planner cockpit
instead of leaving them implicit inside preview output.

This checkpoint remains explicit and manual:

- no automatic Preview execution;
- no hidden Build Plan mutation from sequence review;
- no automatic Suggested Build loading;
- no DB writes;
- no Stage 19 operator execution;
- no canonical apply, rebaseline, or scheduler activation.

## Delivered Cockpit

Stage 20D delivers:

- a dedicated `Sequence` workspace mode in the planner shell;
- a `SequenceCockpitWorkspaceView` that makes build order explicit from current
  placements;
- direct reuse of the existing `CpSummary`, `CpTimelinePanel`, and
  `CpRepairPanel` components after explicit Preview runs;
- stale-preview guidance that tells the user when CP data must be refreshed.

## Ownership

Frontend ownership is now explicit:

- workspace mode registry:
  `frontend/src/features/system-detail/simulation-preview/WorkspaceModeTabs.tsx`
- planner shell integration:
  `frontend/src/features/system-detail/simulation-preview/SimulationPreview.tsx`
- sequence cockpit:
  `frontend/src/features/system-detail/simulation-preview/SequenceCockpitWorkspaceView.tsx`
- CP summary and timeline primitives:
  `frontend/src/features/system-detail/simulation-preview/panels/CpSummary.tsx`
  `frontend/src/features/system-detail/simulation-preview/panels/CpTimelinePanel.tsx`
  `frontend/src/features/system-detail/simulation-preview/panels/CpRepairPanel.tsx`

## Read-only Boundaries

The Stage 20D cockpit preserves:

- manual Run Preview as the only way to refresh CP metrics;
- build-order visibility without implicit resequencing;
- stale-preview warnings when placements change after a run;
- no hidden scoring changes or role mechanics;
- no DB writes or production-like execution.

## Planner Tradeoff Surface

The cockpit now makes these planner questions visible:

- what the current build order is;
- which body each placement targets;
- whether a placement is the primary port;
- the current CP summary after Preview;
- the CP timeline across early steps;
- structured repair suggestions when the CP curve is weak.

## Non-goals Preserved

Stage 20D does not yet deliver:

- auto-apply repair suggestions;
- drag-and-drop sequence editing in the cockpit;
- map-to-sequence coupling;
- body-slot mutation from sequence review;
- automatic preview refresh.

## Next Checkpoint

The next checkpoint remains:

`Stage 20E - Export/operator pack and closeout readiness`

