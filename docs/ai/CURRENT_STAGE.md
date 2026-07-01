# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Accepted — merge pending**

## Current branch and baseline

- Branch: `feat/r1-lab-entry-boundary`
- Base branch: `work/r1-canonical-body-evidence`
- Base commit: `f1f6cb4a8f78a484d514f8153d6e7093602458bd`
- Goal: Stage 1 DEV-only R1 Assessment Laboratory entry boundary and inert shell
- Stage 1 implementation commit: `1800390a915918e9d82ca16d8aef8aa0ac35be42`
- Stage 1 correction implementation commit: `2f798006c0fc902432ce822588866130542c390b`

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

## Actual evidence

- Branch: `feat/r1-lab-entry-boundary`
- Current implementation commit: `2f798006c0fc902432ce822588866130542c390b`
- Review PR: `#277`
- Stage 1 lab tests:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" vitest run "src/lab/r1-assessment-lab/AppEntryIsolation.test.tsx" "src/lab/r1-assessment-lab/R1AssessmentLabRoute.test.tsx" "src/lab/r1-assessment-lab/noNetwork.test.tsx" "src/lab/r1-assessment-lab/sourceBoundary.test.ts"`
  - Result: `4 passed, 9 tests passed`
- Typecheck:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" typecheck`
  - Result: passed
- Production build:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" build`
  - Result: passed
- Production artifact scan over deployable JS/CSS/HTML:
  - `r1-assessment-lab` → no matches
  - `R1 Assessment Laboratory` → no matches
  - `DEV only — reconstruction shell` → no matches
  - `No production scoring` → no matches
  - `No network or persistence` → no matches
  - `Assessment engine not yet reconstructed` → no matches
  - `R1AssessmentLabApp` → no matches
- Git checks executed before final docs update:
  - `git status --short`
  - `git diff --stat`
  - `git diff --name-status`
  - `git diff --check`
  - `git diff --cached --check`

## Raw outcome summary

- Correction 1 completed:
  - exact lab hash declaration moved inside the compile-time `import.meta.env.DEV` branch in `frontend-v2/src/App.tsx`
  - lazy lab import moved inside the same compile-time DEV branch
  - production default path remains `ProductionNormalRoot`
- Correction 2 completed:
  - `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabRoute.test.tsx` now proves a normal DEV non-lab hash mounts the normal provider/root path and Finder content while the lab shell remains absent
- Correction 3 completed:
  - `frontend-v2/src/lab/r1-assessment-lab/sourceBoundary.test.ts` now uses source assertions instead of placeholder tests
  - the test source contains the exact required limitation text:
    - `Source structure does not prove dead-code elimination.`
  - the test source contains the exact required final-gate text:
    - `Final acceptance requires production artifact scanning.`

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

## Acceptance checkpoint

- Status: Accepted
- Accepted code commit: `2f798006c0fc902432ce822588866130542c390b`
- Acceptance checkpoint commit: `9352d933ca9bf43f1fb0d58ff2a359a00f2af862`
- Branch: `feat/r1-lab-entry-boundary`
- Pull request: `#277`
- Evidence reviewed:
  - review of the seven-file PR surface against the Stage 1 contract;
  - DEV exact-hash isolation test;
  - DEV normal-path test;
  - production unknown-hash Finder fallback test;
  - entry-time named network/persistence channel test;
  - source-boundary assertions;
  - reported typecheck and production build;
  - reported zero-match production JS/CSS/HTML artifact scan.
- Caveats:
  - source assertions document intended boundary only; emitted artifact scanning is the actual production non-shipping proof.
  - existing Coalsack-path and chunk-size build warnings were reported as pre-existing and are outside Stage 1 scope.
- Next safe action:
  - merge PR `#277`; do not start Stage 2 until a new stage contract is accepted.

## Last verified state

- Continuity baseline merged into `work/r1-canonical-body-evidence` before this stage.
- New implementation branch created from `f1f6cb4a8f78a484d514f8153d6e7093602458bd`.
- Frontend root: `frontend-v2`.
- No `frontend-v2/src/lab/r1-assessment-lab` directory exists before Stage 1 implementation.
- Stage 1 implementation now exists only in the six authorised product/test files.

## Remaining caveats

- `sourceBoundary.test.ts` explicitly records that source structure does not prove dead-code elimination.
- Final acceptance depended on the production artifact scan outcome, which is reported clean for the Stage 1 lab-only identifiers.
- The production build still emits existing non-blocking warnings about unresolved runtime Coalsack background paths and large chunks; these pre-date the lab shell contract and were not changed in this stage.

## Next safe action

Merge PR `#277`. Stage 2 is not authorised until a separate written contract is accepted.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
