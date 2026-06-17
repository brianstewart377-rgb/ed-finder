# Stage 18H.4 — Warehouse Evidence UX Clarification

## Purpose

Stage 18H.4 keeps the existing read-only warehouse evidence card but makes its
status posture clearer to the operator:

- freshness is explicit
- review status is explicit
- source posture is explicit
- source run identifiers and warnings are visible when available

This is a presentation-only slice. It does not change planner truth, fetch new
data, or authorize any mutation path.

## UX Changes

The planner warehouse evidence card now renders:

1. a freshness badge: `Fresh`, `Stale`, or `Unknown freshness`
2. a source-posture badge:
   - `Dedicated contract`
   - `Provenance fallback`
   - `Unknown source path`
3. a review-status line:
   - `Passive review only`
   - `Manual review required`
4. a source-run line when source metadata is available
5. up to two warnings when the contract or fallback path surfaces them

## Boundaries Preserved

This slice still does **not**:

- add buttons or interactive controls
- promote warehouse evidence into canonical planner truth
- change the planner's write boundary
- add admin-only metadata
- authorize Stage 19 production activation or any canonical apply work

## Files

The UX clarification is implemented in:

- `frontend-v2/src/features/colony-planner/WarehouseEvidenceCard.tsx`
- `frontend-v2/src/features/colony-planner/WarehouseEvidenceCard.test.tsx`
- `frontend-v2/src/features/colony-planner/warehouseEvidenceBridge.ts`
- `frontend-v2/src/types/api.ts`

## Next Roadmap Position

With Stage 18H.1 through 18H.4 complete, the next meaningful warehouse/canonical
follow-on remains Stage 18I — Canonical Write Design Review, which is still a
documentation-only checkpoint and does **not** authorize writes.
