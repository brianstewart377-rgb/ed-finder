# Stage 17I: Static Planner Canvas Preview

Stage 17I is a visual wireframe/preview only.

It exists because the previous planner passes still read too much like:

- a narrow left body rail
- a centre report/card stack
- a dashboard of bordered panels
- suggested-build cards detached from the system topology
- small slot markers that did not make the build layout obvious

## Evidence Reviewed

Local evidence pack:

- `.codex-context/stage17f/stage17f_codex_evidence/README.md`
- `.codex-context/stage17f/stage17f_codex_evidence/docs/stage_17f_codex_prompt.md`
- `videos/ravencolonial_reference_walkthrough.mp4`
- `videos/current_edfinder_stage17e_walkthrough.mp4`
- reference planner extracted frames and screenshots
- ED-Finder extracted frames and screenshots

Observed reference planner behaviour:

- the system tree is the primary surface, not a side navigation list
- parent/child body hierarchy is visible through branch lines
- site counts are visible inline beside bodies
- structures appear directly under or beside the body they belong to
- projected/order/build information stays spatially tied to the system topology
- the calculation panel remains visible while the build layout remains visible

Observed ED-Finder failure mode:

- body navigation and build details were separated into left rail plus centre/right panels
- the centre area still felt like forms, cards, and reports
- structures were often text records rather than visible placements on the system layout
- slot/site capacity was not visually dominant enough
- the workspace did not immediately read as a whole-system planner

## Implemented Prototype

Route:

- `#planner-preview`

Component:

- `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx`

The component is isolated and mock-only:

- no backend fetches
- no API calls
- no Build Plan/project state
- no local storage/persistence
- no optimiser, slot prediction, Simulation Preview, CP, economy, service, Search Tuning, import, or EDMC logic

The mock system includes:

- one star/root
- more than 20 bodies
- nested parent/child moon hierarchy
- known slot counts and unknown slot examples
- one body with 4 orbital slots and 5 ground slots
- planned structures
- projected ghost structures
- primary-port marker
- overflow example
- body economy strips
- compact persistent telemetry/economy panel

## Visual Contract

The preview should be judged on whether it visually reads as:

`whole system -> body hierarchy -> slots -> structures -> economy`

It should not be judged as production functionality. It deliberately does not commit, preview, optimise, persist, or validate anything.

Accepted visual direction:

- one continuous scrollable canvas
- branch lines and indented body rows
- orbital and ground slot boxes inline with each body
- planned structures inside slot boxes
- projected structures shown as ghost/dashed/subdued slot boxes
- structure identity and economy strips directly inside the relevant slot lane
- expanded structure detail is optional/demand-driven, not a permanent Attached Structures column
- compact telemetry panel that stays visible during planning

Rejected visual direction:

- separate body list plus separate centre card grid
- dashboard panels as the main planning experience
- text-only structure lists
- tiny slot markers that cannot be read as capacity
- suggested builds as detached recommendation cards with no visible projection on bodies

## Clean-Room Boundary

Allowed:

- observe reference videos and screenshots
- describe behaviour and workflow
- implement an ED-Finder-styled interaction concept

Forbidden:

- copy reference planner source code
- copy reference planner CSS
- copy reference planner assets/icons
- clone exact visual styling
- call reference planner APIs
- use reference planner API keys or proprietary implementation details

## Stage 17K Real Implementation Follow-Up

Stage 17K maps existing ED-Finder state into this canvas for the real dedicated planner route:

- canonical slot prediction outputs
- current Build Plan placements
- Suggested Build projection state
- planning economy ledger
- selected-body commands
- project save/load state
- explicit Preview status

The mock preview remains available at `#planner-preview` for visual iteration, while the real route is `#colony-planner/system/{id64}`.

Stage 17K preserves the existing safety boundaries: no automatic generation, no automatic load, no automatic Preview, and no mechanics changes unless separately scoped.

Current production-readiness caveat:

- the real canvas uses ED-Finder's current template economy metadata and planning ledger only
- missing economy or slot metadata is shown as unavailable rather than mocked
- final validated economy outcome still requires explicit Preview

## Stage 17M Real Route Follow-Up

Stage 17M applies the preview's central lesson to the real planner route: the system tree is the planning canvas, not a left navigation rail beside a permanent selected-body column.

The real route now has one primary scrollable system build canvas plus a right telemetry/context panel. The former middle selected-body editor is rendered only as an inline expansion under the selected body row. This keeps the surrounding body tree, orbital slots, ground slots, planned structures, projected ghost structures, and economy microbars visible while the user edits one body.

Structure context moved into the same interaction model. Clicking planned structures selects and highlights the structure in the canvas and shows full structure context in telemetry. Projected Suggested Build structures are selectable ghost structures; their telemetry explicitly identifies them as projected and projection-only.

The Advanced Planner remains behind its explicit toggle. Stage 17M does not add automatic generation, automatic candidate loading, automatic Preview, reference planner API calls, or backend mechanics changes.

## Stage 17N Real Route Follow-Up

Stage 17N keeps the preview lesson but improves the real route's context behavior. The right telemetry/context region is a single desktop sticky stack and a bottom-docked expandable Telemetry drawer below desktop. The dock does not duplicate planner state; it reveals the same telemetry and summary content.

Projection affordances are now more deliberate. The telemetry panel includes Bodies, Economy, and Slots comparison controls for the selected Suggested Build projection, so ghost structures can be evaluated against the current Build Plan before the user chooses to load or preview anything. The comparison remains frontend-only and read-only.

Stage 17N still does not add automatic generation, automatic candidate loading, automatic Preview, reference planner API calls, backend scoring/mechanics changes, or observed Architect slot storage.



