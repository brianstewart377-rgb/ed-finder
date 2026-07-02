# R1 Stage 4C — DEV-only Plan Fit Laboratory Presentation Contract v1

This is a forward-reconstruction presentation contract. It does not claim recovered historic UI or planning semantics.

## 1. Status and purpose

Stage 4C is:

- DEV-only
- fixture-backed
- local
- deterministic
- presentation-only
- limited to rendering accepted Stage 2B Assessment output alongside accepted Stage 4B Plan Fit output in the existing R1 Assessment Laboratory

Stage 4C is not implementation-authorised merely because the contract exists.

## 2. Explicit Stage 4C non-goals

Stage 4C must not add:

- production behavior
- normal product navigation
- routing
- persistence
- APIs
- network
- live system data
- editable plans
- reports
- exports
- downloads
- strategy creation
- free-form strategy input
- automatic strategy selection
- strategy inference
- scores
- ranking
- “best” results
- recommendation
- preference
- winner selection
- comparative advice
- material planning
- route planning
- colonisation staging
- changed Stage 2B assessment semantics
- changed Stage 4B Plan Fit semantics

## 3. Presentation boundary

The Stage 4C lab must:

- call accepted `evaluateAssessment` using the existing closed local Fixture, Lens kind, Lens value, and Carrier mode controls
- call accepted `evaluatePlanFit` using the resulting accepted assessment result plus one explicit selected strategy ID
- render returned Plan Fit values without deriving, rewriting, sorting differently, or recalculating them
- never call a state resolver or calculate carrier effects itself
- never construct a Plan Fit result manually
- keep lens context-only
- retain `compare_both` scenario order exactly: `no_carrier`, then `carrier_available`

## 4. Fifth closed selector

Stage 4C may add exactly one new closed local selector:

- label: `Strategy`
- id: `r1-strategy-select`
- default value: `baseline_local_strategy`
- exact options:
  - `baseline_local_strategy`
  - `remote_logistics_strategy`

The existing four selectors and their IDs, option values, defaults, semantics, and order must remain unchanged.

Strategy selection is explicit local context only. It must not be inferred from fixture, assessment state, carrier mode, or lens.

The UI must display plain language that strategy selection is not a recommendation, ranking, “best” result, or automatic choice.

## 5. Required neutral Plan Fit presentation

For every rendered Plan Fit scenario, display:

- carrier mode
- Assessment state
- Plan Fit state
- selected strategy ID
- selected strategy revision
- selected strategy fixture provenance
- deterministic reasons

For each reason, display:

- reason ID
- reason kind
- neutral summary
- blocking boolean
- related requirement IDs
- related evidence IDs

The UI may group Assessment and Plan Fit output beneath the same scenario section, but it must visibly distinguish Assessment state from Plan Fit state.

For `compare_both`, it must visibly preserve the two scenario sections in fixed order.

The exact remote fixture case must visibly preserve:

1. `no_carrier`
   - Assessment state: `conditionally_supported`
   - Plan Fit state: `provisional_plan_fit`
   - non-blocking `dependency:remote_logistics`

2. `carrier_available`
   - Assessment state: `supported`
   - Plan Fit state: `provisional_plan_fit`
   - no `dependency:remote_logistics`

The UI must not describe either scenario as preferred, better, recommended, viable, or best.

## 6. Vocabulary restrictions

The Stage 4C presentation must not render or introduce:

- score
- rank
- best
- recommend
- recommendation
- preference
- winner
- desirability
- traffic-light language
- comparative recommendation wording

Strategy and Plan Fit are permitted as neutral domain labels solely within this DEV-only lab presentation.

## 7. Future implementation boundary

A later Stage 4C implementation PR may change only:

- `docs/ai/CURRENT_STAGE.md`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.tsx`
- `frontend-v2/src/lab/r1-assessment-lab/R1AssessmentLabApp.test.tsx`

It must not modify:

- any Stage 2B core file
- any Stage 4B core file
- `App.tsx`
- `main.tsx`
- routes
- providers
- stores
- APIs
- stylesheets
- package or lock files
- build or test configuration
- production assets
- deployment configuration

## 8. Later implementation tests and evidence

Require a later Stage 4C implementation to prove:

- existing four controls remain intact
- exactly one fifth Strategy selector exists
- its options and default are exact
- changing strategy changes only Plan Fit presentation, not Assessment results
- changing only lens changes only displayed lens context and does not change Assessment or Plan Fit scenario output
- remote `compare_both` output has exact scenario order and the exact accepted Stage 2B/Stage 4B state-and-reason pairing
- no strategy is inferred
- no invalid evaluator inputs are exposed through the UI
- no forbidden output key or forbidden visible term is introduced
- existing Stage 2B evaluator tests and Stage 4B tests remain unchanged regression gates
- existing Stage 3B UI tests are updated only where the addition of the authorised fifth selector requires it
- typecheck, lint, build, full tests, and production artifact scans pass
- deployable `JS/CSS/HTML` artifacts contain none of the existing DEV-only R1 identifiers and none of:
  - `baseline_local_strategy`
  - `remote_logistics_strategy`
  - `no_plan_fit`
  - `blocked_plan_fit`
  - `provisional_plan_fit`

## 9. No implementation authorisation

Stage 4C code cannot begin until this contract is independently reviewed and the owner separately accepts the reviewed contract and explicitly authorises the bounded Stage 4C implementation.

No deployment is authorised.
