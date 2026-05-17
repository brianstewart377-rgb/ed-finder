# Stage 10A - Build Plan Structure Picker / Body Layout UX Feasibility

## Executive Summary

Stage 10A maps how ED-Finder can make manual colony planning more visual without changing mechanics or copying RavenColonial's construction logistics workflow.

The current Colony Planner already has the right safety boundaries: users enter a dedicated workspace, generate Suggested Builds only by explicit action, edit an in-memory Build Plan, run Preview only by explicit action, and then review Observed Evidence / Validation as passive later steps. The weak point is the manual Build Plan editing surface. It is still mostly a flat form list, so users cannot quickly see where placements sit in the system, which body owns which structure, or how a facility choice affects location, CP, economy, and risk before Preview.

Recommendation:

- Stage 10B should be a low-risk frontend-only visual improvement: add an optional body-grouped Build Plan view beside the existing list editor.
- Keep the current flat `BuildPlanEditor` as the canonical editing surface for compatibility.
- Group existing placements by assigned body, show unassigned placements clearly, and render compact badges for primary port, allowed location, tier, economy, CP gives/needs, confidence, and warnings when data exists.
- Defer the full structure picker / variant table until Stage 10C because current frontend facility templates do not expose all RavenColonial-style comparison fields.
- Do not add hauling/material totals, carrier stock, trip estimates, commodity progress, saved builds, accounts, journals, automatic learning, or any mechanics mutation.

Stage 10A is a feasibility/design/report stage only. It does not implement UI behaviour.

Stage 10B implementation note:

- Stage 10B followed this recommendation by adding a body-grouped Build Plan visual view.
- The existing flat/list `BuildPlanEditor` remains the detailed editing surface.
- The List/Body toggle is local UI state only and is not persisted.
- No backend mechanics, scoring, optimiser generation/ranking, validation/review behaviour, Search Tuning behaviour, persistence, auto-run, auto-generate, auto-load, or hauling/material tracking changed.
- Stage 10C evolved the body readout into Layout view with a compact plan summary, body-level layout cards, primary-port status, warning chips, and visible CP generated/needed totals.
- Stage 10D made Layout view locally interactive with read-only selected-body and selected-placement details. Users can inspect a body or placement, see warnings and next-action guidance, and then use List view for any edits.
- Stage 11B deepened this visual readout with card-level readability, stronger selection emphasis, clearer detail grouping, and clearer workflow hierarchy between planning steps and later-step panels.
- Stage 11A began the Colony Planner visual redesign foundation with stronger planning hierarchy, cleaner planner copy, improved workflow signposting, and clearer later-step framing for Observed Evidence and Validation.
- Spansh import was investigated in Stage 10C and remains a backend-supported/manual-refresh follow-up, not a frontend direct import or silent overwrite workflow.
- The full structure picker/table remains deferred beyond Stage 10D.

## Reference Materials

- ED-Finder UI / UX Discussion Tracker maintained from user discussion.
- RavenColonial screenshots discussed by user: hauling tracker, colony builder/map, structure picker dropdown, and structure picker table.
- `docs/colonisation-redesign/stage-8a-colony-planner-ux-prep.md`
- `docs/colonisation-redesign/stage-9b-dedicated-colony-planner-workspace-feasibility.md`
- `docs/colonisation-redesign/simulation-preview-ui-architecture.md`
- `docs/colonisation-redesign/engine-roadmap.md`
- Current repo code in `frontend-v2/src/features/colony-planner/` and `frontend-v2/src/features/system-detail/simulation-preview/`
- Current backend models and simulation/optimiser data structures under `apps/api/src/`

The UI / UX Discussion Tracker is not currently present as a committed repo file, so this stage uses the tracker summary supplied by the user as required source material.

## Current Build Plan Editor

The current dedicated Colony Planner workspace is `#colony-planner/system/{id64}`. `ColonyPlannerWorkspace.tsx` loads `SystemDetail` through `useSystemDetail(id64)` and renders `SimulationPreviewPanel`, which wraps the reusable `SimulationPreview` planner composition.

