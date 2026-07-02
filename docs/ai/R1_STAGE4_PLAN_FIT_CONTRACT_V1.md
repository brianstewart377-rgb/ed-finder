# R1 Stage 4B — Strategy Selection and Provisional Plan Fit Contract v1

**Status:** Drafted 2026-07-01 for independent review and owner approval

This is a forward-reconstruction contract. Stage 4B does **not** claim recovery of historic Plan Fit or strategy semantics.

This contract supersedes the Stage 2B `plan_fit` non-goal only for the narrowly defined Stage 4B fixture-backed pure-core scope described below. It does **not** alter any accepted Stage 2B assessment semantics.

## 1. Status and scope

Stage 4B is defined as:

- DEV-only
- fixture-backed
- deterministic
- local only
- pure core only
- not implementation-authorised merely because this contract exists

Stage 4B does **not** add:

- UI controls
- `App.tsx` changes
- routing
- normal navigation
- providers
- stores
- APIs
- network
- persistence
- live system data
- production behavior
- deployment
- editable plans
- reports
- exports
- downloads

## 2. Assessment remains primary

The Plan Fit evaluator must consume a complete accepted Stage 2B `AssessmentEvaluationResult`.

It must not:

- accept raw assessment fixture facts as an alternative input
- call or reproduce Stage 2B assessment-state resolution
- reinterpret assessment outcomes
- rescue, replace, or override assessment state

Plan Fit is secondary, explicit, plan-specific, and provisional.

## 3. Fixed explicit strategy selection

Stage 4B accepts one explicit selected strategy ID.

No strategy may be inferred from:

- fixture ID
- assessment state
- carrier mode
- lens
- score
- rank
- “best” result
- recommendation logic

Strategies are fixed forward-reconstruction fixtures only.

The exact Stage 4B fixture registry contains only:

- `baseline_local_strategy`
- `remote_logistics_strategy`

No editable strategy objects, free-form strategy input, strategy recommendation, or automatic strategy selection is permitted.

## 4. New implementation boundary for a later Stage 4B code slice

