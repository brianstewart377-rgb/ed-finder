# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Stage 5A docs-only R1 control-fixture discovery drafted — awaiting independent review and owner acceptance.**

## Baseline

- Canonical base branch: `work/r1-canonical-body-evidence`
- Stage 5A documentation branch: `docs/r1-stage5a-control-fixture-discovery`
- Stage 5A documentation base SHA: `fe06439132f52c9ccae5c4652f10de838b5ec445`
- Stage 4B contract PR: `#284`, merged
- Stage 4B contract merge commit: `411ceb9232966bf27aa027d72aa5622c83ee0d03`
- Stage 4B implementation PR: `#286`, merged
- Stage 4B implementation merge commit: `0565a60428904c4fe234f500e05be9871adb5c6d`
- Stage 4B reviewed implementation head: `9f69061c3d625dc111864061166287407e6336c0`
- Stage 4B was independently reviewed and owner-accepted before merge.
- Stage 4C contract PR: `#287`, merged
- Stage 4C contract merge commit: `18464de5a204a109fe145eb4e64a8500b59eaee5`
- Stage 4C implementation PR: `#288`, merged
- Stage 4C implementation merge commit: `5017b713627600887cefc781066c3a6eacfdbcba`
- Stage 4C accepted code commit: `4eabc24ba9b428c2902fa2221c15b7d5371d0433`
- Stage 4C acceptance closeout PR: `#289`, merged
- Stage 4C acceptance closeout merge commit: `fe06439132f52c9ccae5c4652f10de838b5ec445`
- Stage 3B PR: `#282` — `Stage 3B: DEV-only R1 assessment lab`, merged
- Stage 3B merge commit: `98b4bacf1d799e7937b449210046659b3e96615b`
- Stage 2B pure R1 assessment-domain core: PR `#280`, merged at `220c870f89a5af7f98adb88578373dbc3a681a9c`.
- No deployment occurred.

## Active Stage 5A discovery record

- Discovery record: `docs/ai/R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`
- Stage 5A is documentation-only.
- It investigates the deferred names `wregoe_dual_dodec_control` and `plateau_30_vs_60_case` only to determine whether current repository evidence supports a precise later proof role.
- Stage 5A does not assign either name new semantics, create a fixture, change a test, or authorise any implementation.
- The documented finding is that neither name has a recoverable current fixture payload or deterministic proof role; both remain absent from the active registry pending a separate, explicit future contract.
- No implementation is authorised by this discovery record.

## Stage 5A allowed files

- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`

`docs/ai/DECISIONS.md` remains unchanged until the owner accepts the independently reviewed Stage 5A conclusion.

## Stage 5A non-goals

Stage 5A does not add or change:

- R1 fixture data;
- R1 core types, Assessment semantics, or Plan Fit semantics;
- R1 lab UI;
- normal application behavior, routes, navigation, providers, stores, APIs, network, or persistence;
- production assets, configuration, build behavior, deployment, exports, reports, scoring, ranking, recommendation, or planning;
- claims of recovered historical semantics.

## Stage 5A evidence boundary

- `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md` names both controls only as deferred controls requiring a later written contract with a specific proof role.
- The active `R1_ASSESSMENT_FIXTURES` registry contains five fixtures only: `compact_sufficient_case`, `incomplete_evidence_case`, `contradictory_allocation_case`, `fake_flexibility_case`, and `remote_materials_carrier_case`.
- Repository-wide source search found no current source, test, or document reference to either deferred name beyond the deferral note.
- Fixture names alone are insufficient evidence from which to infer a Wregoe, Dodec, numerical-threshold, capacity, logistics, material, planning, ranking, or recommendation rule.

## Stage 4C acceptance checkpoint

- Status: Accepted and merged.
- Accepted code commit: `4eabc24ba9b428c2902fa2221c15b7d5371d0433`
- Acceptance date: `2026-07-02`
- Branch: `feat/r1-stage4c-plan-fit-lab`
- Pull request: `#288`, merged at `5017b713627600887cefc781066c3a6eacfdbcba`
- Documentation-only acceptance checkpoint commit: `2db42b27852f7cae19d0fa7754991cf530845b8c`
- Documentation closeout record: PR `#289`, merged at `fe06439132f52c9ccae5c4652f10de838b5ec445`
- Evidence reviewed:
  - Independent read-only Stage 4C implementation review at `4eabc24ba9b428c2902fa2221c15b7d5371d0433`, verdict: ready for owner acceptance.
  - Reported focused UI test, unchanged Stage 2B and Stage 4B core tests, full test suite, typecheck, lint, and production build.
  - Reported deployable `JS/CSS/HTML` artifact scan with no matches for existing DEV-only R1 identifiers or the Stage 4 identifiers recorded below.
