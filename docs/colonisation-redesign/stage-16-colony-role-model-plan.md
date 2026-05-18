# Stage 16 - Colony Role / Colony Planet Model Plan

Stage 16A is a planning/report phase only. It does not implement code, change backend mechanics, change optimiser scoring, or introduce new persistence behavior.

## Purpose

ED-Finder now has a dedicated Colony Planner workspace with topology navigation, central Build Plan editing, Suggested Builds quality gates, local saved projects, and Evidence/Validation drawers. The next limitation is intent: the planner can show placements on bodies, but it does not yet know what the user thinks each body is for.

Colony roles should give the workspace a language for intent without pretending to know unsupported game mechanics. A body can be a main station candidate, support body, industrial core, or expansion reserve because that is useful planning guidance. That label must not become hidden scoring truth, service unlock truth, economy truth, or primary-port truth.

## Current Limitation

The Stage 15 workspace understands:

- system topology
- body rows and hierarchy where known
- Build Plan placements and body assignments
- local project notes and status
- observed evidence and validation review surfaces

It does not understand:

- why a placement belongs on a body
- whether a body is intended as the colony anchor or merely a support body
- whether a body is a planned role, observed role, or inferred guidance
- whether two placements support the same strategic purpose
- which body should be highlighted as the next manual planning focus

This makes guidance shallow. The UI can say that a body has placements, but not that it is the planned industrial core, the likely tourism body, or the body reserved for later expansion.

## Role Sources

### Planned Roles

Planned roles are project intent. They are attached to the saved Colony Project and represent what the user is designing.

Examples:

- user marks a landable moon as `Industrial Core`
- user marks a high-value body as `Tourism/Agriculture Body`
- user marks a body with the expected primary port as `Primary Port Body`

Planned roles should affect copy, filtering, badges, and guidance. They should not change mechanics, preview scoring, validation truth, or optimiser rankings in Stage 16.

### Observed Roles

Observed roles are evidence-derived or review-derived facts from actual in-game observation. They should live separately from planned roles.

Examples:

- Architect Mode reveals a primary port slot
- observed settlement layout suggests a body already hosts a specific placement
- validation confirms or disputes a planned body assignment

Observed roles should be presented as evidence-backed context. They must not be overwritten by user intent.

### User-Declared Roles

User-declared roles are explicit user choices. They are the safest Stage 16 implementation starting point because they do not require new inference rules.

They should:

- require explicit user action
- be editable
- be saved with the project once persistence is extended
- be visually distinct from inferred roles

They should not:

- silently rewrite Build Plan placements
- imply the game confirms the role
- set primary-port truth

### Inferred Roles

Inferred roles are ED-Finder suggestions from existing plan shape and topology context. They should be low-authority and confidence-labelled.

They can be inferred from:

- placement structure categories
- body assignment concentration
- existing optimiser candidate category
- observed primary-port evidence once that exists
- project notes only if a future explicit parser is added

They should be phrased as guidance: "likely industrial core", "candidate support body", "possible expansion reserve".

## Workspace Fit

Roles belong in the topology workspace because the user thinks about roles at body level:

- left topology rail can show compact role badges on body rows
- central planner can filter or group placements by selected role
- right summary rail can show role coverage, conflicts, and missing planned anchors
- Evidence/Validation drawers can compare planned roles against observed evidence
- Suggested Builds can explain which roles a candidate would seed, without changing optimiser scoring

The core editing surface should remain the central planner until a later stage explicitly moves role editing into topology-local controls. Topology row clicks should continue to navigate/select; role mutation should be an explicit control.

## Guidance Boundaries

Roles may influence:

- which body rows get badges
- which planner context summary is shown
- which warnings are grouped together
- which Suggested Build card copy is more specific
- which manual next action ED-Finder recommends
- which validation/evidence items are easier to review

Roles must not influence in Stage 16 without a later mechanics stage:

- CP formulas
- economy state propagation
- service unlock logic
- buildability rules
- optimiser ranking/generation
- Simulation Preview scoring
- primary-port truth
- observed evidence semantics
- validation semantics
- imports or EDMC ingestion

## Role Definitions

### Colony Anchor

Meaning:

The strategic center of the project. This is the body or placement cluster the user wants the colony plan to orbit around conceptually.

