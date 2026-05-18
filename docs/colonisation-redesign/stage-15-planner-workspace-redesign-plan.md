# Stage 15 - Topology-First Colony Planner Workspace Redesign Plan

## Executive Summary

Stage 15 should move Colony Planner from a vertically stacked explanation surface into a topology-first strategic planning workspace. RavenColonial is useful as workflow inspiration because it keeps the system hierarchy visible, lets users place structures against bodies/slots, keeps summary stats persistent, and makes editing local to the selected body. ED-Finder should not copy RavenColonial's visual style, assets, layout skin, or exact interaction patterns. The goal is a distinct ED-Finder workspace: dark ED-orange, brushed steel, prediction-led, validation-aware, and intentionally strategic.

The current implementation has already outgrown the "Simulation Preview panel inside System Detail" origin. The repo now has a dedicated `#colony-planner/system/{id64}` route, but that route still renders the same mostly vertical `SimulationPreview` composition. Stages 12-14 added useful logic and trust surfaces: structure picker, replacement comparison, guidance, Architect observation readout, topology readout, strategic topology guidance, Observed Evidence, and Validation review clarity. Those additions improved capability, but they also made the planner taller, denser, and more explanation-heavy.

Stage 15 should treat Colony Planner as a saved colony project workspace. Suggested Builds should become meaningful strategic plan starters that can prepopulate the workspace. Manual planning should happen directly through a body/tree topology view. Evidence and Validation should become project lifecycle surfaces rather than giant always-visible panels.

Non-goals for this documentation pass:

- No UI implementation.
- No backend schema changes.
- No route changes.
- No package changes.
- No RavenColonial cloning.

## A. Current State Audit

### Current Planner Architecture

The planner is split across an app-level route shell, a system detail modal, and a simulation-preview feature folder.

| Area | Current state | Relevant files |
|---|---|---|
| App shell | `AppInner` owns hash routing, search, watchlist, pinned, compare, colony tracker, FC planner, admin state, and renders the full page. | `frontend-v2/src/App.tsx` |
| Hash routing | `useHashRoute` parses ordinary modal child routes and the dedicated planner route. `#colony-planner/system/{id64}` maps to `route: 'colony-planner'` plus `plannerSystemId`. | `frontend-v2/src/hooks/useHashRoute.ts` |
| Planner workspace shell | `ColonyPlannerWorkspace` is a route wrapper that loads system detail and renders `SimulationPreviewPanel`. It is not yet topology-first. | `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx` |
| System Detail modal | Stage 15C has simplified this into an overview/discovery surface with a compact Colony Planner entry card. It no longer embeds buildability, regional position, Recommended Builds, Simulation Preview, Observed Evidence, Validation, or slot prediction planner panels. | `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` |
| Compatibility panel | `SimulationPreviewPanel` adapts a selected Recommended Build into `SimulationPreview`. | `frontend-v2/src/features/system-detail/SimulationPreviewPanel.tsx` |
| Planner composition | `SimulationPreview` owns facility template loading, simulation summary loading, plan hook, preview-run hook, Suggested Builds, Build Plan, Preview Result, Observed Evidence, and Validation. | `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx` |
| Build Plan | `BuildPlanSection` owns start modes, status, manual layout import state, archetype selector, List/Layout toggle, and either the list editor or body-group readout. | `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanSection.tsx` |
| Editable list | `BuildPlanEditor` remains the canonical edit surface. It owns structure picker open state and pending replacement state per row. | `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanEditor.tsx` |
| Read-only layout | `BuildPlanBodyView` groups placements by body, shows topology/strategic guidance, and supports selection only. | `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanBodyView.tsx` |
| Detail readout | `BuildPlanLayoutDetailPanel` is a sticky read-only detail panel for summary/body/placement selection. | `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanLayoutDetailPanel.tsx` |
| Topology helpers | Layout/topology helpers derive body-group readouts and strategic guidance from existing plan/body/template facts only. | `buildPlanLayoutUtils.ts`, `layoutTopologyUtils.ts`, `strategicTopologyGuidanceUtils.ts` |
| Architect readout | `ArchitectObservationPanel` and helpers distinguish unknown vs observed frontend context, but no persistence or editing exists. | `ArchitectObservationPanel.tsx`, `architectObservationUtils.ts` |
| Structure picker | The picker and replacement comparison are local to List view rows. Selection is explicit and non-mutating until Apply. | `StructurePickerTable.tsx`, `StructureReplacementComparison.tsx`, `structurePickerUtils.ts`, `structurePickerGroupingUtils.ts`, `structureReplacementDeltaUtils.ts` |
| Suggested Builds | Frontend Suggested Builds uses the optimiser endpoint and displays cards/details/comparison. | `simulation-preview/optimiser/*` |
| Recommended Builds | Older System Detail recommended-build cards still exist above the embedded planner and can open/copy into Colony Planner. | `RecommendedBuildsPanel.tsx`, `BuildPlanCard.tsx` |
| Observed Evidence | Manual evidence CRUD is in an always-visible in-page panel after Preview Result. | `simulation-preview/observations/*` |
| Validation | Compare/review panels are always rendered in-page after Observed Evidence when a preview exists. | `simulation-preview/validation/*` |
| Backend Suggested Builds | Current Stage 5 optimiser candidates are bounded heuristic plans. They can generate port-only candidates when no support facilities match. | `apps/api/src/optimiser/candidate_generator.py`, `apps/api/src/optimiser/ranker.py` |
| Backend Recommended Builds | Older recommended builds generate simple/balanced/advanced drafts from one selected body and catalogue support choices. | `apps/api/src/recommendations/build_generator.py`, `apps/api/src/recommendations/plan_ranker.py`, `apps/api/src/routers/simulate.py` |

