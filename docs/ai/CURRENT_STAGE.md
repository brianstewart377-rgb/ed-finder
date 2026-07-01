# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Implementing — Stage 3B evidence gathered**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Branch: `feat/r1-assessment-lab-presentation`
- Exact base SHA: `b6529e70ddbdcc26d46ce742eea793273138c635`
- Last accepted implementation stage: Stage 2B pure R1 assessment-domain core.
- Stage 2B PR: `#280`, merged.
- Stage 2B merge commit: `220c870f89a5af7f98adb88578373dbc3a681a9c`.
- Stage 3B implementation commit: `fe28827d0703e9fe1ca4d510fbb434e39f64bcf0`

## Active goal

DEV-only fixture-backed assessment-lab presentation.

## Read before any Stage 3 work

- `docs/ai/README.md`
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/RECOVERY.md`
- `docs/ai/ACCEPTANCE_PROTOCOL.md`
- `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`
- the merged Stage 1 DEV boundary and Stage 2B core files.

## Allowed files

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx`

No other files are authorised. Do not modify `App.tsx`, `src/main.tsx`, Stage 1 tests, Stage 2B core files or tests, routes, navigation, providers, stores, APIs, build/configuration files, stylesheets, or package files.

## Fixed controls and defaults

Use only local React `useState` and synchronous direct `evaluateAssessment(...)` calls.

Render exactly four labelled HTML `select` controls, in this order:

1. `Fixture`
   - default: `compact_sufficient_case`
   - options, in order:
     - `compact_sufficient_case`
     - `incomplete_evidence_case`
     - `contradictory_allocation_case`
     - `fake_flexibility_case`
     - `remote_materials_carrier_case`
2. `Lens kind`
   - default: `role`
   - options, in order:
     - `role`
     - `question`
3. `Lens value`
   - when `Lens kind` is `role`:
     - default: `expedition-lead`
     - options, in order:
       - `expedition-lead`
       - `logistics-reviewer`
   - when `Lens kind` is `question`:
     - default: `baseline-assessment`
     - options, in order:
       - `baseline-assessment`
       - `carrier-sensitivity-check`
   - changing `Lens kind` resets `Lens value` to that kind’s default
4. `Carrier mode`
   - default: `no_carrier`
   - options, in order:
     - `no_carrier`
     - `carrier_available`
     - `compare_both`

There are exactly five selectable fixture IDs. The six Stage 2B fixture/scenario assertion rows are not six fixtures.

There is no form submission, Evaluate button, reset button, URL state, free-text input, JSON input, checkbox, radio group, textarea, timer, promise, async function, `useEffect`, dynamic runtime import, error boundary, or evaluator-error UI.

## Exact disclosures

Render these exact lines, visibly and persistently:

- `R1 Lab — DEV-only fixture-backed reconstruction.`
- `R1 Lab — historic evaluator recovery is not claimed.`
- `R1 Lab — no production scoring or live system advice.`
- `R1 Lab — Lens context only: changing it does not alter fixture outcomes, requirement outcomes, conditions, assessment state, or ordering in Stage 3B.`
- `R1 Lab — Lens labels are local presentation context, not rebuilt role or question semantics.`
- `Template: r1_assessment_programme / core_assessment_template / r1-contract-v1 (fixed for Stage 3B)`

## Context-only lens rule

The selected role/question lens must be passed to the Stage 2B evaluator and shown as selected context, but it must not change fixture outcomes, requirement outcomes, conditions, assessment state, or ordering in Stage 3B.

## Result order

Render results in this exact order:

1. `Assessment state`
2. `Structured conditions`
3. `Requirement trace`
4. `Frozen evidence and provenance`
5. `Carrier scenario comparison` where `compare_both` is selected

Inside `compare_both`, render:

1. `no_carrier`
2. `carrier_available`

## Required Stage 3B evidence to define before coding

- `R1AssessmentLabApp.test.tsx` proves the exact controls/defaults, disclosures, fixed-template line, all five selectable fixture IDs, all three carrier modes, and exclusive lens selection with reset-to-default behavior.
- `R1AssessmentLabApp.test.tsx` proves these exact state-coverage combinations:
  - `compact_sufficient_case` + `no_carrier` => `supported`
  - `incomplete_evidence_case` + `no_carrier` => `not_assessable`
  - `contradictory_allocation_case` + `no_carrier` => `not_assessable`
  - `fake_flexibility_case` + `no_carrier` => `not_supported`
  - `remote_materials_carrier_case` + `no_carrier` => `conditionally_supported`
  - `remote_materials_carrier_case` + `carrier_available` => `supported`
  - `remote_materials_carrier_case` + `compare_both` => `no_carrier` then `carrier_available`
- `R1AssessmentLabApp.test.tsx` proves the mandatory context-only lens test:
  - select `remote_materials_carrier_case` and `compare_both`
  - capture rendered scenario result content for state, conditions, requirement trace, and frozen evidence/provenance
  - change lens kind and lens value
  - prove selected lens context changed
  - prove all captured scenario-result content is unchanged and remains in the same order