When user would assign it:

- after choosing the main project focus
- when comparing multiple candidate systems or bodies
- when the project has several placements and needs a clear anchor

When ED-Finder might infer it:

- one body has the majority of high-value placements
- a Suggested Build category clearly centers the plan on one body
- a saved project has one body repeatedly selected as the active planning context

Guidance affected:

- persistent summary context
- role coverage warnings
- suggested next body to review
- "main project focus" copy

Must NOT claim:

- that the game treats this body as capital, primary, or mechanically privileged
- that CP or economy should be recalculated from this role

Possible UI placement:

- prominent badge in topology rail
- summary rail role card
- central planner "Currently viewing" context when selected

### Colony Planet / Core Body

Meaning:

The main body the user expects to carry the colony identity. It may be a planet, moon, or other body depending on system data; the label is planning intent, not a hard astronomical rule.

When user would assign it:

- when one body is the intended main settled world
- when planning surface/orbital structures around a specific core body

When ED-Finder might infer it:

- most placements are assigned to one body
- the body has both station and support placements
- a candidate plan is balanced around one body

Guidance affected:

- body-first planning focus
- missing support warning copy
- central planner grouping

Must NOT claim:

- that this body is the primary port body
- that this body is mechanically required for colony success

Possible UI placement:

- topology row badge
- body detail panel role selector
- saved project summary

### Main Station Body

Meaning:

The body intended to host the main station or main orbital hub for the project.

When user would assign it:

- when choosing where the principal station should go
- when primary-port placement is inconvenient and the user wants the main station elsewhere

When ED-Finder might infer it:

- a large orbital station placement exists on the body
- the plan category is a main station candidate

Guidance affected:

- structure picker context
- warnings about overloading one body
- next action copy for station placement review

Must NOT claim:

- that the body is the primary port
- that the station is confirmed in-game
- that the role creates Build Points

Possible UI placement:

- station icon badge in topology row
- placement editor context label
- Suggested Build explanation

### Primary Port Body

Meaning:

The body or slot associated with the in-game primary port location revealed through System Map -> Architect Mode.

When user would assign it:

- ideally never as arbitrary truth
- user may attach planned guidance only after recording observed Architect evidence in a future evidence workflow

When ED-Finder might infer it:

- only from explicit observed primary-port evidence once supported
- never from optimiser output alone

Guidance affected:

- warning if the planned main station conflicts with observed primary-port guidance
- suggestion to place an outpost at the inconvenient primary-port slot and keep the main station elsewhere
- evidence/validation review grouping

Must NOT claim:

- that users can freely set primary port truth
- that primary-port location is a Build Point source
- that ED-Finder can infer primary port from normal body data

Possible UI placement:

- evidence-backed badge only
- technical details in Evidence drawer
- guidance line in body detail panel

### Industrial Core

Meaning:

The body intended to host industrial, refinery, manufacturing, or logistics-heavy structures.

When user would assign it:

- when planning a production-heavy colony
- when separating industrial function from tourism/agriculture or main station function

When ED-Finder might infer it:

- placements include refinery/industrial structures
- Suggested Build category is industrial/refinery starter
- body has several production-oriented placements

Guidance affected:

- role badge
- support-body suggestions
- warnings about needing complementary support or services

Must NOT claim:

- new economy mechanics
- exact production output
- service unlock guarantees

Possible UI placement:

- topology role badge
- central planner filter
- Suggested Build card purpose line

### Extraction Body

Meaning:

A body selected for mining, raw material extraction, or resource-support intent.

When user would assign it:

- when a body is chosen to support industrial plans
- when the user wants to reserve a resource-adjacent body for later placement

When ED-Finder might infer it:

- extraction-oriented placements exist
- body metadata suggests extraction relevance, if already available in current data

Guidance affected:

- support relationship copy
- role overlap with Industrial Core
- expansion planning hints

Must NOT claim:

- resource availability beyond existing data
- hauling requirements
- material execution plans

Possible UI placement:

- compact badge in topology rail
- support relationship detail in summary rail

### Tourism/Agriculture Body

Meaning:

A body intended for civilian, tourism, agriculture, habitation, or quality-of-life colony identity.

