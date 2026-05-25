# Stage 17N.3-A Guided Planner Quality Contract

Date: 2026-05-25

This stage audits the existing Advanced Planner, Suggested Builds, optimiser,
recommended-build, and Simulation Preview flow. It defines the quality contract
that future Guided Planner presets must satisfy before ED-Finder presents
Light, Medium, High, or Maxed whole-system plans.

This is a repo-only architecture and test-contract stage. It does not connect
to production, run imports, deploy, change rating weights, change slot
prediction, redesign the Raven canvas, add natural-language AI, or wire the new
quality helper into live generation.

## Current Architecture

### Where Suggested Builds Are Generated

There are two generated-plan families today:

1. **Suggested Builds / optimiser candidates**
   - API route: `apps/api/src/routers/optimiser.py`
   - Generator: `apps/api/src/optimiser/candidate_generator.py`
   - Archetype rules: `apps/api/src/optimiser/archetype_rules.py`
   - Facility selection: `apps/api/src/optimiser/facility_selection.py`
   - Ranking: `apps/api/src/optimiser/ranker.py`
   - Frontend consumer: `frontend-v2/src/features/system-detail/simulation-preview/optimiser/OptimiserCandidatePanel.tsx`

2. **Recommended Builds**
   - API route: `apps/api/src/routers/simulate.py`
   - Draft generator: `apps/api/src/recommendations/build_generator.py`
   - Body selection: `apps/api/src/recommendations/body_selector.py`
   - Ranking: `apps/api/src/recommendations/plan_ranker.py`
   - Frontend loading path: `SimulationPreview` and Build Plan helpers

The Raven canvas consumes the editable Build Plan plus optional projected
candidate placements. It does not generate candidates itself.

### Current Inputs

The optimiser candidate route uses:

- `system_id64`
- `target_archetype`
- `max_candidates`
- `preferred_body_ids`
- `allow_estimated_data`
- `run_preview`
- bundled or database facility catalogue
- `systems` and `bodies` rows
- body economy profile inference from `domain.colonisation_rules.profile_body`
- predicted slot totals from `ingest.slot_prediction.predict_system_slots`
- optional lightweight Simulation Preview summaries

Recommended Builds use:

- target archetype profile from `domain.colonisation_rules`
- selected body candidate
- facility catalogue
- slot confidence and total slots
- full Simulation Preview responses for generated drafts
- regional context as a light ranking component

### System-Wide vs Body-Local

The newer optimiser candidates can assign placements across multiple body
anchors, especially for `main_station`, `balanced_expansion`, and
`support_body` strategies. However, the generator still starts from one anchor
and cycles support placements across selected anchors. It does not yet create
an explicit whole-system role map with anchor, support, reserve, and avoided
bodies.

Recommended Builds are mostly body-local. They select one body and place the
generated draft on that body.

### Occupied-Slot Awareness

The current generation path understands predicted slots at a system-summary
level, but it does not consume the Stage 17N occupied-slot source-of-truth
contract. It does not yet know per-body confirmed occupied orbital/ground
slots, unresolved existing infrastructure, or inferred station/body association
confidence. The Raven canvas can display occupied-slot context, but the
candidate generator does not yet treat occupied slots as hard constraints.

### Prerequisite Awareness

The facility catalogue preserves prerequisites. Frontend manual planning shows
prerequisite warnings through `structurePlanningRules.ts`. Simulation Preview
models services, CP, topology, and economy consequences, but current candidate
generation does not explicitly validate that generated facilities include their
catalogue prerequisites before the candidate is displayed.

### Target Economy Discipline

Archetype rules define primary, secondary, support, and avoid economies. The
generator uses these rules when selecting anchors and support templates, but it
also has broad strategies such as `main_station`, `balanced_expansion`,
`support_body`, and `flexible_multirole` that can pull broad support pools.
There is no explicit post-generation contract that says:

- this is the primary economy
- this is the secondary economy
- this support economy is intentionally included
- this many unrelated economies is unsafe unless labelled mixed/risky

### Preview Usage

Suggested Builds can attach a lightweight preview summary when `run_preview` is
true. The full Simulation Preview response is intentionally not embedded in
the candidate response. Ranking uses candidate metadata and the lightweight
preview summary. Candidate generation itself does not search using full Preview
results.

Recommended Builds simulate generated drafts with the full Preview engine and
rank those simulated results.

### Why Economy-Soup Plans Can Happen

Economy-soup plans can happen because the current candidate generator:

- builds candidates from strategy-specific support pools before a final economy
  discipline check
