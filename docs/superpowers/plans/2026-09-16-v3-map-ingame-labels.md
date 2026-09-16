# V3 Map In-Game Labels + Nearest-Star Pick — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **BEFORE STARTING (deferred plan):** rebase this branch on latest `main`, then re-open each touch-point file and **re-confirm the line numbers below** — `adapter.ts` / `SpatialCanvas.svelte` / `galaxy-labels.ts` are the concurrent map session's live files and will have drifted. Update this plan's anchors before executing.

**Goal:** Make the galaxy map behave like the in-game map — nearest-projected-star pick + labels on hover & selection — fixing the firefox spatial-pick flake at its root (SVG-anchor vs WebGL-projection disagreement).

**Design:** `docs/superpowers/specs/2026-09-16-v3-map-ingame-labels-design.md`

**Tech Stack:** SvelteKit 2 / Svelte 5 / TS, Babylon.js, Vitest, Cypress (chrome + firefox). pnpm 11, Node 24. Work in `apps/web/`.

## Global Constraints

- Work in `apps/web/`; validate with `pnpm check`, `pnpm test`, `pnpm build`, and the Cypress lanes (chrome + **firefox**). Firefox `product-journey` spatial-pick passing reliably is the acceptance signal.
- This is a **visual change** → the V3 visual/browser acceptance lane must run before promotion (CLAUDE.md).
- Preserve region-label invariants: 42 region labels always-on, never-suppressed, safe-area clamped; `data-atlas-region-leader-count` = 42.
- Keep the `selectedMarker` exact-ray clickable branch and the region-plane pick fallback.
- Do NOT regress chrome E2E while fixing firefox.

---

### Task 1: Nearest-projected-star as the primary star pick

**Files:** `apps/web/src/lib/spatial/babylon/adapter.ts` (`pickGalaxyTarget` ~1166-1230, `nearestStarTargetByScreen` ~1124-1164); test `apps/web/src/lib/spatial/babylon/adapter.test.ts` (currently no pick coverage — add it).

**Change:** In `pickGalaxyTarget`, resolve the nearest projected star (via `nearestStarTargetByScreen`) as the **primary** star result, before relying on the exact ray for star selection. Keep: (a) the `selectedMarker` exact-ray branch so the selected torus stays clickable; (b) the region-plane pick as the final fallback. Enable nearest-star for hover too (Task 2).

- [ ] **Step 1 (TDD):** Add a unit test for `pickGalaxyTarget` (extract/export it or test via the runtime command path as `camera-session.test.ts:592-599` does with a fake scene): given two projected stars where the exact ray would hit the farther one but the nearer projects closer to the cursor, assert the **nearer** system is returned. Run → fails (current order returns the ray hit).
- [ ] **Step 2:** Reorder `pickGalaxyTarget`: compute `nearestStarTargetByScreen(...)` first (always, not gated on `allowNearestStar`); if it returns a system, return it; else keep selected-marker/exact-ray/region logic. Re-run → passes.
- [ ] **Step 3:** Verify no chrome regression: `pnpm test` green. Commit: `feat(map): nearest-projected-star is the primary galaxy pick`.

### Task 2: Hover reveals a system label

**Files:** `adapter.ts` HOVER branch (~2116-2149), `SpatialCanvas.svelte` (`TARGET_HOVERED` ~670-672, label derivation ~165-188), `galaxy-labels.ts` (`galaxyLabelCandidates` ~139-180); tests `SpatialCanvas.test.ts` (~330-336 mirror region-hover), `galaxy-labels.test.ts` (~81-104).

- [ ] **Step 1:** HOVER branch passes `allowNearestStar=true` to `pickGalaxyTarget` so hovering resolves the nearest system.
- [ ] **Step 2 (TDD):** In `SpatialCanvas.svelte`, add `lastHoveredSystemId64` set from `TARGET_HOVERED` (`target.kind==='system'`), surfaced as `data-last-hovered-system-id64` (mirror `data-last-hovered-region-id`). Add a unit test injecting a `TARGET_HOVERED` system event and asserting the attribute + that a hovered-system label renders.
- [ ] **Step 3:** `galaxyLabelCandidates` accepts a `hoveredSystemId64` and adds it as a candidate (`hovered:true`, priority ~900), alongside selected. `SpatialCanvas` passes `lastHoveredSystemId64` in. Update `galaxy-labels.test.ts` for a hovered-system candidate. Run → green.
- [ ] **Step 4:** Commit: `feat(map): show a system label on hover`.

### Task 3: Expose star projected position; rework E2E off label anchors

**Files:** `SpatialCanvas.svelte` (emit `data-star-screen-x/y` for the hovered/selected star, using the same Babylon projection the pick uses — surfaced from the adapter, not the SVG `projectGalaxyLabel`), `adapter.ts` (expose projected screen position of a system); tests `product-journey.cy.ts` (~151-169), `map-review-lab.cy.ts` (~99-101).

- [ ] **Step 1:** Add an adapter path that returns a system's Babylon-projected screen position (same projection as `nearestStarTargetByScreen`), and surface it in the DOM as `data-star-screen-x/y` for the current hovered/selected star.
- [ ] **Step 2:** Rework `product-journey.cy.ts`: instead of clicking `data-map-label-anchor-*`, hover the target star (assert its hover label appears), read `data-star-screen-x/y`, click there, assert `data-last-picked-id64` = target. This removes the SVG-vs-WebGL mismatch that was the firefox root cause.
- [ ] **Step 3:** Reconcile `map-review-lab.cy.ts:99-101` (3 system labels) with the hover+selection model — ensure the fixture selects/hovers to produce the expected labels, or update the assertion.
- [ ] **Step 4:** `pnpm check && pnpm test && pnpm build`; commit: `test(map): pick stars by projected position, not label anchor`.

### Task 4: Full validation (chrome + firefox + visual)

- [ ] **Step 1:** Run Cypress chrome + firefox locally if possible; otherwise rely on CI. The firefox `product-journey` spatial-pick MUST pass reliably (run it multiple times / confirm no retry-exhaustion).
- [ ] **Step 2:** Trigger the V3 visual/browser acceptance lane (visual change). Capture evidence.
- [ ] **Step 3:** Open the PR; iterate on CI firefox E2E until green (this is where the real proof lives — expect iteration). Ensure chrome E2E and unit lanes stay green.

---

## Self-Review

- **Spec coverage:** nearest-star primary (Task 1), hover labels (Task 2), projection-mismatch removal via `data-star-screen-*` + E2E rework (Task 3), validation incl. visual (Task 4). Selection labels + region invariants preserved (untouched).
- **Deferred-plan caveat:** all line anchors WILL drift — re-confirm after rebasing on `main` before executing. The concurrent map session owns these files; coordinate/rebase.
- **Verification reality:** firefox WebGL pick precision is only provable in CI; plan for an iterate-on-CI loop rather than a one-shot local pass.