When user would assign it:

- when planning a softer economy or scenic/civilian role
- when separating civilian body identity from industry or military placement

When ED-Finder might infer it:

- tourism/agriculture-oriented placements exist
- Suggested Build category is tourism/agriculture starter
- plan has civilian support placements concentrated on one body

Guidance affected:

- card/category copy
- role conflict warnings with heavy industrial/military concentration
- next action prompts for support placement review

Must NOT claim:

- actual tourism value
- biological/agricultural viability beyond existing data
- service unlock certainty

Possible UI placement:

- topology badge
- central planner role filter
- Suggested Build purpose/tradeoff text

### Military/Security Body

Meaning:

A body intended to support security, defence, enforcement, or stabilisation functions.

When user would assign it:

- when planning a security stabiliser
- when separating security infrastructure from civilian or industrial core plans

When ED-Finder might infer it:

- military/security-oriented placements exist
- Suggested Build category is military/security stabiliser

Guidance affected:

- security role badge
- conflict/overlap copy
- candidate build explanation

Must NOT claim:

- system security state changes
- conflict simulation mechanics
- defensive guarantees

Possible UI placement:

- topology badge
- summary rail role coverage list

### Support Body

Meaning:

A secondary body that supports the colony anchor, main station, or core body with specific placements or future capacity.

When user would assign it:

- when spreading placements across bodies
- when a body is useful but not central
- when an inconvenient primary-port slot should host only an outpost

When ED-Finder might infer it:

- the body has one or two support placements
- the plan category is support-body plan
- role relationship points from main body to this body

Guidance affected:

- support relationship display
- topology grouping
- expansion readiness copy

Must NOT claim:

- mechanical dependency
- automatic service support
- Build Point source status

Possible UI placement:

- small badge in topology rail
- body detail relationship list
- right summary "support bodies" count

### Expansion Reserve

Meaning:

A body intentionally left open for future placements or later planning after more data arrives.

When user would assign it:

- when the user wants to avoid filling every available slot
- when data confidence is too low
- when keeping an alternative body available

When ED-Finder might infer it:

- notable body with no current placements in a plan that already has a clear anchor
- body appears suitable in existing data but is not selected
- saved project notes or future tags indicate reservation

Guidance affected:

- avoid "unused body" nagging
- show future planning capacity
- support Stage 16+ project lifecycle copy

Must NOT claim:

- guaranteed future buildability
- hidden slot capacity
- future mechanics support

Possible UI placement:

- muted topology badge
- project notes shortcut
- summary rail reserve list

## Role Conflicts

Conflicts should be advisory and reviewable, not blocking.

Examples:

- one body marked both `Primary Port Body` and `Main Station Body` without observed primary-port evidence
- one body marked `Tourism/Agriculture Body` and `Industrial Core` when the user may be mixing incompatible intent
- multiple `Colony Anchor` roles in one project without a multi-anchor explanation
- `Expansion Reserve` body with active placements

Conflict UI should use plain language:

- "This body has active placements but is marked as reserve."
- "Primary port guidance should come from observed Architect evidence."
- "Two bodies are marked as the colony anchor."

## Role Overlap

Some overlap is valid:

- `Colony Anchor` and `Colony Planet / Core Body`
- `Colony Planet / Core Body` and `Main Station Body`
- `Industrial Core` and `Extraction Body`
- `Support Body` and `Expansion Reserve` only if the reserve is future-oriented and has no active placements

The data model should allow multiple roles per body, with conflict rules layered separately.

## Role Confidence

Each role should carry a source and confidence:

- `declared`: user chose it
- `observed`: evidence supports it
- `inferred`: ED-Finder suggested it
- `mixed`: multiple sources agree or disagree

Confidence should be displayed as compact copy, not numeric pseudo-precision:

- `User planned`
- `Observed`
- `Suggested`
- `Needs evidence`
- `Conflict`

## Role Badges

Badges should be compact and body-row friendly:

- short label or icon plus tooltip
- one primary badge visible by default
- additional roles hidden behind `+N` or details
- evidence-backed roles visually distinct from planned roles
- conflict badges visible but not alarming unless blocking future action

Badges must avoid implying mechanics. For example, `Primary port observed` is acceptable after evidence exists; `Primary port set` is not.

