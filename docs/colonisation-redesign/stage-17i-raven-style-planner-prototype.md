# Stage 17I: Static Raven-Style Planner Canvas Prototype

Stage 17I is a visual wireframe/prototype only.

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
- RavenColonial extracted frames and screenshots
- ED-Finder extracted frames and screenshots

Observed RavenColonial behaviour:

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

- `#colony-planner-prototype`

Component:

- `frontend-v2/src/features/colony-planner/prototype/RavenStylePlannerPrototype.tsx`

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

The prototype should be judged on whether it visually reads as:

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

- copy RavenColonial source code
- copy RavenColonial CSS
- copy RavenColonial assets/icons
- clone exact visual styling
- call RavenColonial APIs
- use RavenColonial API keys or proprietary implementation details

## Stage 17K Real Implementation Follow-Up

Stage 17K maps existing ED-Finder state into this canvas for the real dedicated planner route:

- canonical slot prediction outputs
- current Build Plan placements
- Suggested Build projection state
- planning economy ledger
- selected-body commands
- project save/load state
- explicit Preview status

The mock prototype remains available at `#colony-planner-prototype` for visual iteration, while the real route is `#colony-planner/system/{id64}`.

Stage 17K preserves the existing safety boundaries: no automatic generation, no automatic load, no automatic Preview, and no mechanics changes unless separately scoped.

Current production-readiness caveat:

- the real canvas uses ED-Finder's current template economy metadata and planning ledger only
- missing economy or slot metadata is shown as unavailable rather than mocked
- final validated economy outcome still requires explicit Preview