- `R1AssessmentLabApp.test.tsx` proves `No structured conditions.` renders for condition-free scenarios.
- `R1AssessmentLabApp.test.tsx` proves requirement trace and frozen evidence/provenance render visibly.
- `R1AssessmentLabApp.test.tsx` proves no network or persistence activity after each control change: fixture, lens kind, lens value, and carrier mode.
- `R1AssessmentLabApp.test.tsx` proves the rendered UI, case-insensitively, contains no `score`, `rank`, `best`, `plan_fit`, `plan fit`, `recommend`, `strategy`, `report`, `export`, or `download`.
- unchanged regression gates must pass:
  - `AppEntryIsolation.test.tsx`
  - `R1AssessmentLabRoute.test.tsx`
  - `noNetwork.test.tsx`
  - `sourceBoundary.test.ts`
  - `evaluateAssessment.test.ts`
- `typecheck` and production `build`
- production deployable `JS/CSS/HTML` scan returns zero matches for:
  - the existing seven Stage 1 lab-only identifiers
  - the Stage 3-only strings and identifiers:
    - `R1 Lab — DEV-only fixture-backed reconstruction.`
    - `R1 Lab — historic evaluator recovery is not claimed.`
    - `R1 Lab — no production scoring or live system advice.`
    - `R1 Lab — Lens context only: changing it does not alter fixture outcomes, requirement outcomes, conditions, assessment state, or ordering in Stage 3B.`
    - `R1 Lab — Lens labels are local presentation context, not rebuilt role or question semantics.`
    - `Template: r1_assessment_programme / core_assessment_template / r1-contract-v1 (fixed for Stage 3B)`
    - `compact_sufficient_case`
    - `incomplete_evidence_case`
    - `contradictory_allocation_case`
    - `fake_flexibility_case`
    - `remote_materials_carrier_case`
    - `no_carrier`
    - `carrier_available`
    - `compare_both`
- explicit `git status --short`, `git diff --stat`, `git diff --name-status`, `git diff --check`, and `git diff --cached --check` evidence with a final clean worktree.

## Actual evidence

- Branch: `feat/r1-assessment-lab-presentation`
- Current implementation commit: `fe28827d0703e9fe1ca4d510fbb434e39f64bcf0`
- Stage 3B presentation test:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" vitest run "src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx"`
  - Result: `1 passed, 7 tests passed`
- Stage 1 regression tests:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" vitest run "src/lab/r1-assessment-lab/AppEntryIsolation.test.tsx" "src/lab/r1-assessment-lab/R1AssessmentLabRoute.test.tsx" "src/lab/r1-assessment-lab/noNetwork.test.tsx" "src/lab/r1-assessment-lab/sourceBoundary.test.ts"`
  - Result: `4 passed, 9 tests passed`
- Stage 2B core regression test:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" vitest run "src/lab/r1-assessment-lab/core/evaluateAssessment.test.ts"`
  - Result: `1 passed, 23 tests passed`
- Typecheck:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" typecheck`
  - Result: passed
- Production build:
  - `yarn --cwd "/data/user/work/ed-finder/frontend-v2" build`
  - Result: passed
- Production deployable `JS/CSS/HTML` scan:
  - existing seven Stage 1 lab-only identifiers → no matches
  - Stage 3-only strings and identifiers → no matches
- Git checks executed before final docs update:
  - `git status --short`
  - `git diff --stat`
  - `git diff --name-status`
  - `git diff --check`
  - `git diff --cached --check`

## Raw outcome summary

- Replaced the inert Stage 1 lab body with a closed local presentation surface using only local `useState` and synchronous direct `evaluateAssessment(...)` calls.
- Added exactly four labelled `select` controls with the approved defaults and option order.
- Preserved the Stage 1 boundary strings required by unchanged regression tests.
- Rendered exact Stage 2B state labels neutrally, without winner framing, recommendations, or ranking language.
- Added a dedicated UI test proving the mandatory context-only lens behavior and interaction-time network/persistence silence after each control change.

## Remaining caveats

- The production build still emits the pre-existing Coalsack asset warnings and chunk-size warning; Stage 3B did not change build policy or those asset paths.

## Explicit non-goals

- `App.tsx`, `src/main.tsx`, route, normal navigation, provider, store, API, build/configuration, stylesheet, or package changes;
- Stage 2B evaluator, type, fixture, or semantic changes;
- CSS work, inline styles, state-specific class names, visual statuses, icons, badges, or winner styling;
- editable fixture data, JSON inputs, overrides, free-form inputs, template picker, or error workflow;
- network, persistence, reports, exports, downloads, hashes, markdown output, strategy, Plan Fit, scores, ranking, recommendations, material planning, route planning, colonisation staging, or public UI.

## Next safe action

Push the branch with the Stage 3B implementation and request review of the DEV-only presentation slice. Do not begin another stage until this one is reviewed.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
