# R1 Assessment Laboratory — Reconstruction Contract v1

**Status:** Approved 2026-07-01

This is a forward-looking reconstruction contract. It defines the semantics that the new R1 Assessment Laboratory must implement. It does **not** claim to recover the lost historical source or fixture meanings exactly.

## Purpose of Stage 2B

Stage 2B creates only a pure, local, deterministic, fixture-backed assessment-domain core.

It does not add application UI beyond the Stage 1 inert shell. It does not add network activity, persistence, routes, production behavior, reports, exports, strategy selection, Plan Fit, or a universal score/rank.

## Fixed domain contract

```ts
type AssessmentState =
  | 'not_assessable'
  | 'not_supported'
  | 'conditionally_supported'
  | 'supported';

type CarrierMode =
  | 'no_carrier'
  | 'carrier_available'
  | 'compare_both';

type AssessmentLens =
  | { kind: 'role'; roleId: string }
  | { kind: 'question'; questionId: string };
```

Every evaluation must include one selected programme/template/revision, one `AssessmentLens`, and one `CarrierMode`. A call with neither a role nor a question is invalid; a call with both is invalid by construction.

Safe first-slice categories:

```ts
type RequirementKind = 'eligibility' | 'capacity' | 'logistics' | 'constraint';
type ConditionKind =
  | 'missing_evidence'
  | 'contradictory_evidence'
  | 'logistics_dependency'
  | 'requirement_gap'
  | 'bounded_support';
type EvidenceAvailability = 'known' | 'missing' | 'contradictory' | 'not_applicable';
type RequirementOutcome = 'met' | 'unmet' | 'conditional' | 'unknown' | 'contradictory';
```

## Fixed semantic invariants

- No output may contain a universal score, rank, best-system result, or `plan_fit`.
- Assessment is relative to the explicit programme/template/lens/carrier context.
- The evaluator is pure, side-effect-free, input-immutable, deterministic, and JSON-serializable.
- The evaluator must not use React values, functions, classes, Dates, Maps, Sets, network handles, or persistence handles.
- Carrier mode affects logistics-sensitive requirement outcomes only.
- Carrier mode must never change frozen evidence, provenance, capacity facts, or shared constraints.
- Missing, unknown, contradictory, or ineligible evidence is never rescued by carrier mode, later strategy logic, or future Plan Fit.
- Per-scenario state precedence is:
  1. `not_assessable`
  2. `not_supported`
  3. `conditionally_supported`
  4. `supported`
- `compare_both` returns exactly two scenario results in this order:
  1. `no_carrier`
  2. `carrier_available`
- Requirement results sort by `requirementId`; conditions and frozen evidence sort by `id`.

## Approved reconstruction fixture mapping

This mapping is an explicit R1 reconstruction decision, not an assertion about lost historical behavior.

| Fixture | Scenario | Required state | Purpose |
|---|---|---|---|
| `compact_sufficient_case` | default | `supported` | Clean positive baseline. |
| `incomplete_evidence_case` | default | `not_assessable` | Missing or unknown evidence blocks a valid assessment. |
| `contradictory_allocation_case` | default | `not_assessable` | Contradictory evidence blocks a valid assessment. |
| `fake_flexibility_case` | default | `not_supported` | Assessment is possible, but a mandatory requirement fails. |
| `remote_materials_carrier_case` | `no_carrier` | `conditionally_supported` | Explicit logistics condition remains. |
| `remote_materials_carrier_case` | `carrier_available` | `supported` | Carrier resolves only the logistics condition. |

`wregoe_dual_dodec_control` and `plateau_30_vs_60_case` are not part of Stage 2B unless a later written contract gives them a specific proof role.

## Minimal evaluation shape

The input must contain fixture data, selected programme/template/revision, `AssessmentLens`, and carrier mode. The output contains the resolved context and one or two ordered scenario results, including requirement-level outcomes, structured conditions, and frozen evidence/provenance.

No report, digest, markdown export, strategy result, or Plan Fit field belongs in this stage.

## Stage 2B file boundary

Only these files may be created or changed:

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/core/types.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/fixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts`

No changes to the Stage 1 entry boundary, App routing, shell, stores, API layer, configuration, production build policy, or other files are authorised.

## Required Stage 2B tests

1. Each approved fixture/state mapping above.
2. Explicit missing evidence IDs for `incomplete_evidence_case`.
3. Explicit contradictory evidence IDs for `contradictory_allocation_case`.
4. Output does not contain `score`, `rank`, `best`, or `plan_fit`.
5. Evaluation rejects an invalid or absent assessment lens.
6. Identical input produces deeply equal output and identical normalized JSON.
7. The evaluator does not mutate fixture or template input.
8. `no_carrier` and `carrier_available` each return one matching scenario.
9. `compare_both` returns exactly two ordered scenarios.
10. Across carrier scenarios, frozen evidence and provenance are identical; only logistics-sensitive requirement outcomes may differ.

## Non-goals

Stage 2B must not include:

- reports, digests, markdown/JSON exports;
- strategy selection;
- Plan Fit;
- a carrier comparison UI;
- fixtures beyond the approved mapping;
- routes, navigation, stores, TanStack Query, live APIs, persistence, or production integration;
- bundle/dead-code assertions;
- any claim that the historic R1 evaluator has been recovered.
