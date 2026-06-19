# Stage 24B - Planner Evidence Discoverability Surfaces

## Status

Stage 24B is complete.

This checkpoint implements the first narrow read-only adoption slice defined by
the Stage 24A contract.

## Scope

Stage 24B stays inside the in-scope Stage 24A surfaces:

- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- `frontend-v2/src/features/colony-planner/WarehouseEvidenceCard.tsx`
- `frontend-v2/src/features/colony-planner/warehouseEvidenceBridge.ts`
- `frontend-v2/src/types/api.ts`
- documentation/readme discoverability for the read-only evidence baseline

The delivered slice keeps the existing endpoint path and backend behavior while
making the planner evidence posture easier to find and interpret in the
existing planner workspace.

## Delivered discoverability changes

Stage 24B adds or clarifies:

- a dedicated read-only evidence-posture wrapper in the primary planner
  workspace;
- a more visible summary of selected-system evidence status;
- clearer scanability for source classes and source semantics;
- more obvious report-only, selected-system-only, non-canonical, and
  non-full-coverage posture;
- preserved bounded staging row-cap context inside the evidence card.

## Preserved Stage 24A contract boundary

Stage 24B follows the Stage 24A contract:

- the dedicated endpoint remains preferred when it responds;
- provenance fallback remains fallback-only for dedicated-endpoint read failure;
- the read-only evidence baseline remains selected-system context only;
- bounded staging remains report-only;
- bounded staging remains not canonical truth;
- bounded staging remains not full EDSM coverage.

## User-visible outcome

Users can now find the planner evidence posture more easily in the primary
planner workspace.

The evidence surface now makes it easier to scan:

- current evidence status;
- report-only posture;
- selected-system-only posture;
- source classes;
- source semantics;
- bounded staging limits when present.

## Stable wording preserved

Stage 24B keeps the Stage 24A language contract intact:

- `Available. Selected-system evidence is present as read-only review context only.`
- `Unavailable. No approved bounded staging evidence is linked to this selected system.`
- `Not evaluated in this runtime. The staging boundary was not safely queryable for this request.`
- `Unknown. Selected-system evidence has not been established.`
- `Bounded staging evidence`
- `Report-only review context`
- `Not canonical truth`
- `Not full EDSM coverage`
- `Limited to approved Stage 19BB row-cap evidence`

## Stage 24C remains future work

Stage 24B does not implement Stage 24C.

The following remain candidate Stage 24C surfaces:

- system-detail review surfaces;
- simulation and export-readiness surfaces;
- adjacent API consumers;
- cross-surface provenance fallback consistency guidance.

## Boundaries

Stage 23 remains closed.

Stage 19 remains separately gated.

This checkpoint does not:

- rerun Stage 19BB;
- create any new Stage 19 execution lane;
- perform DB writes;
- perform canonical apply;
- perform rebaseline;
- enable scheduler, service, or timer activation;
- introduce source acquisition;
- commit source files;
- commit runtime artifacts;
- broaden into cross-product redesign.

## Outcome

Stage 24 now has:

- Stage 24 planning baseline;
- Stage 24A implementation contract;
- Stage 24B primary planner discoverability surfaces.

The next follow-on can stay focused on Stage 24C cross-surface consistency
rather than redefining the planner-evidence contract again.
