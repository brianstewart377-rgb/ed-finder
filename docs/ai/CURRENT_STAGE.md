# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Implementing**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Exact current base SHA: `cef563c569544089097e7b75f9f43ae62729097d`
- Required implementation branch: `feat/r1-assessment-core`
- Stage 1 PR: `#277`, merged.
- Stage 1 merge commit: `6b45e760f20f81a8b7673b412c139b3226caeb29`.

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
- `frontend-v2/src/lab/r1-assessment-lab/core/types.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/fixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts`

No other files are authorised. In particular, do not change the Stage 1 boundary or shell, `App.tsx`, routes, navigation, stores, APIs, configuration, build policy, or production behavior.

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

## Explicit non-goals

- UI expansion, reports, digests, exports, markdown/JSON report generation.
- Strategy selection or Plan Fit.
- Carrier comparison UI.
- Additional fixtures beyond the approved mapping.
- Live data, network activity, persistence, TanStack Query, routes, navigation, production integration, or bundle policy changes.
- Any claim that historic R1 source or semantics were recovered.

## Next safe action

Implement only the allowed Stage 2B files: pure domain types, approved fixtures, deterministic evaluator, and required unit tests.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
