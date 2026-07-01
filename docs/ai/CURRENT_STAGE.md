# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Accepted — automatic merge pending**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Stage 3B branch: `feat/r1-assessment-lab-presentation`
- Base SHA: `b6529e70ddbdcc26d46ce742eea793273138c635`
- Review PR: `#282` — `Stage 3B: DEV-only R1 assessment lab`
- Last accepted implementation stage: Stage 2B pure R1 assessment-domain core, merged by PR `#280` at `220c870f89a5af7f98adb88578373dbc3a681a9c`.

## Accepted Stage 3B implementation

- Original presentation implementation: `fe28827d0703e9fe1ca4d510fbb434e39f64bcf0`
- Final presentation-test hardening: `2c10872a82046949bc91cb53481b1cee2390a853`
- Pre-acceptance evidence records:
  - `0a664579163b7b14b08167dcd68ceaf94ffee3a5`
  - `373841a740bc9a48ccff6f1c7b981ea6c64fa69b`
- This commit records final acceptance before automatic merge.

## Reviewed scope

The PR changes only:

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx`

Stage 3B is a DEV-only, fixture-backed assessment-lab presentation surface inside the existing Stage 1 entry boundary. It does not change `App.tsx`, production routing, normal application navigation, providers, stores, APIs, persistence, configuration, stylesheets, or Stage 2B evaluator semantics.

## Accepted behavior and invariants

- The lab exposes exactly four closed local select controls: Fixture, Lens kind, Lens value, and Carrier mode.
- Five fixture IDs and three carrier modes are selectable; the six approved fixture/scenario state rows are test assertions, not six fixtures.
- The fixed template is displayed read-only.
- The selected Role/Question lens is passed to the evaluator and visibly displayed as context only. Changing it does not alter fixture outcomes, conditions, requirement results, frozen evidence/provenance, state, or ordering in this slice.
- The app synchronously evaluates fixed local data only and has no UI for invalid evaluator input.
- Results render state, structured conditions, requirement trace, and frozen evidence/provenance. `compare_both` preserves `no_carrier` then `carrier_available` order.
- State values are rendered neutrally without score, ranking, winner, preference, strategy, Plan Fit, or recommendation behavior.

## Final evidence reviewed

- Dedicated Stage 3B UI tests: 7 passed.
- Unchanged Stage 1 regression tests: 9 passed across 4 files.
- Unchanged Stage 2B core tests: 23 passed.
- Typecheck passed.
- Production build passed.
- Production deployable JS/CSS/HTML scans reported zero matches for the seven Stage 1 lab-only identifiers and all approved Stage 3-only lab strings.
- Final local worktree was reported clean.
- Source review confirmed separate immediate no-side-effect assertions after each fixture, lens-kind, lens-value, and carrier-mode change, plus scoped trace and frozen-evidence provenance assertions.

## Caveats

- The test, typecheck, build, and artifact-scan results are recorded local evidence. No GitHub Actions status is attached to the final pre-acceptance head.
- Existing Coalsack asset-resolution and chunk-size build warnings remain outside Stage 3B scope.
- The lab remains a fixture-backed reconstruction contract and does not claim recovery of the historic evaluator or provide live system advice.

## Next safe action

Merge PR `#282` automatically. Do not deploy. Do not begin Stage 4 until a separate written contract is accepted.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