The current flow is:

1. Finder or Advanced Search Tuning.
2. `Evaluate in Colony Planner`.
3. Dedicated workspace.
4. Suggested Builds.
5. Build Plan.
6. Preview Result.
7. Observed Evidence.
8. Validation / Review Guidance.

Current Build Plan ownership:

- `SimulationPreview.tsx` owns composition, facility-template loading, simulation summary loading, planner hooks, explicit Preview execution, Suggested Builds, Preview Result, Observed Evidence, and Validation.
- `useSimulationPreviewPlan.ts` owns target archetype, start mode, recommended plan loading, optimiser candidate loading, and plan replacement signalling.
- `usePlacementEditor.ts` owns placement array editing: add, update, remove, move, resequence, and primary-port exclusivity.
- `BuildPlanSection.tsx` renders start modes, plan status, target archetype selector, add button, helper copy, empty state, and `BuildPlanEditor`.
- `BuildPlanEditor.tsx` renders one card per placement with facility dropdown, body dropdown, primary-port checkbox, move up/down, remove, and chips.

Current placement shape:

- `facility_template_id: string`
- `local_body_id?: string | null`
- `is_primary_port?: boolean`
- `build_order: number`

Current facility template fields exposed to the frontend:

- `id`
- `name`
- `category`
- `tier`
- `economy`
- `is_port`
- `is_support_facility`
- `allowed_location`
- `pad_size`
- `confidence`
- `notes`
- `yellow_cp_generated`
- `green_cp_generated`
- `yellow_cp_cost`
- `green_cp_cost`

Current body data exposed to the frontend through `SystemBody`:

- `id`
- `name`
- `subtype`
- `body_type`
- `distance_from_star`
- `is_landable`
- `is_terraformable`
- `is_earth_like`
- `is_water_world`
- `is_ammonia_world`
- bio/geo signal counts
- star-specific fields that are filtered out for simulation bodies

The editor can already know before Preview:

- facility name, category, tier, economy, allowed location, pad size, confidence, notes
- CP generated/cost fields from the facility template
- whether a selected template is a port/support facility
- current build order
- current primary-port flag
- assigned body or missing body assignment
- body type/subtype/landability/terraforming/water-world style metadata
- whether the current Preview has not run, is running, is stale, or matches the current Build Plan

Only available after Preview:

- final score, composition score, buildability score
- CP final/spent/generated aggregates and CP timeline
- CP repair suggestions
- economy composition/order/stack
- per-port economy state and influence ledger
- topology and slot fit warnings
- service unlock state
- strengths, warnings, recommendations
- observed-vs-predicted summaries
- validation/review comparison output

Missing for a full RavenColonial-style picker/table/body layout:

- exposed variant family metadata separate from the current template name/id
- stable variant display names such as the RavenColonial examples
- pre-selection validity result for a specific facility/body pair
- structured invalid/warning reasons before adding a placement
- frontend-visible prerequisite detail beyond template notes and Preview warnings
- stat impact columns for population, max population, security, wealth, technology, standard of living, and development
- material/commodity requirements and hauling effort
- selected-site construction/progress state
- saved plan/project state

## RavenColonial-Inspired UX Lessons

### 1. Body-based build map

RavenColonial makes the system layout legible by grouping structures under bodies. ED-Finder should borrow that planning clarity: bodies become visual containers, assigned placements appear under the correct body, and unassigned placements appear in a needs-attention bucket.

ED-Finder should not copy RavenColonial's exact map styling. The ED-Finder version should use the existing Colony Planner visual language: compact dark panels, orange/cyan/silver badges, warning gold for needs-attention states, and explicit Preview/stale copy.

### 2. Structure picker with filters

The RavenColonial picker shows Both / Orbital / Surface filtering, grouped structures, visible variants, and CP indicators near the choice. ED-Finder should adopt this direction later, but it needs a staged approach. The current dropdown is safe and simple; replacing it with a richer picker should wait until data availability and tests are stronger.

### 3. Structure picker table