- allows broad strategies to include many economy families
- ranks using preview summary and warning counts, not an explicit primary /
  secondary / support economy contract
- does not reject one-off support structures from unrelated economies
- does not require a user-facing explanation for mixed-economy or Maxed plans
- does not treat "target economy ignored" as a structural generation failure
- lacks a generated-plan validation layer that can return "No strong coherent
  plan found" instead of padding a candidate with weak structures

## Quality Gates: Where They Should Live

Quality gates should live in both backend and frontend, with different duties.

### Backend Gates

Backend gates should be authoritative for generated-plan eligibility:

- preset/count range contract
- target economy discipline
- economy-soup detection
- body assignment completeness
- occupied-slot and lane-capacity checks
- missing prerequisite warnings
- "No strong coherent plan found" decisions
- preview-required caveats and quality status

Backend validation should run after candidate generation and before candidates
are ranked or returned by a future Guided Planner endpoint. Stage 17N.3-A adds
`optimiser.plan_quality` as a pure helper, but does not wire it into live
routes yet.

### Frontend Gates

Frontend gates should remain presentation and safety affordances:

- show quality status, warnings, and suggested fixes
- compare candidates against the current Build Plan
- require explicit load/replace confirmation
- keep raw trace/evidence behind details
- prevent stale candidates from being silently copied
- keep Advanced Tools diagnostic/manual rather than the main guided workflow

Frontend checks may duplicate simple presentation safeguards, but should not be
the only thing preventing incoherent generated plans from being offered.

## Guided Plan Quality Contract

A generated plan is not user-facing unless it has a structured quality report.

### 1. Clear Plan Intent

Every generated plan must declare:

- preset: Light, Medium, High, or Maxed
- target economy or target economy pair
- optional support economy
- risk tolerance
- expected build count range
- whether Preview is required before trusting the recommendation

Plans that cannot satisfy the requested intent should return a clear lower-plan
recommendation or "No strong coherent plan found".

### 2. System-Wide Body Assignment

Every generated plan must include a body role map:

- main station / anchor body
- support bodies
- reserve bodies
- avoided bodies
- role labels such as Industrial Core, Refinery Support, Security Support,
  Civilian Support, Extraction Anchor, or Reserve Capacity

Every placement must have:

- body assignment
- lane assignment: orbital or ground
- reason for choosing that body and lane

Lane-flexible templates may remain editable in the manual Build Plan, but a
generated plan must pick a lane or warn that lane choice is unresolved.

### 3. Economy Discipline

Every generated plan must define:

- primary economy
- secondary economy
- optional support economy
- economies intentionally avoided
- whether the plan is focused, mixed, or risky

The default contract is:

- one primary economy
- one secondary economy
- at most one clearly justified support economy
- no uncontrolled mixing of five or more unrelated economy families
- no one-off spread across many economy families unless the plan is explicitly
  Maxed/mixed/risky and explains the tradeoff

Economy-soup output should be:

- `ok`: focused or intentionally explained
- `warning`: mixed, weakly dominant, or has one-off unrelated support
- `reject`: ignores requested economy or mixes too many unrelated economies
  without explanation

### 4. Slot and Occupancy Awareness

Generated plans must account for:

- predicted orbital slots
- predicted ground slots
- confirmed occupied orbital slots
- confirmed occupied ground slots
- planned slots
- projected slots
- unresolved existing infrastructure
- inferred station/body association confidence

Hard rule: do not plan into confirmed occupied slots. If capacity is unknown or
association is inferred, warn and lower confidence. If capacity blocks the
requested preset, return a smaller coherent plan or "No strong coherent plan
found".

### 5. Prerequisite Awareness

Generated plans must check catalogue prerequisites.

If a requested structure has prerequisites, the plan should normally include
the support structure first. If a prerequisite cannot be included, the plan
must warn, lower quality, and explain what remains manual.

Missing prerequisites should never be hidden inside raw mechanics trace.

### 6. Warnings and Risks

Generated plans must expose:

- capacity overflow
- unresolved infrastructure
- inferred station/body association
- missing prerequisites
- negative CP pressure
- economy contamination or conflict
- low slot confidence
- preview-required caveats
- data estimated from Spansh or inferred body facts

Warnings should be concise in the primary card. Raw trace and detailed evidence
belong behind details.

### 7. Explanation

Every user-facing plan must explain:

- why this body
- why this structure
- why this economy
- what prerequisites/support structures are included
- what tradeoffs exist
- what would make the recommendation unsafe