### Current Data Flow

1. Entry points call `openColonyPlanner(id64)` or `openSystem(id64)`.
2. `#colony-planner/system/{id64}` loads `ColonyPlannerWorkspace`.
3. `ColonyPlannerWorkspace` calls `useSystemDetail(id64)`, which wraps `/api/system/{id64}`.
4. `SimulationPreview` fetches:
   - `/api/facility-templates` for structure catalogue.
   - `/api/systems/{id64}/simulation-summary` for suggested archetype, buildability, recommended order, and regional context.
5. `useSimulationPreviewPlan` owns the editable placements, target archetype, origin label, and manual edit state.
6. `useSimulationPreviewRun` owns explicit `/api/simulate/build` execution and stale/current preview status.
7. `OptimiserCandidatePanel` calls `/api/optimiser/candidates` only after the user clicks `Generate Suggested Builds`.
8. `BuildPlanSection` can call `/api/colony-planner/system/{id64}/import-layout` after the user clicks manual import.
9. `ObservedEvidencePanel` calls `/api/observations/facts` list/create/update/delete.
10. `ValidationPanel` calls `/api/observations/compare` and `/api/observations/review` after a preview result exists.

This flow is mostly safe and explicit. The problem is presentation: everything is stacked into one long page, and the "workspace" route does not yet introduce a different workspace model.

### Repeated UX Patterns

The current UI repeats the same workflow explanation in several places:

- `ColonyPlannerWorkspace` explains Suggested Builds -> Build Plan -> Preview Result.
- `ColonyPlannerHeader` repeats the same flow.
- `ColonyPlannerSectionNav` repeats the same flow.
- `BuildPlanSection` repeats the same flow.
- Start modes and empty states repeat the Suggested Builds/manual start choice.
- Observed Evidence and Validation each repeat passivity/advisory warnings.
- Layout view repeats "read-only, use List view to edit" across summary, body, placement, and next-action surfaces.
- System Detail has a `Colony Planner` CTA and, as of Stage 15C, no longer embeds the full planner below.
- Recommended Builds and Suggested Builds are two suggestion concepts in close proximity.

The repetition is understandable given prior safety stages, but it is now a major source of vertical bloat.

### Scroll Bloat Sources

High-impact sources:

- Before Stage 15C, System Detail rendered rating, system info, bodies, stations, exploration, buildability, regional position, Recommended Builds, embedded planner, slot predictions, external links, and actions in one modal. Stage 15C removed the planner stack from that modal path.
- The dedicated planner route still wraps a vertical Simulation Preview stack inside a panel.
- `BuildPlanSection` contains start modes, status, layout import, assumptions, target archetype selector, helper copy, List/Layout toggle, global hints, and either editor or layout readout.
- List view renders one large card per placement, and each placement can expand a structure picker and replacement comparison.
- Layout view renders summary, plan warnings, body cards, placement cards, topology readouts, strategic guidance, body guidance, and sticky detail.
- Observed Evidence includes intro copy, passivity notice, planning summary, create form, filters, backend summary, loading/error/list cards.
- Validation includes advisory copy, reminders, stale warning, summary, review guidance, warnings, assumptions, and comparison cards.
- Recommended Build cards are dense and include score, economy bars, selected body, regional context, build order, mechanics basis, caveats, assumptions, strengths, tradeoffs, decision explanation, score breakdown, and a planner button.

### Internal Or Dev-Facing Language To Hide Or Translate

Some terms are acceptable in developer docs but should be compacted or translated in the product UI:

| Current/internal wording | User-facing direction |
|---|---|
| optimiser, candidate, generated candidates | Suggested Builds, build suggestions |
| mechanics basis, mechanics trace, mechanics version | Why ED-Finder thinks this, rule notes, model version only in advanced details |
| assumptions | Planning assumptions or data limits |
| body_diversity, strategic_tags, tags | Body variety, useful body signals, strategic hints |
| confidence impact | Evidence confidence, review confidence, model confidence only when needed |
| contradicted | Differs from preview, needs review |
| prediction/predicted-only | Preview expected, not yet checked |
| observed facts | Observed Evidence |
| source of truth | Detailed preview, current model, or in-game check depending context |
| stage labels | Never show Stage 6/12/14 language in user UI |
| passive | Does not change this plan or scoring, preferably as tooltip/help text instead of repeated panels |
| stale | Needs new preview |
| unknown | Not observed, not assigned, or data unavailable, whichever is more specific |

The code can retain API and internal names where compatibility matters.

## B. Target UX Architecture

### Product Direction

ED-Finder should become a topology-first strategic colony planning workspace:

- The system body tree is the main navigation.
- Plan placements attach directly to bodies and future slots.
- Summary stats remain visible while editing.
- Warnings and unknowns are compact until expanded.
- Suggested Builds can prepopulate a saved workspace.
- Manual editing is local to selected bodies/slots.
- Preview, Evidence, and Validation are workspace modes/drawers tied to a saved project lifecycle.

### Dedicated Route

Near-term route:

