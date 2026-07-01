# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Accepted — merge pending**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Exact current base SHA: `cef563c569544089097e7b75f9f43ae62729097d`
- Implementation branch: `feat/r1-assessment-core`
- Review PR: `#280`
- Stage 1 PR: `#277`, merged.
- Stage 1 merge commit: `6b45e760f20f81a8b7673b412c139b3226caeb29`.

## Active goal

Stage 2B pure R1 assessment-domain core — accepted pending merge.

## Read before editing

- `docs/ai/README.md`
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/RECOVERY.md`
- `docs/ai/ACCEPTANCE_PROTOCOL.md`
- `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`

## Allowed Stage 2B files

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/core/types.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/fixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts`

No other files were authorised. The Stage 1 boundary and shell, `App.tsx`, routes, navigation, stores, APIs, configuration, build policy, and production behavior were not part of Stage 2B.

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
- Assessment requires an exclusive discriminated `AssessmentLens`:
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

## Commits

- Initial implementation: `7a7249f5c17fa53616365a440bf5e95770b6f502` — `feat: add pure R1 assessment core`
- Runtime-validation correction: `1ee4c82aca746bb1036d09e596f075334edfa0be` — `fix: tighten R1 assessment core runtime validation`
- Final hardening implementation: `e5e052a12c7b16dbc9dbff2bb1bef320f3bbab50` — `fix: harden R1 assessment core template validation`
- Final evidence handoff before acceptance: `6bbe663474b45d7bc73fea2529f5f737216ba878`

## Final acceptance checkpoint

- Accepted code commit: `e5e052a12c7b16dbc9dbff2bb1bef320f3bbab50`
- Accepted at: `2026-07-01T20:39:08Z`
- Branch: `feat/r1-assessment-core`
- Pull request: `#280`
- Reviewed scope:
  - pure local deterministic fixture-backed core only;
  - exact four assessment states and three carrier modes;
  - explicit fixture/state mapping;
  - no UI expansion, reports, digests, exports, strategy selection, Plan Fit, API, persistence, or production integration;
  - only the five authorised Stage 2B files changed.
- Runtime protections reviewed:
  - exclusive lens validation;
  - non-empty programme/template/revision validation;
  - carrier-mode validation;
  - carrier variation limited to non-shared logistics requirements marked carrier-sensitive;
  - complete and unique template/fixture requirement coverage;
  - duplicate template requirement ID rejection.
- Evidence reviewed:
  - source and test review on PR `#280`;
  - recorded local Stage 2B core test outcome: 23 tests passed;
  - recorded local Stage 1 regression outcome: 9 tests passed;
  - recorded local typecheck and production build outcomes: passed;
  - recorded deployable JS/CSS/HTML scan: zero matches for all seven Stage 1 lab-only identifiers;
  - clean final worktree reported.
- Caveats:
  - the evaluator remains fixture-backed only and does not claim recovery of lost historical planner semantics;
  - no GitHub Actions status is attached to the final head, so the command outcomes above are recorded local evidence rather than independently executed CI evidence;
  - existing Coalsack asset and chunk-size build warnings remain outside Stage 2B scope.
- Next safe action:
  - merge PR `#280`; do not start Stage 3 until a separate written contract is accepted.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
