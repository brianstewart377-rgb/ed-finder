# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Stage 3A design accepted — technical contract pending**

## Baseline

- Base branch: `work/r1-canonical-body-evidence`
- Last accepted implementation stage: Stage 2B pure R1 assessment-domain core.
- Stage 2B PR: `#280`, merged.
- Stage 2B merge commit: `220c870f89a5af7f98adb88578373dbc3a681a9c`.
- Stage 3A is read-only design work only. No Stage 3 implementation is authorised.

## Active goal

Prepare the Stage 3B technical contract for the smallest credible DEV-only, fixture-backed R1 assessment-lab presentation layer.

## Read before any Stage 3 work

- `docs/ai/README.md`
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/RECOVERY.md`
- `docs/ai/ACCEPTANCE_PROTOCOL.md`
- `docs/ai/R1_RECONSTRUCTION_CONTRACT_V1.md`
- the merged Stage 1 DEV boundary and Stage 2B core files.

## Stage 3A accepted direction

### Confirmed contract

- The lab remains available only through the existing DEV-only `#r1-assessment-lab` entry boundary.
- Stage 3B is fixture-backed only and directly consumes the accepted pure Stage 2B evaluator.
- No production routing, normal app navigation, provider, store, API, live-data, or persistence behavior may be added.
- No score, rank, best-system wording, recommendation, strategy, Plan Fit, report, digest, export, download, material planning, route planning, or colonisation-staging control belongs in Stage 3B.
- Fixed fixture data must remain read-only.
- Results must render in this order:
  1. assessment state;
  2. structured conditions;
  3. requirement trace;
  4. frozen evidence and provenance;
  5. carrier scenario comparison where `compare_both` is selected.
- `compare_both` must present `no_carrier` before `carrier_available`.

### Accepted Stage 3B lens decision

- The UI may expose an explicit Role/Question lens picker.
- The selected lens is passed to the evaluator and displayed as assessment context.
- Lens selection is **context-only** in Stage 3B. It must not change fixture evaluation, requirement outcomes, conditions, or assessment state.
- The UI must state this plainly and persistently. It must not imply that lens-specific analysis has been reconstructed.

### Honest status language required

The presentation must clearly state that it is:

- DEV-only;
- fixture-backed;
- a reconstruction-contract surface;
- not a recovery of the historic evaluator;
- not production scoring or live recommendations.

## Strongly supported Stage 3B boundary

The technical contract should consider this smallest credible file set:

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/presentation.ts`
- `frontend-v2/src/lab/r1-assessment-lab/presentation.test.ts`

This is a proposed boundary, not coding authorisation. The technical-contract review must either accept it exactly or justify a narrower alternative.

## Required Stage 3B evidence to define before coding

- existing Stage 1 entry-isolation, route, no-network, and source-boundary tests remain unchanged regression gates;
- existing Stage 2B core tests remain an unchanged regression gate;
- dedicated UI tests for fixed fixture selection, visible context-only lens notice, all three carrier modes, and `compare_both` order;
- visible proof of all four assessment states;
- visible `No structured conditions.` empty state;
- deterministic visible frozen evidence/provenance;
- interaction-time network/persistence silence after changing all controls;
- no rendered forbidden terms or fields: `score`, `rank`, `best`, `plan_fit`;
- typecheck and production build;
- production JS/CSS/HTML scan for the existing seven lab-only identifiers **plus every new Stage 3-specific visible lab string**;
- explicit diff/check evidence and clean worktree.

## Explicit non-goals

- changes to `App.tsx`, `src/main.tsx`, routes, normal navigation, production behavior, stores, APIs, or configuration;
- changes to Stage 2B evaluator semantics, fixtures, or types;
- editable fixture data, JSON inputs, overrides, free-form system search, or what-if modelling;
- reports, digests, exports, markdown generation, hashes, or downloads;
- strategy selection, Plan Fit, material recommendations, route planning, or colonisation staging;
- public-facing UI.

## Next safe action

Obtain a revised **Stage 3B technical contract** that incorporates the accepted context-only lens decision, the precise UI copy, exact controls/defaults, allowed files, tests, final artifact-scan identifier list, and explicit non-goals. Do not create a Stage 3 branch or edit product code until the owner accepts that contract.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
