# Remove Unused PlannerCanvasPreview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the confirmed-dead `PlannerCanvasPreview` component and its test file, verify nothing else in the frontend depended on it, and commit.

**Architecture:** No architecture change — this is a pure deletion. No other file is modified.

**Tech Stack:** Frontend only (Vite + React 19 + TS 5, `frontend/`).

## Global Constraints

- Delete only the two files identified in the design spec (`docs/superpowers/specs/2026-08-06-remove-unused-planner-canvas-preview-design.md`) — do not touch `economyVisuals.ts` or any of its other 8 consumers.
- All frontend verification commands (`yarn typecheck`, `yarn lint`, `yarn knip --files`, `yarn test`, `yarn build`) must be run from the `frontend/` directory and must pass before committing.

---

### Task 1: Delete PlannerCanvasPreview and verify

**Files:**
- Delete: `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx`
- Delete: `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.test.tsx`

**Interfaces:**
- Consumes: nothing (this task has no prior tasks to depend on)
- Produces: nothing (no other task depends on this one)

- [ ] **Step 1: Delete the component and its test file**

Run (from the repo root):
```bash
git rm frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx
git rm frontend/src/features/colony-planner/preview/PlannerCanvasPreview.test.tsx
```
Expected: both files staged for deletion; `frontend/src/features/colony-planner/preview/` is now empty and will disappear from git's tracked tree once committed (git does not track empty directories).

- [ ] **Step 2: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors (confirms nothing else imports the deleted component).

- [ ] **Step 3: Lint**

Run: `cd frontend && yarn lint`
Expected: passes with no errors.

- [ ] **Step 4: Knip unused-file check**

Run: `cd frontend && yarn knip --files`
Expected: passes — no new "unused export" warnings introduced (e.g. confirms `economyColor` in `economyVisuals.ts` is still considered used, since its other 8 consumers remain).

- [ ] **Step 5: Run the frontend test suite**

Run: `cd frontend && yarn test`
Expected: passes. The deleted test file's cases no longer run; no other test references `PlannerCanvasPreview`.

- [ ] **Step 6: Production build**

Run: `cd frontend && yarn build`
Expected: succeeds with no errors.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Remove unused PlannerCanvasPreview component

1417-line component with zero production consumers - only referenced
by its own test file. Confirmed no dynamic imports or routing
references it. See docs/superpowers/specs/2026-08-06-remove-unused-planner-canvas-preview-design.md
for the verification performed before this change."
```

---

## Self-Review

**Spec coverage:** The design spec's entire scope (delete both files, verify with the 5 named commands) is covered by Task 1's 7 steps. No gaps.

**Placeholder scan:** No TBD/TODO. All commands are exact and complete.

**Type consistency:** N/A — no new code, no functions/types introduced.