User-facing explanation must not expose raw internal IDs such as template IDs,
body IDs, archetype keys, or strategy keys when a label/name is available.

## Preset Contracts

The count ranges below are a starting contract for validation. A future
generator may tune them with real data, but it must keep the same principle:
respect user scale, do not pad with nonsense, and explain lower-plan outcomes.

| Preset | Count Range | Behaviour |
| --- | ---: | --- |
| Light | 2-5 structures | Small starter plan, low risk, minimal prerequisites, avoids filling too many slots, clear main station/support logic. |
| Medium | 6-10 structures | Coherent economy spine, moderate support structures, several bodies when justified, avoids economy soup. |
| High | 11-16 structures | Strong target-economy buildout, includes support/prerequisites, uses more slots, explicit risks and warnings. |
| Maxed | 17+ structures | Near-full whole-system plan that fills most useful slots, respects occupied slots, stays coherent, and explains any mixed-economy or contamination risk. |

Requested count rules:

- A "10 building plan" should produce close to 10 useful structures.
- A tolerance of roughly 20 percent is acceptable when capacity or catalogue
  constraints are explained.
- If capacity prevents the requested count, return a lower preset or "No strong
  coherent plan found".
- Do not add unrelated one-off structures just to hit a count.

## Advanced Planner UX Contract

No UI redesign is part of Stage 17N.3-A. Future UX should follow these rules:

- Advanced Tools are diagnostics/manual editing, not the primary guided
  workflow.
- Guided Planner should live beside or within the main Raven canvas workflow.
- Advanced Planner should not become a wall of text at the page bottom.
- Candidate output should be cards, comparison, warnings, and explanation.
- Raw trace, mechanics evidence, and debug ranking detail belong behind
  details.
- Loading a generated plan into the Build Plan remains explicit.
- Preview remains explicit unless a future stage deliberately adds an
  autosimulated guided workflow with clear loading states.

## Stage 17N.3-A Helper Contract

This stage adds a pure backend helper:

- `optimiser.plan_quality.validate_generated_plan_quality(...)`
- `optimiser.plan_quality.detect_economy_soup(...)`

The helper is not connected to production routes yet. It can evaluate:

- preset/count range fit
- requested count mismatch
- body assignment completeness
- lane ambiguity
- confirmed occupied-slot overflow when supplied with slot state
- missing catalogue prerequisites
- target economy discipline
- economy-soup status
- raw IDs in user-facing explanation
- unresolved infrastructure and inferred association warnings

## Stage 17N.3-B Prototype Generator

Stage 17N.3-B adds a backend/test-first prototype generator:

- `optimiser.guided_planner.GuidedPlanRequest`
- `optimiser.guided_planner.GuidedSystemContext`
- `optimiser.guided_planner.GuidedBodyContext`
- `optimiser.guided_planner.generate_guided_plan_report(...)`

The generator is intentionally not wired to a production route or frontend UI.
It accepts explicit system/body context, facility templates, occupied-slot
counts, target economies, preset, requested count, preferred bodies, avoided
bodies, and avoided economies. It returns a structured report with:

- preset and target economy pair
- title and summary
- lane-specific placements
- body roles
- warnings
- missing prerequisite report
- occupied-slot conflicts
- unresolved infrastructure warnings
- economy discipline result
- `plan_quality` quality-gate result
- explanation fields for body, structure, and tradeoff reasoning
- "No strong coherent plan found" response when capacity, catalogue, or body
  data cannot satisfy the requested preset

The prototype proves report shape and quality-gate behaviour without changing
the existing Suggested Builds route, Recommended Builds route, Simulation
Preview route, Raven canvas, slot prediction, ratings, imports, or production
data.

## What Is Missing Before Light/Medium/High/Maxed Are Safe

The future Guided Planner still needs:

- a public API model and route if/when the prototype graduates
- direct database context loading for occupied slots and station/body
  confidence, using `station_body_links`
- richer prerequisite planner that can resolve more non-literal catalogue
  prerequisite descriptions
- quality-gated candidate filtering before ranking/return
- comparison against current optimiser candidates and Recommended Builds
- richer Preview integration for candidate search, not just summary attachment
- frontend cards that show quality report, warnings, and suggested fixes
- persistence/export decision for generated guided plans

## Recommended Next Stage

Stage 17N.3-C should create a non-production backend API surface or service
adapter for the prototype report, still hidden from the frontend by default.
It should load body, slot, station/body association, and existing infrastructure
context from the database, then compare quality-gated output against current
optimiser candidates without changing the Raven canvas UI.
