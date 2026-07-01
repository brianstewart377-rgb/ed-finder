# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Stage 4B technical contract revised after independent review — awaiting final independent review and owner approval**

## Baseline

- Canonical base branch: `work/r1-canonical-body-evidence`
- Current documentation branch: `docs/r1-stage4-plan-fit-contract`
- Base SHA: `83f4e4bc9829c173979fce5aa0bda734174ca55a`
- Stage 3B PR: `#282` — `Stage 3B: DEV-only R1 assessment lab`, merged
- Stage 3B merge commit: `98b4bacf1d799e7937b449210046659b3e96615b`
- Last accepted implementation stage: Stage 2B pure R1 assessment-domain core, merged by PR `#280` at `220c870f89a5af7f98adb88578373dbc3a681a9c`.
- No deployment occurred.

## Active contract record

- Contract file: `docs/ai/R1_STAGE4_PLAN_FIT_CONTRACT_V1.md`
- This branch is documentation-only.
- No Stage 4B implementation is authorised.
- The first independent review required deterministic-output and carrier-boundary wording corrections in the contract text.

## Proposed later Stage 4B implementation allowlist

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/core/planFitTypes.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/strategyFixtures.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluatePlanFit.ts`
- `frontend-v2/src/lab/r1-assessment-lab/core/evaluatePlanFit.test.ts`

## Scope summary

Stage 4B is defined only as a DEV-only, fixture-backed, deterministic, local, pure-core forward reconstruction for explicit strategy selection and provisional Plan Fit. The contract does not claim recovery of historic strategy or Plan Fit semantics and does not alter accepted Stage 2B assessment semantics.

## Exact non-goals

Stage 4B does not add:

- UI expansion
- `App.tsx` changes
- routing or normal navigation
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
- scoring
- ranking
- best result
- automatic strategy selection
- strategy recommendation
- preference
- winner selection
- material planning
- route planning
- colonisation staging
- lens-specific strategy semantics
- any reinterpretation of accepted Stage 2B assessment semantics

## Preserved merged invariants

- The lab exposes exactly four closed local select controls: Fixture, Lens kind, Lens value, and Carrier mode.
- Five fixture IDs and three carrier modes are selectable; the six approved fixture/scenario state rows are test assertions, not six fixtures.
- The fixed template is displayed read-only.
- The selected Role/Question lens is passed to the evaluator and visibly displayed as context only. Changing it does not alter fixture outcomes, conditions, requirement results, frozen evidence/provenance, state, or ordering in this slice.
- The app synchronously evaluates fixed local data only and has no UI for invalid evaluator input.
- Results render state, structured conditions, requirement trace, and frozen evidence/provenance. `compare_both` preserves `no_carrier` then `carrier_available` order.
- State values are rendered neutrally without score, ranking, winner, preference, strategy, Plan Fit, or recommendation behavior.

## Caveats

- This branch contains only documentation updates.
- No implementation, test, configuration, or production change is authorised by the Stage 4B contract alone.
- Any later Stage 4B implementation must use the new focused plan-fit files rather than modifying accepted Stage 2B or Stage 3B files.

## Next safe action

Obtain independent read-only review of `R1_STAGE4_PLAN_FIT_CONTRACT_V1.md`. Do not create a Stage 4B implementation branch or edit core code until the owner explicitly authorises implementation.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
