# Remove unused PlannerCanvasPreview — Design

**Goal:** Delete `PlannerCanvasPreview.tsx`, a confirmed-dead 1417-line component, and its test file, as the first (lowest-risk) item in working through the 2026-08-05 Codex code-splitting review.

**Context:** A static code-splitting review (Codex, read-only, 2026-08-05) flagged `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx` as having no consumers anywhere under `frontend/src`, with a note to verify it isn't dynamically loaded before acting. The review identified roughly seven largely-independent refactoring targets across the backend importer, EDDN listener, operator scripts, grid builder, frontend map rendering, API models, and the frontend API client, plus a couple of standalone quick wins — too broad for one design, so this is being worked as separate sub-projects. This is the first.

## Verification performed (2026-08-06)

- `grep` across all of `frontend/src` for `PlannerCanvasPreview` (both `import` and the bare component name, to catch dynamic references) found only:
  - Its own definition (`PlannerCanvasPreview.tsx:528`)
  - Its own test file (`PlannerCanvasPreview.test.tsx`, 19 references, all `render(<PlannerCanvasPreview />)` calls inside the test's own describe block)
  - No route registrations, no barrel-file re-exports, no dynamic `import()` calls referencing it.
- `frontend/src/features/colony-planner/preview/` contains exactly these two files — nothing else. Removing them removes the directory entirely.
- The component's only external dependency, `economyColor` from `../economyVisuals`, is used by 8 other live files (`stationBaselineEconomy.ts`, `planningEconomy.ts`, `SystemBuildMapCanvas.tsx`, `PlanningEconomyStrip.tsx`, `ProjectedStructureSlot.tsx`, `BodyStructureSlot.tsx`, and two test files) — it stays untouched.
- No separate mock-data file exists to clean up alongside it; sample/demo data is defined inline within the component file itself, so deleting the file removes it all.
- This is a distinct, dead prototype surface — not a duplicate of the *live* embedded planner at `frontend/src/features/system-detail/simulation-preview/` (the actual in-use preview surface per `CLAUDE.md`'s architecture notes). Nothing currently reachable from the app renders `PlannerCanvasPreview`.
- `yarn knip --files` (the CI-gated unused-file check) has not been flagging this file, most likely because `PlannerCanvasPreview.test.tsx` importing it satisfies knip's reachability graph even though no *production* code path does — a known category of knip blind spot (test-only reachability), not a sign the file is actually live.

## Decision

Delete outright, rather than relocate to Storybook/documentation. Nothing currently depends on it, there's no indication it's slated for near-term reuse, and this codebase has no existing Storybook setup to relocate it into (introducing one would be new infrastructure, out of scope for a dead-code removal).

## Change

- Delete `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx`
- Delete `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.test.tsx`
- Directory `frontend/src/features/colony-planner/preview/` is removed as a result (now empty)

## Verification after deletion

- `yarn typecheck` — confirms nothing else in the frontend referenced it
- `yarn lint` — clean
- `yarn knip --files` — confirms no new unused-import warnings surface elsewhere (e.g. in `economyVisuals.ts` if `PlannerCanvasPreview` had been its only external-to-the-module consumer of some export — already ruled out above, but knip is the automated backstop)
- `yarn test` — full suite still passes with the test file gone (no other test references `PlannerCanvasPreview`)
- `yarn build` — production build still succeeds

## Out of scope

- The other six-plus items from the code-splitting review (`import_spansh.py`, EDDN batching, operator script duplication, `build_grid.py`, `R3FMapFoundation.tsx`, `models.py`/`evidence_store`, `api.ts`, `MyWorkWorkspace.tsx`) — each gets its own design/plan cycle, prioritized separately.