- Keep `#colony-planner/system/{id64}` as the current app-safe route.
- Add project identity later as `#colony-planner/system/{id64}/project/{projectId}` or an equivalent state model.

Future route naming if the app moves beyond hash routing:

- `/system/:id64/planner` if system detail remains the parent information architecture.
- `/planner/:systemId` if Planner becomes a top-level workspace with recent projects.

Do not add a static top-level Planner tab until there is a recent-projects or system chooser experience.

### Layout Concept

Desktop target:

| Region | Purpose |
|---|---|
| Top workspace bar | System name, project name, status, save state, current target, actions. |
| Left topology tree | Stars, planets, moons, orbitals, ground slots, unassigned placements, project role labels. Primary navigation. |
| Center planning canvas/editor | Selected body/slot editor, placed structures, local add/replace controls, preview overlay where useful. |
| Right persistent summary | CP, economy/service preview summary, warning count, primary-port status, evidence/validation status, project status. |
| Bottom/drawer area | Preview, Evidence, Validation, Journal, and detailed mismatch views as modes/drawers. |

Mobile target:

- Top project bar remains.
- Body tree becomes a collapsible drawer or segmented "Bodies / Plan / Summary" shell.
- Right summary becomes a bottom sticky summary strip with an expandable drawer.
- Drawers replace side-by-side panels.

### Left Body/Topology Tree

The left tree should show:

- Stars as root/system context.
- Bodies ordered by orbital hierarchy and distance where hierarchy is known.
- Moons nested under parents when data supports it.
- Body badges: landable, terraformable, ELW/WW/AW, ringed, bio/geo, sparse data.
- Planned placements attached under the body.
- Orbital and ground slot groups when slot data is known.
- Unknown slot counts as compact badges, not paragraphs.
- Architect primary-port flag as `Architect flag: not observed` or `observed on slot/body`.
- Colony ship/initial presence as system-level or first-placement context.
- Unassigned placements as a first-class "Needs assignment" bucket.

Tree rows should be compact and scannable. Expanding a row should reveal local placements and slot context, not explanatory essays.

### Central Planning Canvas/Editor

The center should switch based on selection:

- System selected: project overview, build path, recommended next action.
- Body selected: body summary, local slots, placements on this body, local add structure action, role assignment.
- Slot selected: slot details, structure picker, replacement comparison, validation/evidence status for that slot.
- Unassigned bucket selected: drag/move/assign placements to bodies.
- Suggested Build loaded: show the imported topology plan and mark origin.

Manual editing should be local:

- Add structure to selected body/slot.
- Replace structure on selected placement.
- Move placement to another body/slot.
- Reorder build sequence through a compact sequence control.
- Keep primary-port state read-only unless it comes from an explicit model rule or future observed Architect data workflow.

### Right Persistent Summary Panel

The right panel should stay visible on desktop:

- Project status: unsaved draft, saved draft, previewed, needs observation, validation needs review.
- Target archetype and suggested strategic purpose.
- Placement count and assigned/unassigned count.
- CP summary: yellow/green generated/needed, pressure status.
- Economy/service preview summary from last Preview, if current.
- Warning stack: critical count, caution count, unknown count.
- Architect status: not observed, observed, conflicting, needs observation.
- Primary-port guidance: concise state and next action.
- Evidence status: observations recorded, unchecked checklist items.
- Validation status: no preview, no evidence, mostly confirmed, mixed, needs review.

Each row should open the relevant drawer or select the related tree node.

### Bottom/Drawer Panels

Large explanatory panels should move into modes:

- Preview drawer: detailed simulation result, economy/service panels, CP timeline, mechanics trace advanced details.
- Evidence drawer: project journal and manual observed evidence.
- Validation drawer: mismatch summary, comparison rows, review guidance.
- Suggested Build drawer: plan alternatives and comparison against current workspace.
- Structure drawer: picker/replacement details for selected body/slot.

Drawers should be closed by default unless the user explicitly opens the mode or needs to resolve a blocking issue.

### Compact Warning/Status System

Replace repeated paragraphs with:

- Badges: `Needs preview`, `Needs body`, `Architect not observed`, `CP pressure`, `Estimated data`, `Validation needs review`.
- Warning groups: `Placement`, `Topology`, `Preview`, `Evidence`, `Validation`.
- Click-to-expand details.
- A single "Needs observation" checklist rather than repeated Architect warnings.

### Contextual Structure Picker And Replacement Flow

Target flow:

1. User selects a body/slot.
2. User clicks `Add` or a placed structure's replace icon.
3. A structure drawer opens filtered to compatible structures first.
4. User can expand incompatible/estimated options.
5. Replacement comparison shows only changed fields by default.
6. Apply changes only the selected placement and marks Preview as needs refresh.

The existing picker/replacement logic can be reused, but it should move from row expansion into a body/slot-context drawer.

## C. System Detail Page Simplification

System Detail should become an inspection summary and planner entry point, not a second full planner.

Keep:

- System name, ID64, coordinates, population/colonisation state.
- Rating profile and compact top reasons.
- Compact body/station summaries with "open full bodies table" affordance if needed.
- Regional/buildability quick summary.
- Saved colony project summary if one exists.
- Current planner status: no project, draft, preview stale, needs observation, validation needs review.
- Primary action: `Open Colony Planner`.
- Secondary action: `Start new colony project` or `Open saved project`.
- Lightweight errors only.

Move out or collapse:

- Full embedded `SimulationPreviewPanel`.
- Full `RecommendedBuildsPanel` card grid.
- Full `SlotPredictionPanel`.
- Long body/station tables where summary is enough.
- Deep mechanics, assumptions, score breakdowns.

System Detail should answer:

- "Is this system worth inspecting?"
- "Do I already have a colony project here?"
- "Open the planner."

The Planner Workspace should answer:

- "What should I build and where?"
- "What have I checked in-game?"
- "Does the saved project still match the evidence?"

## D. Suggested Builds Redesign

### Current Problem

Suggested Builds and Recommended Builds can be too trivial:

- "Colony Ship only"
- "Colony Ship + one station"
- Port-only or minimal candidates generated when support facilities do not match.

These are technically safe fallback candidates, but they are poor product recommendations. They should not appear as first-class "Suggested Builds" unless explicitly labelled as a fallback/manual seed.

### Product Rules

Suggested Builds should require:

- A strategic purpose.
- Enough structure to be useful.
- A body/topology rationale.
- A preview/rank rationale.
- Clear tradeoffs.
- A one-click `Load into Planner Workspace` action.
- A manual build alternative.

### Quality Gate

Filter or demote candidates that fail usefulness thresholds:

| Gate | Recommended rule |
|---|---|
| Minimum content | Hide first-class suggestions with fewer than 3 meaningful placements, unless no alternatives exist. |
| Role coverage | Require at least one port/anchor plus at least one support function for normal suggestions. |
| Strategic purpose | Require a recommendation class such as `Primary-port starter` or `Industrial/refinery starter`. |
| Preview viability | Demote or hide candidates with very low final score, severe CP pressure, or no preview summary. |
| Body context | Prefer suggestions with assigned body and body rationale; place system-level suggestions in manual/fallback area. |
| Warning cap | Hide or demote suggestions with high warning count unless explicitly presented as experimental. |
| Duplication | Deduplicate not only identical placements but also near-identical trivial variants. |
| Confidence | Label estimated-data suggestions clearly and avoid ranking them above stronger observed/topology-backed suggestions without explanation. |

If all candidates fail, show:

- "No useful Suggested Builds yet."
- Why: missing catalogue support, insufficient body data, slot confidence too low.
- Actions: `Start manual plan`, `Import / refresh layout`, `Check Architect Mode`, `Try a broader target`.

### Recommendation Classes

Use user-facing classes instead of raw strategies/tags:

- Primary-port starter
- Main station candidate
- Industrial/refinery starter
- Tourism/agriculture starter
- Military/security stabiliser
- Balanced expansion
- Support-body plan
- Low-CP scout plan
- Service unlock support
- Expansion reserve

Internal strategy names (`balanced`, `pure`, `services_aware`, `low_cp`, `flexible_multirole`) can remain backend metadata but should not be the main card title.

### Card Content

Each suggestion should show:

- Strategic class.
- Short purpose: "Establishes a main station candidate with refinery support on A 2."
- Body placement summary.
- Structures count.
- CP pressure badge.
- Preview/rank confidence badge.
- Top reason.
- Top risk.
- `Load into Planner Workspace`.
- `Compare with current project`.

Avoid:

- Raw tags like `body_diversity`.
- "Candidate" as the main visible noun.
- Long score breakdown by default.
- "Source of truth" language.

### Load Into Workspace

Loading a suggestion should:

- Create or update an unsaved draft project.
- Preserve a suggestion origin field.
- Attach placements to bodies/unassigned nodes.
- Mark Preview as not run or stale until explicitly run.
- Never save to backend silently.
- Never claim the plan is in-game truth.

## E. Persistence Model

Persistence is essential because a project has a lifecycle: draft -> preview -> in-game observation -> validation -> revision. Without saved projects, Observed Evidence and Validation remain disconnected panels.

### Minimal Colony Project Model

```ts
type ColonyProject = {
  projectId: string;
  systemId64: number;
  systemName: string;
  projectName: string;
  status: 'draft' | 'previewed' | 'needs_observation' | 'validated' | 'needs_review' | 'archived';
  targetArchetype: string | null;
  strategicPurpose: string | null;
  placements: ColonyProjectPlacement[];
  bodyAssignments: ColonyProjectBodyAssignment[];
  bodyRoles: ColonyProjectBodyRole[];
  architectObservation: ArchitectObservationRecord | null;
  notes: ProjectNote[];
  suggestionOrigin: SuggestionOrigin | null;
  previewSnapshot: PreviewSnapshot | null;
  observedEvidenceRefs: string[];
  validationSnapshot: ValidationSnapshot | null;
  createdAt: string;
  updatedAt: string;
  schemaVersion: number;
};
```

```ts
type ColonyProjectPlacement = {
  placementId: string;
  facilityTemplateId: string;
  localBodyId: string | null;
  slotId: string | null;
  placementKind: 'orbital' | 'ground' | 'system' | 'unknown';
  isPrimaryPortPlanned: boolean;
  buildOrder: number;
  role: ColonyRoleId | null;
  notes: string | null;
};
```

```ts
type ColonyProjectBodyAssignment = {
  bodyId: string;
  roleIds: ColonyRoleId[];
  userDeclaredRoleIds: ColonyRoleId[];
  inferredRoleIds: ColonyRoleId[];
  notes: string | null;
};
```