The RavenColonial table makes comparison easy by exposing validity, pad, location, tier, needs/gives CP, economy influence, stat impact, and score. ED-Finder can support a subset now from existing template data, but several columns require backend/catalogue enrichment or Preview-derived data.

The haul/material column should be explicitly deferred. RavenColonial is already strong at execution/logistics. ED-Finder should not clone commodity demand, carrier stock, deficit, progress, or trip tracking.

### 4. Selected site / placement card

The selected placement should show structure, body, allowed location, status, primary-port role, CP/economy impact, confidence, and quick actions. ED-Finder already has most of this information in the flat editor, but it is not arranged spatially.

### 5. Right-side planner summary

RavenColonial's right-side summary shows project status and compact consequences. ED-Finder should eventually add a planning summary that answers: target archetype, placement count, primary port, unassigned count, Preview status, stale state, CP risk, economy focus, warnings, and next action.

### 6. Inline warnings

Warnings should appear near the thing the user can fix: unassigned body warnings near the unassigned group, invalid location warnings near a placement, primary-port warnings near the primary card, and stale Preview warnings near Build Plan status.

## ED-Finder Product Boundary

ED-Finder should own the planning/intelligence layer:

- Which system is promising?
- What build plans make sense?
- Which structure variants are valid?
- What does this placement affect?
- What are the likely CP/economy/buildability risks?
- What should the user tweak before Preview?
- What does Preview predict?
- What evidence later confirms or challenges the prediction?

RavenColonial should remain the stronger execution/logistics layer:

- What commodities are needed?
- Which carrier has stock?
- How many hauling trips remain?
- What has been delivered?
- Which construction projects are active?

ED-Finder may later support handoff/export if a clear integration path exists, but it should not duplicate the hauling/material tracker.

## Body-Based Build Plan Layout Proposal

Keep the existing flat list as the detailed editor and add a visual body-grouped view.

Recommended first implementation:

- Add a local, non-persisted view toggle in `BuildPlanSection`: `List view` and `Body view`.
- Default to List view in Stage 10B to avoid surprising existing tests and users.
- Body view groups placements by `local_body_id`.
- Placements with `null`, empty, or unknown body IDs appear in `Unassigned / needs body`.
- Each body group shows body name, body type/subtype, landable/terraformable/water-world tags, and placement count.
- Each placement card shows order, facility/template name, primary-port badge, allowed-location badge, tier, economy, category/role, CP gives/needs, confidence, and missing-template/body warnings.
- Body view can expose low-risk move/remove actions, but detailed edits remain in List view.
- Add clear copy: `Use List view for detailed editing.`

Unassigned placements:

- Should be visible, not hidden.
- Should appear after assigned bodies.
- Should warn that Preview should not be trusted until body assignment is reviewed.

Primary port:

- Show a strong `Primary port` badge on the placement card.
- If no primary port exists, show a summary warning in a later stage.
- If multiple primary ports somehow exist, do not crash; show the badge wherever the data says true and consider a later validation warning.

Preview/stale state:

- Reuse existing Build Plan status copy.
- Body view toggle must not run Preview, generate Suggested Builds, load a build, or mutate evidence/validation.

Migration path:

1. Stage 10B: body-grouped readout using existing data.
2. Stage 10C: richer picker/table for structure selection.
3. Stage 10D: planning summary and inline pre-preview warnings.
4. Later: optional handoff/export feasibility, not logistics cloning.

## Structure Picker / Variant Table Proposal

The future picker should replace only the facility-selection interaction, not the whole Build Plan flow.

Recommended interaction:

- Start with a row-level `Change structure` action from List view.
- Open a focused picker panel/popover or modal for that placement.
- Include Both / Orbital / Surface filters.
- Group by category, economy, and facility family where possible.
- Keep invalid options visible with explanation rather than hiding them, so the user learns why a choice is blocked.
- Provide a compact card/list mode first, then an advanced table mode when data supports it.

Recommended table columns:

- Valid
- Structure / variant
- Location
- Pad
- Tier
- CP needs
- CP gives
- Economy influence
- Population
- Max population
- Security
- Wealth
- Tech
- Standard of living
- Development
- Score / suitability
- Warnings

