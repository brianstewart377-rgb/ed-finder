# Stage 18H.3 — Planner Warehouse Fetch with Provenance Fallback

## Purpose

Stage 18H.3 moves the planner to the dedicated
`warehouse_planner_evidence/v1` endpoint added in Stage 18H.2 while preserving
the existing Stage 18H provenance cockpit bridge as a strict fallback.

This means the planner now prefers the dedicated contract when it is safely
available, but does **not** lose the earlier read-only warehouse surface when
the dedicated endpoint returns `unavailable` or cannot be read.

## Planner Flow

The Colony Planner workspace now:

1. requests `GET /api/colony-planner/system/{id64}/warehouse-planner-evidence`
2. maps a non-`unavailable` contract response directly into the existing
   planner read-only warehouse card
3. falls back to the current provenance cockpit warehouse bridge when the
   dedicated endpoint returns `availability = "unavailable"` or errors

## Boundaries Preserved

This slice still does **not**:

- mutate planner truth
- promote warehouse evidence to canonical status
- authorize writes, apply lanes, rebaseline, or scheduler work
- expose admin-only warehouse details
- change the planner card into an interactive control surface

The card remains read-only and report-only, with the same conservative source
labels used in earlier Stage 18H work.

## Delivered Files

The fetch/fallback integration is implemented in:

- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- `frontend-v2/src/features/colony-planner/warehouseEvidenceBridge.ts`

Focused workspace tests cover both:

- the dedicated endpoint path
- the fallback-to-provenance path

## Follow-on

The next slice is Stage 18H.4: clarify freshness, review status, and source
posture in the planner UX now that the dedicated endpoint path is live.