Any later approved code implementation may change only:

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/core/planFitTypes.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/strategyFixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluatePlanFit.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluatePlanFit.test.ts`

The following remain explicitly excluded from Stage 4B implementation:

- `frontend-v2/src/lab/r1-assessment-lab/core/types.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/fixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts`
- all Stage 1 tests
- all Stage 3B UI files and tests
- `frontend-v2/src/App.tsx`
- `frontend-v2/src/main.tsx`
- routes
- providers
- stores
- APIs
- stylesheets
- package files
- build/configuration files

New plan-fit types and strategy fixtures belong in new focused files to prevent accidental changes to the accepted Stage 2B and Stage 3B exports.

## 5. Strategy model

Every fixed strategy requires:

- non-empty strategy ID
- non-empty strategy revision
- non-empty neutral label
- exact compatibility tuple:
  - `programmeId`
  - `templateId`
  - `templateRevision`
- fixture provenance:
  - `sourceKind: fixture`
  - `fixtureId`
  - `fixtureRevision`
- a unique non-empty list of required assessment requirement IDs
- a possibly empty list of unique logistics-sensitive requirement IDs

The exact Stage 4B strategy records are fixed and non-negotiable:

| Strategy | Exact fields |
|---|---|
| `baseline_local_strategy` | `strategyId: baseline_local_strategy`; `strategyRevision: v1`; `label: Baseline local strategy`; compatibility: `r1_assessment_programme / core_assessment_template / r1-contract-v1`; provenance: `fixture / baseline_local_strategy / v1`; `requiredAssessmentRequirementIds`: `foundation_evidence`, `allocation_consistency`, `capacity_floor`; `logisticsSensitiveRequirementIds`: `[]` |
| `remote_logistics_strategy` | `strategyId: remote_logistics_strategy`; `strategyRevision: v1`; `label: Remote logistics strategy`; compatibility: `r1_assessment_programme / core_assessment_template / r1-contract-v1`; provenance: `fixture / remote_logistics_strategy / v1`; `requiredAssessmentRequirementIds`: `foundation_evidence`, `allocation_consistency`, `capacity_floor`, `remote_logistics`; `logisticsSensitiveRequirementIds`: `remote_logistics` |

These are fixed forward-reconstruction records, not recovered historic strategies.

Hard rules:

- Every logistics-sensitive requirement ID must be included in required assessment requirement IDs.
- Every required assessment requirement ID must exist in the accepted R1 assessment template.
- Every logistics-sensitive requirement must map to an accepted template requirement that is:
  - `kind: logistics`
  - `carrierSensitive: true`
  - `sharedConstraint: false`
- A strategy must not declare a capacity, shared-constraint, non-logistics, or carrier-insensitive requirement as logistics-sensitive.
- Duplicate strategy IDs and duplicate strategy fixture keys must be rejected.
- A strategy compatibility tuple mismatch is rejected before Plan Fit output is computed.

Do not require a broad user-configurable condition language. Keep strategy behavior limited to declared requirement dependencies and declared logistics-sensitive dependencies.

## 6. Exact Plan Fit states

Use exactly:

- `no_plan_fit`
- `blocked_plan_fit`
- `provisional_plan_fit`

Plan Fit results must be scenario-specific. A top-level single assessment state is forbidden because `compare_both` can have different assessment states per scenario.

The planned output shape must carry, per scenario:

- `carrierMode`
- `assessmentState`
- `planFitState`
- deterministic reasons
- selected strategy ID
- selected strategy revision
- selected strategy provenance

The result context carries:

- `programmeId`
- `templateId`
- `templateRevision`
- context-only lens
- original carrier mode
- selected strategy ID
- selected strategy revision

## 7. Exact assessment-state and strategy-fit rules

### `not_assessable`

Permitted Plan Fit state:

- `no_plan_fit` only

Required behavior:

- do not evaluate strategy dependencies for fit
- emit the deterministic assessment-state gate reason `gate:not_assessable`
- carrier cannot alter this result
- no strategy can turn this into blocked or provisional fit
- `no_plan_fit` contains exactly one reason: `gate:not_assessable`

### `not_supported`

Permitted Plan Fit state:

- `blocked_plan_fit` only

Required behavior:

- emit the mandatory blocking assessment-state gate reason `gate:not_supported` first
- then evaluate every selected strategy dependency and emit its §8 dependency reason where applicable
- these dependency reasons are explanatory only and cannot change `blocked_plan_fit` to `provisional_plan_fit`
- no carrier effect can turn this into `provisional_plan_fit`

### `conditionally_supported`

Permitted Plan Fit states:

- `provisional_plan_fit`
- `blocked_plan_fit`

Rules:

- `provisional_plan_fit` is allowed only where no blocking reason remains
- `blocked_plan_fit` is required where the selected strategy has an unmet required dependency
- conditional selected-strategy dependencies create non-blocking unresolved reasons
- this state must never become recommendation, preference, “good,” “best,” or final approval language

### `supported`

Permitted Plan Fit states:

- `provisional_plan_fit`
- `blocked_plan_fit`

Rules:

- `provisional_plan_fit` is allowed only where no blocking reason remains
- `blocked_plan_fit` is required where the selected strategy has an unmet required dependency
- support at the assessment layer does not guarantee a selected strategy fits

### Cross-state reason invariant

- `no_plan_fit` contains exactly one reason: `gate:not_assessable`
- `blocked_plan_fit` must contain at least one blocking reason
- `provisional_plan_fit` must contain zero blocking reasons
- Plan Fit must never alter the assessment scenario state
- an assessment-state gate reason is always first when required
- all remaining dependency reasons are sorted lexically by reason ID
- `not_assessable` contains exactly one reason: its assessment-state gate reason
- `not_supported` contains its gate reason first, followed by any emitted dependency reasons in lexical reason-ID order
- `provisional_plan_fit` has no gate reason and its dependency reasons sort lexically by reason ID
- `blocked_plan_fit` caused by a selected strategy dependency, rather than an assessment-state gate, contains dependency reasons sorted lexically by reason ID

## 8. Exact dependency-to-reason mapping

For each selected strategy requirement dependency in each accepted assessment scenario:

### `met`

- produce no dependency reason

### `conditional`

- produce one non-blocking reason
- use a logistics-specific reason kind only when the requirement is declared logistics-sensitive by the selected strategy
- otherwise use a neutral strategy-dependency reason kind

### `unmet`

- produce one blocking strategy-dependency reason

### `unknown` or `contradictory`

- these must never be silently converted into a fit result
- for a properly accepted Stage 2B result they lead to `not_assessable` and therefore `no_plan_fit`
- a structurally inconsistent passed assessment result must be rejected rather than reinterpreted

Reasons must:

- contain stable non-empty IDs using this exact scheme:
  - `gate:not_assessable`
  - `gate:not_supported`
  - `dependency:<requirementId>`
- contain neutral summary text
- carry related requirement IDs
- carry related evidence IDs where available
- have no recommendation, ranking, preference, winner, score, or comparative language

For `not_supported`, emit the mandatory blocking assessment-state gate reason first. Then evaluate every selected strategy dependency and emit its dependency reason where applicable. These dependency reasons are explanatory only and cannot change `blocked_plan_fit` to `provisional_plan_fit`.

For `not_assessable`, do not evaluate dependency reasons.

## 9. Assessment-result trust boundary and narrow validation

The Plan Fit evaluator trusts Stage 2B semantic state resolution and must not recompute it.

It must nevertheless reject structurally invalid input before computing output.

Require narrow guards for:

- non-empty template context identity
- exact assessment context tuple match against the accepted fixed template
- valid exclusive lens
- valid carrier mode
- scenario result count and exact carrier scenario ordering:
  - `no_carrier` => `[no_carrier]`
  - `carrier_available` => `[carrier_available]`
  - `compare_both` => `[no_carrier, carrier_available]`
- no duplicate carrier scenario entries
- valid scenario assessment states
- reject any scenario whose assessment state is not `not_assessable` but whose requirement results contain an `unknown` or `contradictory` outcome
- per-scenario requirement results containing every accepted template requirement exactly once
- no unknown, duplicate, or missing requirement IDs
- `RequirementAssessment` does not carry a carrier mode. Carrier identity is supplied only by its enclosing `ScenarioAssessment.carrierMode`. The Plan Fit evaluator must not require, infer, or invent a per-requirement carrier mode.
- `carrierLogisticsAffected`, where present in the accepted Stage 2B type, must be boolean and must not be treated as a second carrier-mode field
- selected strategy ID resolving exactly once in the fixed strategy registry

The evaluator must not verify whether an assessment state was correctly derived from the full requirement outcomes. That is Stage 2B’s responsibility. The `unknown` / `contradictory` rule above is a narrow structural consistency guard only; it does not recompute Stage 2B assessment state.

## 10. Carrier and lens invariants

Plan Fit never applies, repairs, transforms, or independently calculates carrier effects.

Any carrier difference originates solely from accepted Stage 2B per-scenario requirement outcomes.

Plan Fit copies each accepted Stage 2B scenario assessment state unchanged into its matching Plan Fit scenario result. It does not calculate, suppress, or replace assessment-state changes caused upstream by accepted Stage 2B carrier evaluation.

Carrier can affect only strategy dependencies that are both:

- declared logistics-sensitive by the selected strategy
- validated as logistics, carrier-sensitive, and non-shared in the accepted template

In `compare_both`, for each selected strategy requirement dependency, the evaluator compares its outcome across `no_carrier` and `carrier_available`.

Where an outcome differs across scenarios, that requirement ID must be declared in the selected strategy’s `logisticsSensitiveRequirementIds`; otherwise reject the assessment result as incompatible with the selected strategy.

Plan Fit’s only response to accepted carrier-specific outcomes is to map them through the fixed dependency-to-reason rules.

In `compare_both`, a carrier-sensitive logistics outcome may produce both:

- a different incoming `assessmentState`
- a different Plan Fit dependency-reason set

These are distinct effects. Plan Fit preserves the first and maps the second through the fixed dependency-to-reason rules.

Carrier must never:

- fill missing evidence
- resolve contradiction
- invent capacity
- bypass a shared constraint
- alter a non-logistics dependency
- convert `not_assessable` to another fit state
- convert `not_supported` to `provisional_plan_fit`

Lens remains context-only.

With the same complete assessment result and selected strategy, changing only lens may change only returned context lens. It must not change:

- scenario count
- scenario ordering
- assessment states
- Plan Fit states
- reasons
- strategy identity
- strategy provenance

## 11. Required fixed fixture matrix

These are forward-reconstruction fixture combinations, not recovered historic strategies.

1. `compact_sufficient_case` + `baseline_local_strategy` + `no_carrier`
   - supported assessment
   - `provisional_plan_fit`
   - no blocking reason

2. `remote_materials_carrier_case` + `remote_logistics_strategy` + `no_carrier`
   - conditionally_supported assessment
   - `provisional_plan_fit`
   - visible non-blocking logistics reason

3. `remote_materials_carrier_case` + `remote_logistics_strategy` + `compare_both`
   - exact scenario order: `no_carrier` then `carrier_available`
   - `no_carrier`
     - `assessmentState: conditionally_supported`
     - `planFitState: provisional_plan_fit`
     - includes non-blocking `dependency:remote_logistics`
   - `carrier_available`
     - `assessmentState: supported`
     - `planFitState: provisional_plan_fit`
     - has no `dependency:remote_logistics` reason
   - these assessment states are accepted Stage 2B input preserved by Plan Fit, not recalculated by Plan Fit
   - no comparative recommendation language

4. `fake_flexibility_case` + `baseline_local_strategy` + `no_carrier`
   - `not_supported` assessment
   - `blocked_plan_fit`
   - blocking assessment-state gate reason

5. `incomplete_evidence_case` + `baseline_local_strategy` + `no_carrier`
   - `not_assessable` assessment
   - `no_plan_fit`
   - carrier cannot repair it

6. `contradictory_allocation_case` + `baseline_local_strategy` + `compare_both`
   - both scenarios remain `no_plan_fit`
   - carrier cannot repair contradiction

## 12. Exact test contract for later implementation

The later Stage 4B test suite must prove:

- fixed strategy registry contains exactly the two stated strategy IDs
- duplicate strategy IDs and duplicate fixture keys reject
- missing or unknown strategy selection rejects
- incompatibility tuple rejects before output
- invalid strategy requirement IDs reject
- strategy logistics-sensitive declarations reject when requirement is non-logistics, carrier-insensitive, capacity, or shared
- malformed assessment-result structural guards reject
- rejection of non-`not_assessable` scenarios containing `unknown` or `contradictory` outcomes
- rejection where a selected strategy requirement changes outcome across `compare_both` without appearing in that strategy’s `logisticsSensitiveRequirementIds`
- no raw fixture input path exists
- repeated evaluation is deeply equal and normalized JSON is identical
- evaluation does not mutate assessment input, nested requirement results, frozen evidence/provenance, fixed template, strategy fixture, or output across calls
- per-state Plan Fit gating follows the exact rules above
- `not_supported` emits `gate:not_supported` first and then all applicable selected-strategy dependency reasons
- `not_assessable` contains exactly `gate:not_assessable` and no dependency reasons
- dependency-to-reason mapping follows the exact rules above
- gate-first plus lexical ordering of all following dependency reasons
- the exact reason-ID scheme is used
- required fixture matrix passes
- `compare_both` preserves accepted Stage 2B scenario states exactly:
  - `no_carrier` remains `conditionally_supported`
  - `carrier_available` remains `supported`
- the only Plan Fit dependency-reason difference for the approved remote-logistics fixture is:
  - `dependency:remote_logistics` exists in `no_carrier`
  - `dependency:remote_logistics` is absent in `carrier_available`
- the evaluator does not require or inspect a per-requirement carrier mode, because none exists in `RequirementAssessment`
- the evaluator does not calculate carrier effects or assessment-state transitions; it preserves scenario states provided by Stage 2B and maps dependency outcomes only
- carrier cannot repair missing evidence, contradiction, capacity, shared constraint, `not_assessable`, or `not_supported`
- changing only lens changes only returned context lens
- scenario order is exact
- reason order follows the gate-first then lexical dependency-order rule above
- exact strategy-table fields are preserved, including compatibility, revision, provenance, required requirement IDs, and logistics-sensitive requirement IDs
- strategy revision and provenance are preserved exactly
- rejection paths are thrown errors
- synthetic or cloned malformed test inputs are permitted solely to exercise required rejection coverage
- a recursive object-key scan proves output contains no:
  - `score`
  - `rank`
  - `best`
  - `recommend`
  - `recommendation`
  - `preference`
  - `winner`
  - `desirability`
- strategy and plan-fit vocabulary are allowed internal core-domain terms in Stage 4B; do not inherit a stale blanket ban on those words
- existing Stage 1 regression tests, Stage 2B evaluator tests, and Stage 3B UI tests remain unchanged gates
- typecheck, production build, and production deployable JS/CSS/HTML scans remain required evidence
- the production artifact scan must include the existing Stage 1 and Stage 3 lab identifiers plus Stage 4-specific identifiers:
  - `baseline_local_strategy`
  - `remote_logistics_strategy`
  - `no_plan_fit`
  - `blocked_plan_fit`
  - `provisional_plan_fit`

## 13. Explicit non-goals

Stage 4B does not add:

- live system advice
- automatic strategy selection
- strategy recommendation
- scoring
- ranking
- best result
- preference
- winner selection
- editable plans
- material planning
- route planning
- colonisation staging
- reports
- digests
- exports
- downloads
- UI expansion
- network
- persistence
- production integration
- lens-specific strategy semantics
- any reinterpretation of Stage 2B assessment semantics