Current data can support:

- structure name
- category/family at a coarse level
- orbital/surface/both allowed location
- pad size
- tier
- CP needs/gives
- economy
- confidence/estimated marker

Needs enrichment:

- variant family/name separation
- selected-body validity result before Preview
- prerequisite/warning reasons in a frontend-safe format
- population/max population and stat impacts
- suitability score independent of running Preview
- material/haul effort, if ever supported, should remain a handoff/export topic rather than an ED-Finder tracker clone

## Data Availability Audit

| desired UI field | available now? | source | missing data | likely stage |
|---|---|---|---|---|
| Facility name | Yes | `FacilityTemplate.name` / `/api/facility-templates` | None | 10B |
| Category/family | Partly | `FacilityTemplate.category` | Better family grouping and variant taxonomy | 10C |
| Variant name | Partly | Template `name`/`id` may encode it | Dedicated variant/family fields | 10C |
| Orbital/surface allowed | Yes | `FacilityTemplate.allowed_location` | Body-specific validity reason | 10B for display, 10C/10D for validation |
| Pad size | Yes | `FacilityTemplate.pad_size` | Consistent display labels | 10C |
| Tier | Yes | `FacilityTemplate.tier` | None | 10B |
| CP needs | Yes | `yellow_cp_cost`, `green_cp_cost` | Clear UX labels | 10B/10C |
| CP gives | Yes | `yellow_cp_generated`, `green_cp_generated` | Clear UX labels | 10B/10C |
| Economy influence | Partly | `FacilityTemplate.economy`; backend has `economy_effects` internally | Expose richer economy-effect values if needed | 10C/10D |
| Population | No for picker | Backend catalogue may have `stat_effects`, not exposed in `FacilityTemplateResponse` | Expose stat effects safely | 10C+ |
| Max population | No | Not exposed to frontend picker | Catalogue enrichment / API exposure | 10C+ |
| Security | No | Backend catalogue may have stat effects, not exposed | Catalogue/API enrichment | 10C+ |
| Wealth | No | Backend catalogue may have stat effects, not exposed | Catalogue/API enrichment | 10C+ |
| Tech | No | Backend catalogue may have stat effects, not exposed | Catalogue/API enrichment | 10C+ |
| Standard of living | No | Backend catalogue may have stat effects, not exposed | Catalogue/API enrichment | 10C+ |
| Development | No | Backend catalogue may have stat effects, not exposed | Catalogue/API enrichment | 10C+ |
| Prerequisite | Partly | Backend template has `prerequisites`; frontend only gets `notes` | Expose structured prerequisites | 10C/10D |
| Validity for selected body | Partly | Backend domain has placement validation helpers; frontend has body/template fields | API/client validation contract | 10C/10D |
| Warning text | Partly | Preview warnings after explicit run; template notes before run | Pre-preview placement warnings | 10D |
| Material/haul effort | No | Not in current ED-Finder frontend planning data | Explicitly deferred / possible handoff only | Deferred |
| Score/suitability | Partly | Preview result and optimiser ranking after explicit actions | Pre-selection score would need a separate design | 10C+ |

Conclusion: Stage 10B can be frontend-only if it focuses on a body-grouped visual readout using existing data. A full structure picker/table likely needs at least frontend component work plus possible backend/catalogue exposure for variants, prerequisites, stat effects, and pre-selection validity.

## UX Scope Options

### Option 1 - Low-risk picker polish

Improve current dropdown labels, add simple filters, and add helper badges.

Pros:

- Smallest code change.
- Keeps the current editor intact.
- Can use existing template fields.

Cons:

- Does not solve the biggest spatial clarity issue.
- Still feels like a form rather than a planner.

Data requirements:

- Existing frontend template fields.

Complexity:

- Low.

Recommended stage:

- Possible minor part of Stage 10C, not the main Stage 10B win.

### Option 2 - Structure picker table

Add a table-like picker with filters, visible variants, CP/location/pad/economy columns, and invalid-state display.

Pros:

- Moves closest to RavenColonial's comparison strength.
- Makes facility selection more informed.

Cons:

- Larger interaction change.
- Needs better data for variants, prerequisites, stat effects, and validity reasons.
- Higher test surface.

Data requirements:

- Existing fields for a small first pass; enriched catalogue/API for the full table.

Complexity:

- Medium to high.

Recommended stage:

- Stage 10C after the body-layout pass.

### Option 3 - Body-grouped Build Plan

Group current placements by body, show cards/badges, and keep List view for edits.

Pros:

- Directly addresses spatial planning clarity.
- Uses existing placement, body, and template data.
- Low backend risk.
- Does not replace the editor.
- Easy to test for passivity.

Cons:

- Does not improve structure selection yet.
- Some warning/validity logic remains post-Preview or deferred.

Data requirements:

- Existing frontend data is enough.

Complexity:

- Low to medium.

Recommended stage:

- Stage 10B.

### Option 4 - Full visual planner

Body-grouped layout, structure picker/table, selected-site card, and right-side summary in one stage.

Pros:

- Biggest product leap.
- Strongest visual planning result.

Cons:

- Too broad.
- Higher risk of accidental mechanics or workflow changes.
- Harder to preserve explicit-action boundaries.

Data requirements:

- Existing data plus backend/catalogue enrichment.

Complexity:

- High.

Recommended stage:

- Not recommended as one stage. Split across 10B/10C/10D.

## Recommended Stage 10B

Implement Option 3: Body-grouped Build Plan visual view.

Stage 10B should:

- Add `BuildPlanBodyView` as a focused presentational component.
- Add a local List/Body toggle in `BuildPlanSection`.
- Default to List view for compatibility.
- Render existing placements grouped by body.
- Render unassigned/unknown-body placements in an explicit warning group.
- Show facility/template badges from existing data only.
- Keep `BuildPlanEditor` as the canonical detailed editor.
- Keep Preview, Suggested Builds, Observed Evidence, and Validation passivity boundaries.
- Update docs to say this is a visual planning readout, not construction logistics.

Stage 10B should not:

- Implement the full structure picker/table.
- Add saved builds.
- Add material/hauling/trip tracking.
- Change optimiser generation/ranking.
- Change Preview scoring, CP, economy, services, buildability, Search Tuning, Observed Evidence, or Validation.
- Auto-run Preview.
- Auto-generate or auto-load Suggested Builds.

## Tests Needed For Stage 10B

Frontend tests should cover:

- Body view groups placements by assigned body.
- Unassigned placements render in `Unassigned / needs body`.
- Placement cards show build order and facility name.
- Primary port badge appears.
- Body tags/metadata render when available.
- Missing body/template data does not crash.
- Toggle switches between List view and Body view.
- List view still renders the existing `BuildPlanEditor`.
- Body view shows `Use List view for detailed editing` or equivalent.
- Zero placements still show the existing empty state.
- Toggling views does not call `simulateBuild`.
- Toggling views does not call `fetchOptimiserCandidates`.
- Existing optimiser candidate load and stale-preview tests still pass.

Do not use brittle full snapshots.

## Deferred Work

- Full structure picker/table.
- Variant/family taxonomy and variant-aware grouping.
- Frontend-visible structured prerequisites.
- Pre-preview placement validity API or helper.
- Stat-impact columns for population, max population, security, wealth, technology, standard of living, and development.
- Right-side planner summary.
- Saved builds.
- Construction progress tracking.
- Commodity/material requirement calculation.
- Carrier stock, surplus/deficit, progress bars, and hauling trip estimates.
- EDMC/journal ingestion and external data ingestion, likely Stage 11A or later.
- Optional RavenColonial handoff/export feasibility if a real integration path exists.

## Final Recommendation

ED-Finder should move visually closer to RavenColonial's planning clarity without cloning RavenColonial's execution/logistics product. The safest next step is a Stage 10B body-grouped Build Plan view: bodies as containers, placements as visual cards, compact badges for known impacts, explicit unassigned warnings, and the existing list editor preserved for detailed edits.

