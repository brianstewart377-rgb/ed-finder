# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Implementing — final hardening required**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Exact current base SHA: `cef563c569544089097e7b75f9f43ae62729097d`
- Required implementation branch: `feat/r1-assessment-core`
- Stage 1 PR: `#277`, merged.
- Stage 1 merge commit: `6b45e760f20f81a8b7673b412c139b3226caeb29`.
- Current head before correction: `769059d52f6301b95b429452c26ee041221ce7b6`

## Active goal

Stage 2B pure R1 assessment-domain core.

## Read before editing

- `docs/ai/README.md`
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/RECOVERY.md`
- `docs/ai/ACCEPTANCE_PROTOCOL.md`
- `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`

## Allowed files

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts`

No other files are authorised. In particular, do not change the Stage 1 boundary or shell, `App.tsx`, routes, navigation, stores, APIs, configuration, build policy, or production behavior.

## Correction requirements

1. Reject duplicate selected-template requirement IDs before fixture coverage is evaluated.
   - a duplicated template requirement must not be collapsed by a `Map`
   - a single fixture evaluation must not satisfy two template requirements with the same id

2. Require an explicit selected programme/template/revision at runtime.
   Reject selected templates where any of these is absent, not a string, or blank after trim:
   - `programmeId`
   - `templateId`
   - `revision`

## Fixed Stage 2B contract

- Assessment states are exactly:
  - `not_assessable`
  - `not_supported`
  - `conditionally_supported`
  - `supported`
- Carrier modes are exactly:
  - `no_carrier`
  - `carrier_available`
  - `compare_both`
- Assessment must require an exclusive discriminated `AssessmentLens`:
  - `{ kind: 'role'; roleId: string }`, or
  - `{ kind: 'question'; questionId: string }`.
- No score, rank, best-system result, or `plan_fit` may exist in code or output.
- Carrier can change logistics-sensitive requirement outcomes only. It must not alter frozen evidence, provenance, capacity facts, or shared constraints.
- State precedence is `not_assessable`, `not_supported`, `conditionally_supported`, then `supported`.
- `compare_both` returns `no_carrier` then `carrier_available`.
- Output ordering must be deterministic and inputs must remain immutable.

## Approved fixture/state mapping

This is a forward reconstruction decision, not a claim about lost historic behavior:

| Fixture | Scenario | Required state |
|---|---|---|
| `compact_sufficient_case` | default | `supported` |
| `incomplete_evidence_case` | default | `not_assessable` |
| `contradictory_allocation_case` | default | `not_assessable` |
| `fake_flexibility_case` | default | `not_supported` |
| `remote_materials_carrier_case` | `no_carrier` | `conditionally_supported` |
| `remote_materials_carrier_case` | `carrier_available` | `supported` |

`wregoe_dual_dodec_control` and `plateau_30_vs_60_case` are not part of Stage 2B.

## Stage 2B implementation commit

- `7a7249f5c17fa53616365a440bf5e95770b6f502` — `feat: add pure R1 assessment core`
- Correction implementation commit: `1ee4c82aca746bb1036d09e596f075334edfa0be` — `fix: tighten R1 assessment core runtime validation`
- Correction evidence commit: `ee86b05e6745d4dfe4efebd377e7322452d778f7` — `docs: record Stage 2B correction evidence`

## Required evidence before acceptance

1. `evaluateAssessment.test.ts` proves every approved fixture/state mapping.
2. Tests prove missing and contradictory evidence IDs are explicit.
3. Tests prove no score/rank/best/`plan_fit` fields exist in output.
4. Tests prove invalid/missing assessment lenses are rejected.
5. Tests prove deterministic deep equality and identical normalized JSON for identical input.
6. Tests prove fixture/template inputs are not mutated.
7. Tests prove singleton carrier mode behavior and `compare_both` ordering.
8. Tests prove frozen evidence/provenance are identical across carrier scenarios and only logistics-sensitive outcomes may differ.
9. Run the Stage 2B core test file, the four existing Stage 1 lab test files, typecheck, and production build.
10. Re-run the Stage 1 production JS/CSS/HTML identifier scan for:
    - `r1-assessment-lab`
    - `R1 Assessment Laboratory`
    - `DEV only — reconstruction shell`
    - `No production scoring`
    - `No network or persistence`
    - `Assessment engine not yet reconstructed`
    - `R1AssessmentLabApp`
11. Record branch, full commits, raw command results, artifact-scan result, `git status --short`, `git diff --stat`, `git diff --name-status`, `git diff --check`, and `git diff --cached --check` before final handoff.
12. Add focused correction tests for:
   - duplicate template requirement id rejection;
   - blank `programmeId` rejection;
   - blank `templateId` rejection;
   - blank `revision` rejection.

## Explicit non-goals

- UI expansion, reports, digests, exports, markdown/JSON report generation.
- Strategy selection or Plan Fit.
- Carrier comparison UI.
- Additional fixtures beyond the approved mapping.
- Live data, network activity, persistence, TanStack Query, routes, navigation, production integration, or bundle policy changes.
- Any claim that historic R1 source or semantics were recovered.

## Actual evidence

- Branch: `feat/r1-assessment-core`
- Current implementation commit: `1ee4c82aca746bb1036d09e596f075334edfa0be`
- Stage 2B core test:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" vitest run "src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts"`
  - Result: `1 passed, 19 tests passed`
- Stage 1 regression tests:
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
- Final worktree state: clean after final docs checkpoint

## Raw outcome summary

- Added a pure `AssessmentLens`-gated, deterministic evaluator with exact Stage 2B assessment states and carrier modes.
- Added the approved minimal fixture set and exact approved fixture/state mapping coverage.
- Added explicit tests for:
  - missing evidence IDs
  - contradictory evidence IDs
  - invalid/missing lens rejection
  - no score/rank/best/`plan_fit`
  - deterministic deep equality and stable normalized JSON
  - immutability
  - singleton carrier behavior and `compare_both` ordering
  - logistics-only carrier effects with identical frozen evidence/provenance across scenarios
- Added runtime correction coverage for:
  - invalid exclusive lens runtime shapes
  - invalid carrier mode rejection
  - carrier-varying capacity rejection
  - carrier-varying shared-constraint rejection
  - missing template requirement evaluation rejection
  - duplicate fixture evaluation rejection
- Left Stage 1 boundary, shell, routes, stores, API code, and configuration unchanged.

## Remaining caveats

- The pure evaluator is fixture-backed only and does not claim to recover lost historical planner semantics.
- The build still emits the pre-existing Coalsack asset warnings and chunk-size warning; Stage 2B did not change build policy or those runtime asset paths.

## Next safe action

Implement the final hardening pass only in `evaluateAssessment.ts` and `evaluateAssessment.test.ts`, then gather the required evidence and request final Stage 2B review on PR `#280`.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