```ts
type ArchitectObservationRecord = {
  state: 'not_observed' | 'observed' | 'conflicting';
  observedAt: string | null;
  source: 'manual' | 'imported' | 'unknown';
  primaryPortBodyId: string | null;
  primaryPortSlotId: string | null;
  orbitalSlotCount: number | null;
  groundSlotCount: number | null;
  notes: string | null;
};
```

### Frontend-Only First

Frontend-only first is the safer implementation path:

- Store draft projects in versioned local storage or IndexedDB.
- Use a repository-style adapter so backend persistence can replace storage later.
- Keep project IDs stable.
- Persist build plan placements, roles, notes, selected view mode, and preview/validation snapshots.
- Keep existing observed-facts backend untouched.

This proves the workspace lifecycle without premature backend/account work.

Frontend-only limitations to state clearly:

- Local to browser/device.
- Not suitable for account sync.
- Not a permanent source for shared projects.
- Export/import should be considered if backend persistence is deferred.

### Backend Persisted Later

Backend persistence should follow once the project model stabilises:

- `colony_projects`
- `colony_project_placements`
- `colony_project_roles`
- `colony_project_notes`
- `colony_project_snapshots`
- Optional join table between project and observed facts.

Do not rush backend tables before the topology workspace shape is tested.

### Evidence And Validation Snapshots

Observed Evidence can remain in the existing observed-facts API at first, keyed by system. The project should store references or filters:

- linked observation IDs when the user explicitly attaches evidence to the project.
- latest validation result snapshot for "what did this project last conclude?"
- preview fingerprint used for validation.

## F. Topology/Body-Tree Model

### Tree Nodes

```ts
type PlannerTreeNode =
  | StarNode
  | BodyNode
  | SlotGroupNode
  | SlotNode
  | PlacementNode
  | UnassignedNode;
```

Required concepts:

- Stars: root context and system hierarchy.
- Bodies: planets/moons with known scan metadata.
- Moons: nested when parent relationship exists; otherwise sorted as bodies with unknown parent.
- Orbitals: group node for orbital-capable/observed orbital slots.
- Ground slots: group node for surface-capable/observed ground slots.
- Unknown slots: explicit unknown capacity state.
- Planned placements: children under body/slot/unassigned nodes.
- Selected body/slot/placement: one workspace selection model.
- Architect primary-port flag: observation context, not user-declared truth.
- Colony ship/initial presence: system-level requirement or first placement indicator.
- Unassigned placements: first-class tree section.

### Unknown Slot Counts

Slot capacity should have explicit states:

- `unknown`: not observed.
- `estimated`: inferred from scan/topology model.
- `observed`: manually recorded or imported from a trusted future source.
- `conflicting`: project evidence disagrees.

Never invent exact slot locations from current data.

### Placement State

```ts
type PlannerPlacementState = {
  placementId: string;
  bodyId: string | null;
  slotId: string | null;
  facilityTemplateId: string;
  buildOrder: number;
  status: 'planned' | 'needs_body' | 'needs_slot' | 'built_observed' | 'mismatch';
  warnings: PlannerWarning[];
};
```

### Architect Primary-Port Flag

Rules:

- ED-Finder must not let users arbitrarily set primary port as confirmed truth.
- A future observation workflow can record what Architect Mode showed.
- Primary-port location is placement guidance, not a Build Point source.
- If the flagged slot is inconvenient, suggest a lighter outpost there and main station elsewhere.
- Do not say a poor primary-port location makes the system bad.

User-facing states:

- `Architect flag not observed`
- `Architect flag observed on body/slot`
- `Architect flag conflicts with current project`
- `Use as outpost candidate`
- `Main station planned elsewhere`

## G. Colony Role / Colony Planet Foundation

Roles should make the project strategic without changing game mechanics.

### Role Set

- Colony Anchor
- Main Station Body
- Primary Port Body
- Industrial Core
- Extraction Body
- Tourism/Agriculture Body
- Military/Security Body
- Support Body
- Expansion Reserve

### Role Dimensions

Each role should track:

- `planned`: assigned in the current project.
- `observed`: supported by in-game evidence.
- `inferred`: suggested from current placements/body data.
- `userDeclared`: explicitly chosen by user.

User-declared roles should win display priority. Inferred roles should remain advisory.

### Role Influence

Roles should influence:

- Guidance copy.
- Suggested Build classification.
- Warning prioritisation.
- Body tree grouping/filtering.
- Needs-observation checklist.
- Project summary.

Roles should not change:

- CP mechanics.
- Economy/service simulation rules.
- Buildability scoring.
- Optimiser ranking unless a later explicit stage introduces role-aware recommendation scoring.

## H. Observed Evidence And Validation Redesign

### Current Issue

Observed Evidence and Validation are correctly passive, but they are always visible in the planner stack. This makes them feel like mandatory form sections even when the user is still drafting.

### Target Project Journal

Create a project journal model:

- `Plan changes`
- `Preview runs`
- `Architect observations`
- `Manual evidence`
- `Validation runs`
- `Notes`

The journal should be a drawer or tab, not part of the primary editing canvas.

### Evidence Drawer

Evidence drawer should include:

- Compact evidence status header.
- Needs-observation checklist.
- Manual evidence form.
- Evidence list grouped by category.
- Architect observation capture when future storage exists.
- Link/attach evidence to selected body/slot/placement.

### Validation Review Tab/Drawer

Validation should show:

- Compact project-level status badge.
- Mismatch summary first.
- Rows grouped by category:
  - Matches plan
  - Differs from preview
  - Missing observation
  - Unknown/not checked
  - Needs manual review
- Filter by severity/status.
- Link each mismatch to tree/body/slot when possible.
- "What to check next" checklist.

### Compact Status Badges

Always-visible summary should collapse Evidence/Validation into badges:

- `No evidence`
- `3 observations`
- `Needs Architect check`
- `Validation not run`
- `Validation mixed`
- `2 mismatches`
- `Preview stale`

Clicking a badge opens the relevant drawer.

## I. Implementation Phases

### Stage 15A - Planner Workspace Report / Architecture Docs

Purpose:

- Document the topology-first product and technical plan.
- Ground the plan in current files and data flow.
- Define safety boundaries before implementation.

Files likely affected:

- `docs/colonisation-redesign/stage-15-planner-workspace-redesign-plan.md`
- `docs/colonisation-redesign/engine-roadmap.md`
- `docs/colonisation-redesign/simulation-preview-ui-architecture.md`

Implementation notes:

- Documentation only.
- No React/API/schema changes.

Tests:

- `git diff --check`
- No frontend build required if only docs change.

Safety boundaries:

- No code.
- No package changes.
- No backend persistence.

Explicitly deferred:

- All UI, API, persistence, and route implementation.

### Stage 15B - Dedicated Planner Route Shell V2

Current Stage 15B status:

- Implemented on the existing `#colony-planner/system/{id64}` route; no new route was added.
- `ColonyPlannerWorkspace.tsx` now renders a workspace-level shell with a compact system header, left topology/sidebar placeholder, central contained planner area, and right persistent summary/context panel.
- Existing `SimulationPreviewPanel` functionality remains available inside the central planning content area. Stage 15B does not redesign planner internals.
- The left rail is a read-only topology orientation placeholder for Stage 15D. It shows body counts, notable body rows where available, and an unassigned-placement placeholder without mutating plan state.
- The right rail is a persistent summary placeholder for project/planner status, Architect observation status, loaded body/station counts, workspace modes, and deferred-stage reminders.
- Focused workspace tests now cover shell rendering, existing planner availability, side-panel headings, and no preview/optimiser/import/validation/evidence side effects on load.

Purpose:

- Evolve the existing `#colony-planner/system/{id64}` route from a wrapper around vertical `SimulationPreview` into a workspace shell with topology/sidebar/summary regions.

Files likely affected:

- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- New `frontend-v2/src/features/colony-planner/*` shell components.
- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.test.tsx`
- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.integration.test.tsx`

Implementation notes:

- Keep existing route.
- Create layout regions but initially reuse current planner content in the center.
- Add responsive shell only; no behavior rewrite yet.
- Keep System Detail embedded planner until Stage 15C. Stage 15C has now completed that handoff by replacing the embedded planner stack with a compact entry card.

Tests:

- Route renders shell for valid id.
- Empty/loading/error states preserved.
- No `simulateBuild`, optimiser generation, validation, observation mutation, or import call on load.
- Mobile shell does not hide primary actions.

Safety boundaries:

- No mechanics changes.
- No Suggested Build generation changes.
- No persistence.

Explicitly deferred:

- Stage 15E: topology-local build editing.
- Stage 15G: saved colony project persistence.
- Stage 15H: Evidence/Validation drawers.

### Stage 15C - System Detail Simplification

Current Stage 15C status:

- Implemented in `frontend-v2/src/features/system-detail/SystemDetailModal.tsx`.
- System Detail is now an overview/discovery surface: Colony Planner entry card, rating profile, system info, bodies/stations/exploration summaries, external links, and existing modal actions.
- The full planner stack no longer renders inline on System Detail. Buildability, regional position, Recommended Builds, embedded `SimulationPreviewPanel`, slot prediction, Observed Evidence, and Validation are workspace-first surfaces.
- The entry card shows planner availability, system name/ID64, concise player-facing copy, a disabled friendly state when the workspace route cannot be opened, and the `Open Colony Planner` CTA wired to `#colony-planner/system/{id64}` through the existing app route handler.
- Recommended Builds are not generated or displayed on System Detail. The summary copy directs users to review Suggested Builds inside the Colony Planner.
- Error display is compact and friendly; raw backend strings are not surfaced in the System Detail modal.

Purpose:

- Make System Detail lightweight and make Planner Workspace primary.

Files likely affected:

- `frontend-v2/src/features/system-detail/SystemDetailModal.tsx`
- `frontend-v2/src/features/system-detail/SystemDetailModal.test.tsx`
- `frontend-v2/src/App.test.tsx`

Implementation notes:

- Replace embedded `SimulationPreviewPanel` with project/planner summary and CTA.
- Remove full Recommended Builds from System Detail without deleting the underlying components.
- Keep old planner, Recommended Builds, Evidence, and Validation internals available for the dedicated workspace and later migration stages.

Tests:

- System Detail still loads and closes.
- `Open Colony Planner` routes to workspace.
- No embedded planner render in default System Detail.
- Details actions from Finder/Search Tuning still open System Detail.
- No new preview/generation/fetch side effects are introduced by System Detail.

Safety boundaries:

- Do not delete planner internals.
- Do not change API contracts.

Explicitly deferred:

- Stage 15E: topology-local plan editing.
- Stage 15F: Suggested Builds quality gate and load-into-workspace flow.
- Stage 15G: saved project status/persistence summary on System Detail.