This gives users a clearer spatial understanding of the Build Plan while keeping ED-Finder as the planning/intelligence layer and leaving hauling/material execution to RavenColonial or a later handoff.

Stage 10C confirms the next safe step after 10B: strengthen the body-grouped readout into a graphical Layout view and document Spansh import as a backend/manual-refresh follow-up. The structure picker/table, variant comparison, and external system-layout import workflow remain separate future stages.

## Stage 11B - Layout Cards, Detail Panel, and Workflow Hierarchy Polish

Stage 11B implemented the first deep visual polish for the Colony Planner readout surface only.

Implemented outcomes:

- Continued focus on Stage 11A foundations: dedicated planner path, List view as editing surface, Layout view as read-only planning surface.
- Added stronger card-level clarity in `BuildPlanBodyView.tsx` for body groups and placement cards (including concise grouping headers, clearer title/metadata separation, and stronger selected-state indicators).
- Improved `BuildPlanLayoutDetailPanel.tsx` detail grouping, summary/body/placement hierarchy, and read-only guidance.
- Improved `ColonyPlannerSectionNav.tsx` so Suggested Builds → Build Plan → Preview Result is visually primary and Observed Evidence / Validation are clearly secondary later-step context.
- Left all mechanics untouched: no scoring changes, no mechanics mutation, no auto-preview/generation behaviour.

Deferred beyond Stage 11B:

- Further map-like planning visualisation and deeper body/structure spatialization.
- Structure picker/table interaction polish beyond the current layout-readout baseline.
- New execution/logistics features (hauling, carrier stock, trip estimates, commodity requirements).

## Stage 11D - Reviewer-Driven Visual Hierarchy Refinement

Stage 11D continues the low-risk visual pass by consolidating planner-copy hierarchy for the Colony Planner path:

- Confirmed `Suggested Builds -> Build Plan -> Preview Result` as the visible primary flow.
- Kept `Observed Evidence` and `Validation` explicitly as later steps.
- Preserved `List view` as the canonical editing surface and `Layout view` as readout-only.
- No simulator/optimiser/validation side effects introduced through layout interactions.

## Stage 11E - Colony Planner Micro-Polish and Copy Hardening

Stage 11E hardens interaction clarity and terminology across the Planner workflow surface without mechanics changes.

- Added final copy normalization for workspace/header/nav sections and layout guidance (`Use List view to edit`, `Planning workspace` path visibility).
- Reconfirmed no-preview and no-suggested-build mutation behavior for layout selection, view toggles, and copy-driven state.
- Preserved separate keyboard-accessible body and placement controls in Layout view.

## Stage 11F - Micro-Polish and QA Guardrails

Stage 11F is a narrow follow-up to the interaction/accessibility hardening in Stage 11E.

- Reaffirmed the existing `List view` as the canonical editing surface and `Layout view` as a read-only planning readout.
- Kept the primary workflow visible as `Suggested Builds -> Build Plan -> Preview Result` and kept later-step framing for `Observed Evidence` and `Validation`.
- Preserved all existing interaction constraints: no preview auto-run and no Suggested Builds auto-generation/load from layout interactions.
- Kept keyboard/accessibility behavior for body and placement interactions intact.

## Stage 11G - Workflow Label Consistency and Header Micro-Polish

Stage 11G is a small mechanics-safe polish pass focused on planner-label consistency.

- Synchronized planner header and section labels to avoid mismatched terminology.
- Reduced redundant phrase variants so users see a single, predictable set of workflow labels.
- Preserved no-side-effect boundaries and read-only/read-write separation.

## Stage 11H - Layout Import State Reset Guardrail

Stage 11H addresses a residual quality-of-life issue in the planning surface.

- Added a system-scoped reset so stale layout-import status messages (running/error/result) are cleared when switching systems.
- Kept the behavior passive: no layout-import side effects are introduced beyond the existing manual layout import action.
- Preserved strict separation between layout-import status and planner build/editing behavior.

Chronology note:

- Stage 11F happened before Stage 11G, and Stage 11H follows Stage 11G.