- Caveats:
  - The acceptance checkpoint was recorded in a post-merge documentation repair. It did not reopen product-code review.
  - The reported full suite retained pre-existing `act(...)` warnings from `src/features/my-work/MyWorkWorkspace.test.tsx`.
  - The reported production build retained pre-existing Coalsack asset-resolution warnings and the existing chunk-size warning.
  - No deployment occurred.

## Accepted Stage 4C record

- Contract file: `docs/ai/R1_STAGE4C_PLAN_FIT_LAB_PRESENTATION_CONTRACT_V1.md`
- Stage 4C implemented only the accepted DEV-only, fixture-backed, deterministic, local presentation slice inside the existing R1 Assessment Laboratory.
- Its code change was restricted to `R1AssessmentLabApp.tsx` and `R1AssessmentLabApp.test.tsx`; the stage record was the only documentation file changed.
- No Stage 2B or Stage 4B core file, production behavior, routing, persistence, network, API, recommendation, scoring, ranking, planning behavior, deployment, or production asset change was included.

## Preserved merged invariants

- The lab exposes exactly five closed local select controls: Fixture, Lens kind, Lens value, Carrier mode, and Strategy.
- The first four selector IDs, values, defaults, ordering, and semantics remain unchanged. Strategy is explicit local DEV-lab context only, with the fixed options `baseline_local_strategy` and `remote_logistics_strategy`; it is not inferred from fixture, assessment state, carrier mode, or lens.
- Five fixture IDs and three carrier modes are selectable; the six approved fixture/scenario state rows are test assertions, not six fixtures.
- The fixed template is displayed read-only.
- The selected Role/Question lens is passed to the evaluator and visibly displayed as context only. Changing it does not alter fixture outcomes, conditions, requirement results, frozen evidence/provenance, state, Plan Fit output, or ordering in this slice.
- Accepted Stage 4B Plan Fit output remains bounded pure-core logic subordinate to accepted Stage 2B assessment results.
- Stage 4C presents returned Assessment and Plan Fit scenario output without deriving, rewriting, or recalculating it.
- `compare_both` preserves `no_carrier` then `carrier_available` order.

## Caveats

- No deployment occurred.
- Stage 4B and Stage 4C are merged and accepted.
- Stage 5A is a documentation-only discovery record and introduces no production behavior, recommendation, ranking, scoring, strategy inference, planning behavior, fixture change, test change, or code change.
- Local validation reported on the Stage 4C implementation branch:
  - `yarn test "src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx"`
  - `yarn test "src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts"`
  - `yarn test "src/lab/r1-assessment-lab/core/evaluatePlanFit.test.ts"`
  - `yarn test`
  - `yarn typecheck`
  - `yarn lint`
  - `yarn build`
  - production deployable `JS/CSS/HTML` scan for existing DEV-only R1 identifiers plus:
    - `baseline_local_strategy`
    - `remote_logistics_strategy`
    - `no_plan_fit`
    - `blocked_plan_fit`
    - `provisional_plan_fit`
    - `gate:not_assessable`
    - `gate:not_supported`
    - `dependency:`
- The reported production build retained the pre-existing Coalsack asset-resolution warnings and the existing chunk-size warning.

## Next safe action

Obtain an independent read-only review of the Stage 5A discovery record and this stage record. Do not create an implementation branch, edit R1 fixtures, tests, core, or UI, change the normal application, merge a new implementation, or deploy until the owner accepts the reviewed Stage 5A conclusion and separately authorises any later stage.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
