# Stage 8A - Colony Planner UX Backlog

Stage 8A should make Colony Planner easier to find, understand, and act on. Stage 7E does not implement this work; it captures the pre-implementation sense check so the next stage starts from a clear problem statement.

## Problem Statement

Colony Planner currently works as a system-detail planning surface, but the user path is still too buried and the first successful preview can feel under-explained. Users need clearer entry into suggested builds, clearer feedback after editing economies/buildings, and a more obvious next step after Simulation Preview.

## User-Raised UX Issues

- Colony Planner feels buried inside system detail.
- Simulation Preview is not self-explanatory enough.
- Adding an economy/building can feel like nothing happened.
- Preview output can feel minimal relative to the amount of setup.
- There is no obvious next step after running Preview.
- Suggested builds should probably be the primary path.
- Starting blank should remain available, but secondary and advanced.

## Source Materials To Inspect

- Uploaded DaftMav spreadsheet.
- Elite Dangerous colonisation Mega Guide.
- Current `frontend-v2/src/features/system-detail/simulation-preview/` flow.
- Existing recommended-build, optimiser-candidate, validation, and observed-evidence panels.

## Likely Scope

- Make the recommended-build path the primary starting point when available.
- Keep blank plan creation as an explicit advanced path.
- Clarify what Simulation Preview did after a run and what changed after edits.
- Improve next-step guidance after preview: review CP, economy alignment, risks, and candidate alternatives.
- Surface primary port, CP tiers, T2/T3 port order, hauling effort, dependencies, economy alignment/contamination, and orbital-vs-planetary tradeoffs in user-facing language.
- Consider whether Colony Planner needs a more direct entry point from system detail or search-result handoff.

## Strict Non-Goals

- Do not change backend simulation scoring as part of UX work.
- Do not change optimiser candidate generation or ranking without a separate mechanics stage.
- Do not make Search Tuning feed validation/review evidence into ranking.
- Do not auto-run Simulation Preview from Search Tuning handoff.
- Do not remove the blank-plan path.

## Risks To Check Before Implementation

- `SimulationPreview.tsx` already has many adjacent concerns: build-plan editing, recommended plans, optimiser candidates, preview results, observed evidence, and validation. Stage 8A should avoid making one component own more workflow state.
- Recommended builds and optimiser candidates are separate concepts; the UI should not blur "recommended build loaded" with "candidate generated".
- Candidate generation can run lightweight previews internally, while the main Simulation Preview remains explicitly user-run. Copy must keep that distinction clear.
- Validation and observed evidence are passive advisory layers; they must not feed back into Search Tuning, candidate ranking, or simulation scoring.
- Editing placements should make stale preview state obvious and should not imply that changes have been simulated before the user runs Preview again.