## Future Optimiser Integration

Stage 16A does not change optimiser generation or ranking.

Future integration should be staged:

1. Display-only: Suggested Build cards can say which roles a candidate would seed.
2. Review-only: users can filter candidates by desired role category.
3. Planner-only: loaded plans can prefill planned roles if the user explicitly accepts that.
4. Optimiser-aware: only after mechanics/product review, roles may influence candidate generation prompts or constraints.

Any optimiser-aware stage must separately review scoring, ranking, and unsupported mechanic risks.

## Validation And Evidence Integration

Roles should integrate with Evidence/Validation as review context:

- Evidence drawer can show observed roles and their source.
- Validation drawer can compare planned role intent against observed evidence.
- Primary-port evidence must remain evidence-backed and cannot be arbitrary user truth.
- Role mismatches should be advisory unless a later validation stage defines stricter semantics.

Examples:

- planned `Primary Port Body` without observed evidence -> needs observation
- observed primary port on a body marked `Support Body` -> suggest outpost there and main station elsewhere if desired
- planned `Main Station Body` differs from observed primary-port body -> guidance, not error

## Persistence Needs

Saved Colony Projects should eventually persist:

- body role assignments
- role source (`declared`, `observed`, `inferred`)
- role confidence/status
- optional role notes
- conflict acknowledgements
- role assignment timestamps

Local persistence can extend the Stage 15G model first. Backend persistence should wait until role schema and migration needs are proven.

## Migration From Saved Projects

Existing Stage 15G saved projects have placements and selected body assignments but no roles.

Safe migration path:

- load existing projects with an empty role map
- infer display-only suggestions at runtime, without saving them automatically
- prompt users to accept declared roles explicitly
- never infer or save primary-port truth from legacy project data
- keep archived projects readable without role migration

## Proposed Stage 16 Implementation Breakdown

Stage 16A:

- documentation/report only

Stage 16B:

- workspace cleanup and decomposition before role implementation
- local-only project UX clarification
- no role editing, backend persistence, or mechanics changes

Stage 16C:

- topology role badges and read-only inferred role display

Stage 16D:

- explicit user-declared role controls in the central workspace

Stage 16E:

- role conflict/overlap guidance and summary rail coverage

Stage 16F:

- evidence/validation role review integration

Stage 16G:

- Suggested Build role explanation and explicit load-time role acceptance

Late Stage 16 or Stage 17:

- durable Colony Project persistence
- backend/cloud storage design
- export/import JSON
- migration from localStorage
- optional account/device sync if the product later supports accounts
- saved preview, observed evidence, and validation snapshots

## Acceptance Criteria For Future Implementation

- Roles are body-level planning intent, not mechanics truth.
- Primary-port role is evidence-backed only.
- No role assignment happens from topology row selection alone.
- No auto-preview, auto-generation, auto-validation, auto-import, or autosave is introduced.
- Existing saved projects load without data loss.
- Role UI improves guidance without making unsupported claims.

## Stage 16B Cleanup Addendum

Stage 16B completed the pre-role workspace cleanup.

Delivered:

- `ColonyPlannerWorkspace.tsx` now acts as a route container instead of owning the full workspace.
- `WorkspaceGrid.tsx` owns workspace layout, topology selection, review drawer mode, and planner mounting.
- `WorkspaceHeader.tsx`, `WorkspaceSummaryRail.tsx`, and `ProjectControlsCard.tsx` isolate header and summary rail presentation.
- `useWorkspaceProjectState.ts` isolates local-only project lifecycle state.
- The right summary rail is split into compact Project, Plan Health, Selection, Architect, Workspace Modes, and save-state cards.
- The central workspace has a compact planning-focus banner for selected bodies and a short first-run start panel for empty plans.
- User-facing stage/roadmap copy was removed from the workspace UI.
- Architect status now says `Architect flag not recorded` unless the current local plan indicates only a planned primary-port placement; it does not claim observation.
- Suggested Build filtering remains frontend-only, with clearer user-facing copy and more defensive trivial-plan detection.

Still deferred:

- full colony role editing
- role badges
- role persistence/migration
- backend/cloud saved project persistence
- Architect Slot Survey storage
- export/import JSON