### Stage 15D - Topology Tree Readout MVP

Current Stage 15D status:

- Implemented in `frontend-v2/src/features/colony-planner/ColonyTopologyRail.tsx` and wired through `ColonyPlannerWorkspace.tsx`.
- The left rail is now a real read-only topology/body-tree MVP rather than a placeholder. It renders a compact system root row, body rows, moon/child indentation when parent metadata is present, per-body planned placement counts, orbital/surface/flex chips, sparse metadata chips, primary-port planned chips, unknown/unmatched placement groups, and unassigned placements.
- The workspace receives a one-way read-only plan snapshot from `SimulationPreviewPanel` / `SimulationPreview`. This lets the rail show current placement counts without moving editing ownership out of the central planner.
- Selecting a body, placement, unknown group, or unassigned group highlights the rail and updates the right summary panel with selected name, selected type, placement count, warning count, Architect status, and read-only selection copy.
- Build Plan editing remains inside the central planner content. Topology selection does not mutate placements, run Preview, generate Suggested Builds, import layout, mutate observations, or run validation.
- Empty body layout state now tells users: `No body layout imported yet. Use the planner tools to import/refresh layout when available.`

Purpose:

- Introduce the body/topology tree as primary navigation.

Files affected:

- `frontend-v2/src/features/colony-planner/ColonyTopologyRail.tsx`
- `frontend-v2/src/features/colony-planner/ColonyTopologyRail.test.tsx`
- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.test.tsx`
- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.integration.test.tsx`
- `frontend-v2/src/features/system-detail/SimulationPreviewPanel.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx`

Implementation notes:

- Read-only first; all structure editing remains in the central planner.
- Use existing system bodies, current placements, and facility templates.
- Include unassigned placements.
- Include unknown/unmatched body reference states.
- Selecting a node updates the right context panel only.

Tests:

- Stars/bodies/unassigned render from system detail.
- Placements attach under body/unassigned nodes.
- Unknown/unmatched placements render without exposing raw body IDs by default.
- Empty body layout state renders friendly copy.
- Selection updates read-only context.
- No mutation or API side effects on selection.
- Planner workspace still renders central `SimulationPreviewPanel`.
- System Detail remains simplified and links to Planner.

Safety boundaries:

- Do not invent exact slots.
- Do not add primary-port editing.

Explicitly deferred:

- Topology-local structure editing.
- Drag/drop.
- Slot editing.
- Persistent Architect survey records.
- Saved projects.

### Stage 15E - Build Plan Editing In Topology Workspace

Purpose:

- Move manual build/edit workflow from row-heavy List view into body/slot context.

Files likely affected:

- New topology editor components.
- `BuildPlanEditor.tsx`
- `StructurePickerTable.tsx`
- `StructureReplacementComparison.tsx`
- `usePlacementEditor.ts`

Implementation notes:

- Reuse existing placement update/remove/move semantics.
- Structure picker becomes a drawer or local panel for selected body/slot.
- Replacement comparison remains explicit Apply/Cancel.
- Mark Preview stale on edit through existing hook behavior.

Tests:

- Add to selected body.
- Replace selected structure.
- Move placement to another body/unassigned.
- Reorder build sequence.
- Apply/cancel replacement behavior preserved.
- No auto-preview/generation/validation.

Safety boundaries:

- Primary-port controls remain read-only.
- Layout/topology selection does not silently mutate.

Explicitly deferred:

- Drag/drop unless scoped separately.
- Backend project save.

### Stage 15F - Suggested Builds Quality Gate + Load Into Workspace

Purpose:

- Stop surfacing trivial suggestions as meaningful recommendations and let useful suggestions prepopulate the topology workspace.

Files likely affected:

- `apps/api/src/optimiser/candidate_generator.py`
- `apps/api/src/optimiser/ranker.py`
- `apps/api/src/optimiser/models.py`
- `frontend-v2/src/features/system-detail/simulation-preview/optimiser/*`
- New workspace suggestion drawer components.
- Tests under `tests/test_plan_ranker.py`, `tests/test_recommended_builds.py`, optimiser frontend tests.

Implementation notes:

- Add backend or frontend candidate quality metadata.
- Hide/demote port-only and one-support suggestions.
- Add strategic-purpose classification.
- Load suggestions into workspace draft through existing plan hook or new project state.
- Keep manual build path visible.

Tests:

- Port-only candidates are not first-class when alternatives exist.
- Empty useful result shows helpful manual alternatives.
- Classes render as user-facing labels.
- Loading suggestion populates placements and origin, but does not save or run Preview.

Safety boundaries:

- Do not overfit to RavenColonial.
- Do not claim optimality.
- Do not change simulation mechanics.

Explicitly deferred:

- Exhaustive optimiser.
- Role-aware scoring unless explicitly scoped.

### Stage 15G - Colony Project Persistence MVP

Purpose:

- Give plans a saved lifecycle.

Files likely affected:

- New `frontend-v2/src/features/colony-planner/project/*`
- Local storage/IndexedDB adapter.
- Project tests.
- Possibly System Detail project summary.

Implementation notes:

- Frontend-only first.
- Versioned schema.
- Save/load/delete local projects.
- Store placements, roles, notes, target, origin, preview snapshot, validation snapshot refs.
- Do not change observed-facts backend yet.

Tests:

