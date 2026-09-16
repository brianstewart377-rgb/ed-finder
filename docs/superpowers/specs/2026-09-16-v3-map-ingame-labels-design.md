# V3 Galaxy Map — In-Game-Style Labels + Nearest-Star Pick — Design

**Date:** 2026-09-16
**Status:** design, pending implementation (deferred to a fresh session)
**Branch:** `feat/v3-map-ingame-labels`
**Motivation:** A firefox E2E flake (`product-journey.cy.ts:168` — clicking a system's label anchor picks a *neighbour* star) surfaced two real map issues; the fix is to make the map behave like the Elite Dangerous in-game map.

## Root cause (from systematic-debugging investigation)

The E2E test clicks a system's **SVG label anchor** as a proxy for clicking the star, then asserts the spatial pick selected that system. In firefox it picks a neighbour because:

1. **The pick isn't nearest-star-first.** `pickGalaxyTarget` (`apps/web/src/lib/spatial/babylon/adapter.ts:1166-1230`) leads with an exact Babylon ray (`scene.pick` on `starMesh`), which can hit a background/overlapping star or narrowly miss; only *then* does it fall back to nearest-projected-star within 12px (and only when `allowNearestStar`, which PICK passes but HOVER does not).
2. **Two projections disagree.** The label anchor is projected by a *manual* camera-basis projection in `galaxy-labels.ts` `projectGalaxyLabel()` (CSS px); the pick uses Babylon's `Vector3.ProjectToRef` against the render viewport. In firefox these can disagree enough that clicking the SVG anchor lands nearer a different star.

This is **not** caused by Finder F2a or map PR #735 (verified — #735 only regenerated API types). It is pre-existing map-interaction code.

## What already exists (don't rebuild)

- System labels are **already selection-gated** — `galaxyLabelCandidates()` (`galaxy-labels.ts:139-180`) filters to the current selection set, budgeted to 8 (`DEFAULT_MAXIMUM_SYSTEM_LABELS`). There are **no** always-on system labels today. Region labels (42) are always-on and stay.
- The selected system already has a distinct 3D marker (`createSelectedSystemMarker()`, `adapter.ts:800-825`).
- The adapter can already resolve a hovered *system* via the exact-ray branch and emits it in `TARGET_HOVERED`, but the Svelte side discards it (`SpatialCanvas.svelte:670-672` keeps only region ids), and hover never uses nearest-star.

## Decisions (in-game behaviour)

1. **Nearest-projected-star is the PRIMARY star pick.** Reorder `pickGalaxyTarget` so nearest-projected-star (Babylon projection) resolves a star before the exact ray is used for star selection — keep the `selectedMarker` exact-ray branch so the selected torus stays clickable, and keep the region-plane fallback last. Enable nearest-star for **both** PICK and HOVER. This is the in-game "click near a star → select that star" behaviour and fixes the wrong-pick.
2. **Labels on HOVER + SELECTION.** Hovering a star shows its label; the selected system keeps its label (unchanged). Regions unchanged. No always-on system labels (already the case).
3. **Remove the SVG-vs-WebGL test coupling.** Expose each rendered star's **Babylon-projected** screen position via a data attribute (e.g. `data-star-screen-x/y` on a per-selected/hovered marker, or a small projected-point map) so E2E clicks the star where the *pick* projects it — eliminating the projection-disagreement root cause. Tests stop clicking SVG label anchors.

## Architecture / touch-points

### `apps/web/src/lib/spatial/babylon/adapter.ts`
- `pickGalaxyTarget` (1166-1230): make `nearestStarTargetByScreen` primary for star resolution; preserve selected-marker branch (1186-1193) and region fallback (1216-1229). Consider widening/confirming the tolerance (`12 * max(scale)`).
- HOVER branch (2116-2149): pass `allowNearestStar=true` so hovering resolves the nearest system, not only an exact ray hit.
- Add a way to read a system's projected screen position for tests (new data path).

### `apps/web/src/lib/spatial/SpatialCanvas.svelte`
- `TARGET_HOVERED` subscription (670-672): add `lastHoveredSystemId64` (currently only `lastHoveredRegionId`), surface as a `data-*` attr for tests, mirror the `data-last-hovered-region-id` hook pattern.
- Label derivation (165-188): pass the hovered system into `galaxyLabelCandidates`.
- Emit `data-star-screen-x/y` (or equivalent) for the hovered/selected star.

### `apps/web/src/lib/spatial/galaxy-labels.ts`
- `galaxyLabelCandidates` (139-180): add the **hovered system** as a candidate (currently `hovered:false` hardcoded for systems), priority ~900 like regions; keep the selected + budget gates.

### Tests to rework
- `apps/web/cypress/e2e/product-journey.cy.ts` (151-169): stop clicking `data-map-label-anchor-*`; click the star's projected position via the new attribute; add a hover-shows-label assertion.
- `apps/web/cypress/e2e/map-review-lab.cy.ts` (99-101): the "3 system labels" assertion depends on the fixture selecting 3 systems — confirm/rework under hover+selection.
- `apps/web/src/lib/spatial/SpatialCanvas.test.ts` (468-484, 330-336): add hovered-system-label coverage mirroring the region-hover test; keep selected-label coverage.
- `apps/web/src/lib/spatial/galaxy-labels.test.ts` (81-104): add a hovered-system candidate case.
- `adapter.ts` pick/hover currently have **no** unit coverage — add nearest-star-primary unit tests.

## Validation

- **Unit:** `pnpm test` (Vitest) — new nearest-star-primary + hovered-system-label tests.
- **E2E:** `pnpm cypress` chrome + **firefox** (the firefox `product-journey` spatial-pick must pass reliably — the whole point).
- **Visual acceptance:** this changes visible map interaction (hover labels) — run the V3 visual/browser acceptance lane per CLAUDE.md before promotion.

## Risks / coordination

- `adapter.ts` / `SpatialCanvas.svelte` / `galaxy-labels.ts` are the **concurrent map session's live files** (many recent commits: #733 firefox flake fixes, starfield shaping). Execute after that work settles; rebase on latest `main` at implementation time and re-confirm the line references above (they will drift).
- Firefox WebGL pick precision can't be verified locally — CI E2E is the proof; expect an iterate-on-CI loop.
- Keep region-label invariants (never-suppress, 42 count, safe-area) intact.

## Out of scope

- Finder F2b/F2c (archetype builder + ranking) — separate track; F2a already merged.
- Broader map visual redesign beyond labels + pick.
