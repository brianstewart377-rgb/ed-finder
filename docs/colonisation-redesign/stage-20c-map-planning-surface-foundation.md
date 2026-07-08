# Stage 20C - Map Planning Surface Foundation

## Purpose

Stage 20C establishes the planner-facing map foundation by reusing the current
map primitives inside the Simulation Preview workspace rather than creating a
parallel renderer or a separate planner shell.

This checkpoint remains read-only. It does not authorize planner mutation from
map interaction, DB writes, Stage 19 operator commands, canonical apply,
rebaseline, scheduler activation, or production-like DB execution.

## Delivered Foundation

Stage 20C delivers:

- a dedicated `Map` workspace mode in the planner shell;
- a `MapFoundationWorkspaceView` that reuses the current `MapTab`;
- timeline-layer ownership in `MapTab` using the existing `useMapLayers`
  contract;
- explicit guidance that map interaction is contextual only and does not change
  Build Plan, Evidence, Validation, or deferred Stage 19 lanes.

## Ownership

The current map foundation now has explicit frontend ownership:

- workspace mode and planner shell routing:
  `frontend/src/features/system-detail/simulation-preview/WorkspaceModeTabs.tsx`
  `frontend/src/features/system-detail/simulation-preview/SimulationPreview.tsx`
- planner map foundation view:
  `frontend/src/features/system-detail/simulation-preview/MapFoundationWorkspaceView.tsx`
- shared map surface:
  `frontend/src/features/map/MapTab.tsx`
  `frontend/src/features/map/GalacticMap.tsx`
  `frontend/src/features/map/useMapLayers.ts`

## Read-only Boundaries

The Stage 20C map foundation explicitly preserves:

- no Build Plan mutation from selection, pan, zoom, or layer toggles;
- no automatic Preview execution;
- no automatic Suggested Build generation or loading;
- no Evidence or Validation state mutation;
- no DB writes;
- no Stage 19 operator execution;
- no canonical apply, rebaseline, or scheduler/service enablement.

## Timeline Foundation

`MapTab` now exposes a bounded timeline layer toggle and bucket selector. The
timeline summary is informational only and prepares the map architecture for a
future scrubber without coupling it to planner mechanics.

Supported Stage 20C buckets:

- `month`
- `quarter`
- `year`

## Performance Foundation

Stage 20C reuses the current `useMapLayers` query ownership rather than adding
new fetch paths. Layer queries remain independent and lazily enabled, which
keeps the planner map foundation bounded to:

- regions;
- heatmap;
- clusters;
- timeline.

## Non-goals Preserved

Stage 20C does not yet deliver:

- planner overlays that mutate or author Build Plan state;
- map-side body-slot editing;
- route-based map persistence;
- a new renderer;
- high-volume live backend map aggregation changes.

## Next Checkpoint

The next checkpoint remains:

`Stage 20D - Planner sequence and CP curve cockpit`