- Create project.
- Save/load project by system.
- Migration/default handling for schema version.
- Corrupt storage fallback.
- System Detail summary detects project.

Safety boundaries:

- Clearly local-only.
- No backend/account sync.
- No silent saves unless product explicitly chooses autosave with visible status.

Explicitly deferred:

- Backend persistence.
- Sharing/sync.
- Project collaboration.

### Stage 15H - Evidence/Validation Drawers

Purpose:

- Move Observed Evidence and Validation out of the always-visible stack and into project lifecycle drawers.

Files likely affected:

- `ObservedEvidencePanel.tsx` and subcomponents.
- `ValidationPanel.tsx` and subcomponents.
- New drawer/mode components in `features/colony-planner`.
- Query invalidation tests.

Implementation notes:

- Reuse existing panels internally, but render them inside workspace modes/drawers.
- Add compact Evidence/Validation badges to summary.
- Add needs-observation checklist.
- Link validation mismatches to selected body/slot where data allows.

Tests:

- Drawers open from badges.
- Evidence CRUD still works.
- Validation still requires Preview.
- Observed Evidence invalidates compare/review queries.
- No auto-preview or auto-generation.

Safety boundaries:

- Evidence remains passive.
- Validation remains advisory.

Explicitly deferred:

- Automatic evidence ingestion.
- Automatic mechanics updates.

### Stage 15I - QA / Accessibility / Regression Hardening

Purpose:

- Make the new workspace reliable across desktop/mobile and protect safety boundaries.

Files likely affected:

- Workspace tests.
- E2E smoke tests.
- Accessibility and responsive CSS.

Implementation notes:

- Add keyboard navigation for topology tree.
- Verify focus management for drawers.
- Ensure compact status badges have accessible labels.
- Add responsive screenshots where practical.

Tests:

- `yarn test`
- Focused component/integration tests.
- Playwright smoke for planner route.
- No side-effect tests for load/selection/drawer open.
- `git diff --check`

Safety boundaries:

- No broad redesign outside planner/system detail.

Explicitly deferred:

- Large visual redesign of unrelated app tabs.

## J. Risks / Tradeoffs

### Route And State Complexity

The current hash router is simple but already has separate modal and planner state. Project routes, drawer modes, and selected tree nodes can make hash state brittle. Keep project selection and drawer state mostly internal at first; only persist/share route state once the workspace model stabilises.

### Persistence Timing

Persistence is essential, but backend persistence too early may freeze the wrong model. Frontend-only persistence first is safer, as long as the UI clearly says local-only. Backend persistence should follow after project schema, roles, and evidence links settle.

### Avoiding RavenColonial Cloning

RavenColonial should inspire workflow quality, not visuals. ED-Finder should keep:

- ED-orange/brushed steel styling.
- Prediction-first summary.
- Strategic guidance.
- Evidence/validation lifecycle.
- Compact warnings.
- Its own topology language and project model.

Avoid copying:

- Exact visual layout skin.
- Proprietary assets.
- Names, icons, or unique visual composition.
- Any exact interaction sequence that is distinctive rather than generic.

### Not Overfitting To One Site

RavenColonial is one strong reference. ED-Finder should also respect its own data model: prediction confidence, observed evidence, validation, regional context, and future colony roles. The workflow should be familiar, not derivative.

### Keeping ED-Finder Identity

The planner should feel like ED-Finder's strategic instrument panel, not a generic form or another app clone. Use the existing dark technical style, but reduce the current wall of repeated explanation.

### Avoiding More Scroll Bloat

The biggest risk is moving existing panels into a new shell without reducing anything. Stage 15 should enforce:

- Persistent summary instead of repeated summaries.
- Drawers instead of always-visible advanced panels.
- Compact tree rows instead of long cards.
- Local detail on selection.
- No repeated workflow copy in every component.

### Avoiding Premature Backend Changes

Backend changes are tempting for projects and suggestions. Delay schema work until:

- The topology workspace shape is usable.
- Project model fields are proven in frontend state.
- Suggested Build classes are stable.

### Test Strategy

Tests should focus on behavior and safety:

- Route separation: planner route does not open modal accidentally.
- No auto-run/generate/validate/save on load.
- Tree selection does not mutate plan.
- Editing marks preview stale.
- Evidence/Validation remain passive.
- Trivial suggestions are filtered/demoted.
- Project local persistence survives reload and handles schema migration.
- Mobile layout keeps tree/summary/drawers accessible.

## K. Deliverables For This Pass

Documentation only:

- Add this report: `docs/colonisation-redesign/stage-15-planner-workspace-redesign-plan.md`
- Update roadmap: `docs/colonisation-redesign/engine-roadmap.md`
- Update UI architecture notes: `docs/colonisation-redesign/simulation-preview-ui-architecture.md`

No implementation changes should be made in Stage 15A.

## Open Questions Before Implementation

1. Should local-only project persistence be acceptable for the first MVP, or should Stage 15G wait until backend persistence is ready?
2. Resolved in Stage 15C: the old System Detail Recommended Builds panel is removed from the modal path and replaced with compact copy that sends users to the Colony Planner for Suggested Builds.
3. Should the planner route expose project IDs in the hash immediately, or keep project selection local until saved projects are proven?
4. Should Suggested Builds quality gates live in the backend response, frontend display layer, or both?
5. Should Architect observation capture be a subtype of Observed Evidence first, or a separate project survey record first?
