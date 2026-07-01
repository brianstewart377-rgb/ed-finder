# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Implementing**

## Current branch and baseline

- Branch: `feat/r1-lab-entry-boundary`
- Base branch: `work/r1-canonical-body-evidence`
- Base commit: `f1f6cb4a8f78a484d514f8153d6e7093602458bd`
- Goal: Stage 1 DEV-only R1 Assessment Laboratory entry boundary and inert shell

## Allowed files

### Product / test files

- `frontend-v2/src/App.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/AppEntryIsolation.test.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabRoute.test.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/noNetwork.test.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/sourceBoundary.test.ts`

### Control-file exception

- `docs/ai/CURRENT_STAGE.md`

No other product, test, route, config, provider, store, API, workflow, or deployment files are authorised in this stage.

## Fixed Stage 1 scope

Stage 1 is only the DEV-only laboratory entry boundary and an inert reconstruction shell.

It does **not** recreate:

- fixtures;
- templates;
- evaluation logic;
- carrier comparison;
- evidence snapshots;
- digests;
- strategies;
- Plan Fit;
- reports;
- exports;
- final lab UI beyond the inert shell;
- invented assessment results.

## Explicit non-goals

- Do not modify `frontend-v2/src/main.tsx`.
- Do not modify `frontend-v2/src/hooks/useHashRoute.ts`.
- Do not add the lab hash to route enums or valid-route lists.
- Do not modify normal navigation, production routing, app stores, API code, or configuration.
- Do not add fixtures, scoring, assessment states, carrier modes, Plan Fit, reports, exports, or invented results.
- Do not add any files outside the allowed file list.

## Required evidence before Stage 1 can be accepted

- exact branch name and full current commit SHA;
- lab-entry tests;
- typecheck;
- production build;
- production artifact scan over deployable JS, CSS, and HTML for:
  - `r1-assessment-lab`
  - `R1 Assessment Laboratory`
  - `DEV only — reconstruction shell`
  - `No production scoring`
  - `No network or persistence`
  - `Assessment engine not yet reconstructed`
  - `R1AssessmentLabApp`
- `git status --short`;
- `git diff --stat`;
- `git diff --name-status`;
- `git diff --check`;
- `git diff --cached --check`.

## Stage 1 acceptance contract

- Production normal root owns QueryClientProvider, React Query devtools, and the ordinary app tree.
- Only inside a compile-time `import.meta.env.DEV` branch:
  - define the exact `#r1-assessment-lab` hash;
  - define the DEV-only hash listener/state;
  - define the lazy lab component and dynamic import;
  - render the lab outside the normal root when the exact hash matches;
  - otherwise render the normal root.
- Production must render only the normal root.
- No conditional React hooks inside a component body.
- The exact DEV lab hash must not mount the normal provider/bootstrap tree.
- Production must treat `#r1-assessment-lab` as an ordinary unknown hash and fall back to Finder.

## Last verified state

- Continuity baseline merged into `work/r1-canonical-body-evidence` before this stage.
- New implementation branch created from `f1f6cb4a8f78a484d514f8153d6e7093602458bd`.
- Frontend root: `frontend-v2`.
- No `frontend-v2/src/lab/r1-assessment-lab` directory exists before Stage 1 implementation.

## Next safe action

Implement only the Stage 1 DEV-only R1 Assessment Laboratory entry boundary and inert shell inside the six authorised product/test files, then gather the required evidence before any further stage is considered.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
