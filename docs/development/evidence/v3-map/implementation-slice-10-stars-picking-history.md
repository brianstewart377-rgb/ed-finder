# Implementation slice 10 — catalogue stars, stellar icons, picking and travel history

**Date:** 2026-09-14
**Status:** implemented candidate; browser release-head validation pending

## Delivered

- Explore streams bounded real catalogue systems from `/api/map/systems` using
  the camera's exact 3-D light-year bounds.
- Individual-star budgets descend from 40,000 at the widest star range to 1,800
  in the closest range; the whole-Galaxy view retains the real density layer.
- Stable, tested presentation covers the complete owner-supplied star-family
  legend, including black-hole rings and an unknown fallback.
- Thin-instance translation matrices retain catalogue coordinates exactly;
  icon colour, halo and relative size are presentation only.
- Clicking a star selects its lossless Id64 and opens its facts/actions card.
- The Commander History toggle calls `/api/exploration/viewport-visits` with the
  local sync key and renders only journal-derived visit markers/cells in a
  separate `COMMANDER_HISTORY` contribution.

## Truth boundary

The star layer is catalogue truth, not generated occupancy. The travel heatmap
is personal derived history and is not the known-systems density layer. A
truncated endpoint result remains visibly bounded; no synthetic points fill it.

## Evidence

Focused tests cover camera budgets, lossless mapping, icon classification,
exact Babylon instance positions, non-pickable journal heat geometry and layer
receipts. Product E2E assertions cover the star information card and history
toggle. The normal release-head browser matrix is still required for acceptance.
