# Stage 17A/17B Colony Architect Report

> Historical reference only. This report records an earlier planner direction
> and rescue pass. It is not an active roadmap source. Use `docs/ROADMAP.md`
> and `docs/colonisation-redesign/README.md` for current direction.

Stage 17A identified that the planner problem is not missing labels. The useful direction is a **Colony Architect** workflow:

1. analyse the system
2. understand player intent
3. generate a concrete plan
4. preview the plan
5. explain why it was suggested
6. let the player refine it

Stage 17B is the rescue implementation for the existing Suggested Builds surface. It does not implement a full advisor, LLM planning, role-aware mechanics, automatic preview, automatic loading, or persistence changes.

## Stage 17B Rescue Changes

The immediate `/optimiser/candidates` 500 root cause was a backend contract mismatch in the optimiser preview-context query. The route queried `systems.system_id64`, but the systems table and the rest of the system-detail API use `systems.id64`. Stage 17B changes the optimiser context query to `WHERE id64 = $1`.

The route now logs the request, generation stages, ranking start, preview attachment, trivial-candidate filtering, and root-cause exceptions. Unexpected route failures are still logged with the exception, but clients receive a safe 503 detail:

`Suggested Builds are temporarily unavailable. You can still edit your Build Plan manually or try again.`

The frontend now shows that friendly message by default, keeps a Retry button, and hides raw API details behind an explicit technical-details expander.

## Candidate Usefulness Floor

Suggested Builds now reject or hide candidates that are not useful strategic recommendations:

- port-only or colony-ship-only output
- colony-ship/bootstrap output as a top strategic suggestion
- one generic low-purpose station without a clear strategic role
- duplicate near-identical plans
- plans without a body/structure purpose

When generated backend candidates exist but all are filtered as trivial, the frontend shows:

`No useful suggested builds are available yet. Start manually or provide more system data.`

## Generation Quality Foundation

Stage 17B keeps generation deterministic and bounded. It adds stronger archetype-shaped strategies:

- Main station candidate
- Balanced expansion
- Industrial / refinery starter
- Tourism / agriculture hub starter
- Military / security stabiliser
- Support-body plan
- Primary-port bootstrap, treated as bootstrap only

The backend now prefers non-colony ports for strategic candidates and requires at least one support placement with a clear player-facing purpose before returning a plan. A small deterministic system-strategy analysis helper summarises economy pressure, body opportunities, weak points, and sparse-data conditions for future advisor work.

## Stage 17C Usability Rescue

Stage 17C shifts the dedicated Colony Planner toward a body-first workflow:

`click body -> inspect body -> add/review structures there -> run Preview explicitly`

The rescue is functional rather than visual. It keeps ED-Finder's dark/orange brushed-steel style while borrowing the useful reference planner workflow principle that the body tree is the primary navigation surface.

Implemented UX changes:

- topology rows are compact clickable controls with body type marker, body name, one count chip, and tiny status markers instead of role badge clusters
- selected rows use a stronger orange selected state and keyboard-visible focus
- the central workspace now shows a body planning surface before the existing planner internals
- selecting a body shows body type, compact suitability tags, planned structures on that body, and explicit Add structure here / Review structures actions
- Build Plan defaults to body view; List view remains the advanced editor
- the right summary rail is reduced to Project, Plan Health, Current Focus, one compact Body Hint, and Evidence/Validation mode buttons
- local project copy is reduced to "Saved locally in this browser. Not cloud synced."

Suggested Builds status after Stage 17C:

- Stage 17B's useful-candidate filtering and friendly error handling remain in place
- raw API/JSON details stay hidden behind the technical-details expander
- trivial output remains hidden or downgraded to the useful-empty state
- generation, loading, and Preview remain explicit user actions

EDDN ticker fix:

- the ticker no longer displays the raw SSE reconnect message in the main UI
- production SSE `onopen` and valid `onmessage` clear the transient error state
- the SSE cleanup path now clears pending flush timers
- the visible fallback is the compact "EDDN feed reconnecting" state

## Stage 17D Colony Planner Functional UX Reset

Stage 17D is a usability rescue pass focused on the dedicated Colony Planner loop:

`pick body -> plan on body -> project suggested build -> run preview explicitly`

It does not change CP formulas, economy/service mechanics, simulation scoring, Search Tuning, imports, EDMC ingestion, or persistence architecture.

### Root causes addressed

- Nav overlay: menu state/layout let the compact route menu behave like a blocking planner overlay in narrow/transition states.
- Health banner: frontend status checks and display fallback allowed the wrong endpoint path and technical failure payloads to leak into normal UI.
- EDDN ticker: SSE-first rendering could present dead/reconnecting states even while recent events were available.
- Planner interaction: topology, central surface, and Suggested Builds were still acting like disconnected report cards.

### Stage 17D changes

- Nav/menu:
  - mobile/compact menu is closed by default
  - menu closes on route click, outside click, and Escape
  - planner route no longer starts with an open blocking menu
- Health display:
  - `api.health()` explicitly targets `/api/health`
  - normal UI status copy is compact (`Online`, `API connection issue`)
  - raw API/Cloudflare payloads are not shown in the normal planner shell
- EDDN feed:
  - `useEddnFeed` now uses explicit feed states (`connecting`, `live`, `reconnecting`, `offline`)
  - SSE reconnects degrade to compact reconnecting/offline labels
  - recent-events polling fallback keeps ticker useful when SSE is unstable
  - malformed event payloads are ignored safely
- Topology rail:
  - compact body names (for example `A 1`, `A 1 a`) are shown in-row
  - full body name remains available via title/selected-body context
  - body rows remain explicit button controls with strong selected state
  - projection context can mark bodies used by a selected suggested build
- Central planning surface:
  - selected body now drives the centre surface immediately
  - body-local planned structures are listed directly
  - `Add structure here` / `Review structures` now issue explicit workspace commands instead of DOM query hacks
- Suggested Builds projection:
  - selected candidate now reports projected body usage in candidate details and topology
  - explicit load action remains unchanged (no auto-load, no auto-preview)
- Right summary rail:
  - compact rail focused on Project, Plan Health, Current Focus, and Preview/Suggested status
  - reduced strategy/role narrative clutter in default view

Remaining limitations:

- Add structure here still delegates into the existing safe Build Plan add path instead of introducing drag/drop or slot editing
- Suggested Builds are still deterministic heuristic starts, not a full strategy advisor
- topology projection for hovered Suggested Builds is still limited
- Architect slot counts and primary-port truth remain evidence-backed future work
- backend dirty-recalc statement-timeout warnings can be tracked separately, but they are not treated as Stage 17D blockers for live-feed ticker UX

## Remaining Limitations

This is still not the full Colony Architect advisor. ED-Finder does not yet accept refinement prompts such as “make it produce CMM”, “move the Dodec to A5”, or “make it more industrial and less tourism”. Suggested Builds are still heuristic and should be treated as editable starting points. The topology rail, summary rail, and wider workspace focus issues remain for later UX stages.

## Next Stage

Stage 17C should turn the deterministic analysis and candidate explanations into an explicit Guided Colony Strategy Advisor shell: system analysis, declared intent, generated plan, preview, explanation, and refinement controls without introducing black-box planning.

## Stage 17E reference planner-Style Functional Build Planner Rebuild

Stage 17E is a functional rebuild pass, not a visual polish pass. It targets the missing loop:

`click body -> plan on that body -> add structure there -> see it in tree -> compare projected suggested plan -> load explicitly -> preview explicitly`

### Stage 17E implemented changes

- Left rail now behaves as a true build tree:
  - planned structures stay nested under bodies
  - projected suggested-build placements render as separate ghost rows under bodies before load
  - projected bodies are explicitly highlighted
- Central planner is now body-local first:
  - selected body shows planned + projected structures directly
  - `Add structure here` opens an explicit body-aware structure picker (no DOM query hacks)
  - selecting a structure from the picker issues an explicit body/template add command
- Old stack is now secondary:
  - Suggested Builds, Preview, and advanced list/body editor live behind an explicit `Advanced planner views` toggle in the centre column
  - core body planning remains visible first
- Suggested Builds are now scale-aware and less trivial:
  - backend candidate assembly targets starter/expansion/full footprints where catalogue/body coverage allows
  - candidate tags now include scale markers (`scale_bootstrap`, `scale_starter`, `scale_expansion`, `scale_full`)
  - fallback duplication of supports is bounded so sparse catalogues can still produce useful 5+ placement plans
  - multi-body distribution is applied for non-bootstrap strategies when anchor bodies exist
- Suggested Build cards/details now show plan scale and footprint:
  - scale label
  - placement count
  - body count
  - short scale rationale

### Stage 17E boundaries kept

- no CP formula changes
- no economy/service scoring changes
- no automatic preview, generation, or loading
- no live LLM calls
- no backend persistence changes

### Remaining Stage 17E limitations

- body-local planner currently uses deterministic placement creation from existing template catalogue metadata; slot-level drag/drop is still future work
- candidate scale still depends on catalogue breadth and body coverage; sparse systems can still produce starter-level output
- LLM advisor remains foundation-only (schema/docs), not active UI generation

## Stage 17N.2d Existing Infrastructure Awareness

Stage 17N.2d closes the main correctness gap left by the whole-system planner:
an empty Build Plan no longer implies the system has no infrastructure.

Implemented behaviour:

- existing station records from `/api/system/{id64}` are resolved into a
  frontend `existing` structure model separate from planned and projected
  structures
- safely mapped existing orbital/surface structures render directly in the planner canvas
  slot lanes as solid occupied slots
- unresolved stations render in a compact "Existing infrastructure not matched
  to body" area
- Add Orbit/Add Surface respects existing occupancy and disables when the lane
  has no empty capacity
- existing slots do not mutate the user Build Plan, do not select as planned
  placements, and do not inflate planned counts

Safe assumptions:

- exact `body_id` / `local_body_id` can be treated as exact when available
- exact `body_name` can be treated as exact when it matches one known body
- unique non-zero `distance_from_star` can be shown as inferred, not exact
- Coriolis/Orbis/Ocellus/Outpost/AsteroidBase are orbital slot occupants
- PlanetaryPort/PlanetaryOutpost/surface/settlement-like types are surface slot
  occupants

Unsafe assumptions avoided:

- no body is guessed from an ambiguous name or distance
- no unknown station type is forced into orbital/surface capacity
- fleet carriers and megaships are not counted as colony-slot occupants
- `stations.id` is exposed as `market_id` for diagnostics but still needs
  backend verification before it is treated as a separate canonical identity

## Stage 17N.2d-H Normalized Occupied-Slot Source

Stage 17N.2d-H adds the data contract behind the Stage 17N.2d UI:

- `station_body_links` is the normalized source for station/body/lane
  association
- association status is explicit: `confirmed`, `inferred`, or `unresolved`
- confidence/source are explicit: exact/manual/import/EDDN/resolver body-name or
  distance, strong inference, unresolved
- the resolver never invents body ids and never lets ambiguous distance matches
  become inferred occupancy
- the manual backfill script supports dry-run, limit, system targeting, apply,
  and preserving confirmed links by default
- `/api/system/{id64}` exposes association metadata so the planner can render
  confirmed, inferred, and unresolved infrastructure honestly

Planner behaviour:

- confirmed links occupy slots normally
- inferred links occupy the displayed lane but are marked `verify`
- unresolved or unknown-lane links remain visible outside body lanes
- planned/projected/existing distinctions remain separate

This still does not mean every station can be perfectly mapped. It establishes
the source-of-truth foundation and keeps unknowns visible until source data or
manual/Architect-observed correction can confirm them.

## Stage 17N.2e Economy Bar Correctness

Stage 17N.2e tightens the planner canvas's economy display without changing
slot prediction, Preview mechanics, rating weights, or occupied-slot source of
truth.

Implemented changes:

- economy colours are centralized in `economyVisuals.ts` and shared by the planner canvas
  slot bars, selected-body structure slots, projected slots, planning economy
  strips, RatingRadar economy bars, and the retained preview
- supported visual economies are Agriculture, Refinery, Industrial, HighTech,
  Military, Tourism, Extraction, Terraforming, Civilian, Support, Contextual,
  and Unknown
- per-structure bars are readable 8-10px hover targets instead of hairline
  decoration
- direct facility bars show catalogue/template economy metadata and real CP
  generated totals where template data provides them
- station/port inherited baseline bars use the same body economy profile rules
  as the backend Preview foundation: base economies weighted `1.0` then `0.8`,
  modifier economies weighted `0.45`, then normalized into percentages
- no fallback invents equal 50/50 shares or fake CP; if the body profile cannot
  produce a baseline, the UI reports it as unavailable and points to Preview

Remaining limitation:

- `/api/system/{id64}` bodies expose enough fields for the common body profile
  cases, but Preview can still use richer scan facts where available. The
  planner baseline is therefore a calculation-backed pre-Preview estimate, not
  a replacement for Preview validation.

## Stage 17G Validated Slot Algorithm Everywhere + System-Wide Slot Map

Stage 17G standardises slot prediction on one canonical backend algorithm and changes the dedicated planner from a body list plus report cards into a whole-system slot/economy map.

Delivered:

- canonical runtime predictor in `apps/api/src/ingest/slot_prediction.py` (`validated-slot-v1`)
- strict unknown behavior for missing required inputs (`insufficient data for validated prediction algorithm`, `Verify in Architect Mode`)
- system totals remain unknown if any required body inputs are missing, preventing partial totals from masquerading as capacity
- no active radius/class/body-type fallback slot estimates when canonical prediction cannot be produced
- legacy trait-derived topology fallback is disabled as a compatibility no-op
- canonical slot metadata in API responses (`prediction_status`, `prediction_version`, `validation_note`, `required_input_missing`, `missing_inputs`, `source_label`)
- frontend slot-map surfaces consume canonical `predicted_*` fields directly and render unknown lanes when unavailable
- planner left rail shows dense whole-system per-body slot lanes (orbital + ground), planned occupancy, projected ghost occupancy, compact economy contribution, and overflow labels
- central selected-body planner mirrors left-rail slot counts with larger editable lanes and lane-specific add actions
- live planning economy ledger is visible in workspace header, selected-body editor, left rail, summary rail, and Suggested Build details
- Suggested Build selection projects ghost structures and projected economy into the map without auto-loading or auto-running Preview

Prediction wording is explicit and conservative:

- `Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.`
- `Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.`

Boundaries kept:

- no CP formula changes
- no economy/service scoring changes
- no Search Tuning changes
- no import/EDMC/persistence model changes
- no auto-generation/auto-load/auto-preview behavior changes
- no Architect-observed slot storage in this stage

Economy wording is explicit and conservative:

- `Planning economy mix — run Preview for validated outcome.`
- economy contribution is counted from existing facility-template economy metadata only
- Simulation Preview remains the authoritative mechanics result

## Stage 17H Default Whole-System Planner Replacement

Stage 17H is a rejection/replacement pass for the default dedicated Colony Planner experience.

Why the previous iterations failed as the default:

- Stage 17F/17G added useful slot-lane and projection pieces, but the first impression could still read as the old Build Plan/Suggested Builds/Preview card stack.
- The left side could still be interpreted as a body/navigation list instead of the main whole-system build map.
- The user still had to move into body-level or advanced panels to understand enough of the system plan.
- Suggested Builds were still too easy to experience as candidate report cards instead of projected system layouts.

Stage 17H replaces the default route composition:

- `WholeSystemColonyPlanner.tsx` is the default dedicated planner composition.
- `SystemSlotMapPanel.tsx` wraps the whole-system slot map as the left/default system surface.
- `SelectedBodyPlannerCanvas.tsx` owns the centre graphical body editor and no-body graphical prompt.
- `PlannerStatusStrip.tsx` keeps system-level status and the live planning economy strip compact.
- `AdvancedPlannerDrawer.tsx` is the only default-route path to the old Simulation Preview/Suggested Builds/list-editor stack, and it is closed by default.
- `WorkspaceGrid.tsx` is retained only as a compatibility wrapper around the new whole-system planner, so the rejected old layout cannot be reintroduced by importing it.

Default planner behavior:

- opening the planner immediately shows the whole-system left slot map and centre graphical planner surface
- left body rows show body name/type, orbital slots, ground slots, planned structures, projected ghost structures, overflow/unconfirmed state, and compact economy strips
- the centre no-body state offers `Select a body from the system map`, `Generate Suggested Build`, and `Open Advanced Planner`
- selecting a body opens a larger graphical editor with matching orbital/ground/flexible lanes and lane-specific add actions
- adding structures updates local plan state immediately in both the left map and centre editor
- selecting/providing a Suggested Build projection pushes ghost placements into the left map, selected-body lanes, projected-body highlighting, and planning economy ledger

Safety boundaries kept:

- no auto-generation
- no auto-load
- no auto-preview
- no CP formula, economy mechanics, service scoring, Search Tuning, import, EDMC, or hauling/material workflow changes
- no primary-port truth editing or Architect survey persistence
- no reference planner source/CSS/assets/API mutation

## Stage 18 direction

Stage 18 should build a constrained Colony Architect assistant shell on top of the Stage 17H whole-system planner:

- natural-language intent capture
- deterministic constraint translation
- explicit user review/acceptance
- no silent build mutation
- Preview remains the validation authority

## Stage 17I Static Planner Canvas Preview

Stage 17I is a visual wireframe stage, not a live planner replacement.

Why it exists:

- previous iterations kept drifting back toward left rail plus centre report/card panels
- slot lanes and projected structures existed, but the first impression still did not read as a continuous whole-system build layout
- the visual direction needs to be validated before another implementation pass wires real data through it

Delivered boundary:

- `frontend/src/features/colony-planner/preview/PlannerCanvasPreview.tsx`
- safe review route: `#planner-preview`
- hardcoded/mock system data only
- no backend fetches, no Build Plan state, no local project mutation, no persistence
- no optimiser, slot prediction, Simulation Preview, CP, economy, service, Search Tuning, import, or EDMC logic changes

Visual preview goals:

- whole system as one continuous scrollable build canvas
- body hierarchy shown by branch lines and vertical flow, not a detached body list
- orbital and ground site boxes visible inline for each body
- planned and projected structures rendered inside slot boxes and repeated as attached child markers
- ghost/projection styling is visually distinct from planned structures
- compact economy strips live beside each body while the build layout remains visible
- a persistent reference-planner-like telemetry panel shows score, population, security, tech, wealth, standard of living, development, economy mix, haul, and active-build placeholders

Clean-room boundary:

- reference planner evidence was used only to understand functional visual behaviour: system tree, inline site counts, attached structures, projection ghosts, and persistent calculations
- no reference planner source, CSS, assets, icons, API calls, or proprietary implementation details were copied
- ED-Finder keeps its dark/orange/brushed-steel/cyan styling

What must be validated before real implementation:

- whether the continuous canvas reads as a planner instead of a dashboard
- whether slot boxes are large and obvious enough at desktop widths
- whether structure attachment is understandable without opening body cards
- whether the right telemetry panel helps without consuming too much width
- whether compact rows remain usable for 15-25 body systems

The next real implementation pass should wire this shape to existing planner state only after the visual direction is accepted.

## Stage 17F Graphical Slot-Lane Planner and Full-Width Workspace

Stage 17F converts the dedicated planner centre from a body-local list into a graphical slot-lane planning surface while preserving explicit planner safety.

Implemented Stage 17F changes:

- full-width planner route:
  - `#colony-planner` now uses a route-specific full-width app container
  - the workspace grid now prioritises centre width (`left ~280px`, wide centre canvas, narrower right rail)
  - other app routes keep the existing max-width container
- graphical selected-body planner surface:
  - new lane planner components render **Orbital**, **Surface**, and **Flexible / Unknown** lanes
  - each lane shows planned placement cards and projected Suggested Build ghost cards
  - empty lanes show explicit empty states and lane-local add actions
  - selected placement state remains explicit and synchronised with Build Plan selection context
- slot-count handling:
  - lane headers display occupied/available when body slot-count fields exist
  - unknown slot capacity remains explicitly unknown
  - no fake slot counts are invented
- surface-lane validity:
  - non-landable or water-world bodies render compact surface-lane limitation state
  - surface add action is disabled in clearly invalid cases
- lane-aware add flow:
  - lane add actions open a body + lane filtered structure picker
  - orbital/surface/flexible filtering is conservative and frontend-local
  - selected template still mutates the editable Build Plan only through the existing explicit add command path
- left rail as build tree:
  - planned and projected children remain nested under each body
  - compact planned/projection group markers improve hierarchy scanability
  - selected body and projected-body states remain explicit
- Suggested Builds scale controls:
  - user-facing scale selector now exposes `Starter`, `Expansion`, and `Full / Ambitious`
  - default filter is `Expansion` (bootstrap is not the default recommendation view)
  - candidate footprint visibility remains explicit: scale, placement count, body count, main/support body context
- right summary-rail reduction:
  - rail is narrower and includes a compact toggle mode
  - heavy project details (notes/duplicate/archive controls) are collapsed behind an explicit project-details toggle
- advanced stack remains secondary:
  - the existing Build Plan/Suggested Builds/Preview stack remains behind the existing `Advanced planner views` toggle and stays closed by default

Stage 17F boundaries preserved:

- no CP formula changes
- no economy/service/simulation scoring mechanics changes
- no Search Tuning changes
- no backend persistence changes
- no auto-preview/auto-generate/auto-load
- no live LLM calls

Stage 18 foundation remains unchanged:

- natural-language intent should translate to explicit structured constraints
- deterministic planner remains the source of truth
- Preview remains the validation authority
- mutation remains explicit and user-confirmed

Stage 17H supersession note: Stage 17F's graphical lane work remains part of the implementation, but it is no longer the default architecture description. The current default is the Stage 17H whole-system planner with the old stack behind Advanced Planner.

## Stage 17K Planner Real Data Wire-Up

Stage 17K wires the accepted whole-system planner direction into the real dedicated Colony Planner route while keeping the isolated preview route for visual testing.

Implemented Stage 17K changes:

- `#colony-planner/system/{id64}` now renders a data-driven whole-system planner canvas as the first planner surface.
- `#planner-preview` remains mock-only for visual iteration.
- the real canvas consumes the existing planner snapshot:
  - loaded system detail and real body hierarchy
  - canonical slot-prediction response
  - editable Build Plan placements
  - facility template metadata and display names
  - selected Suggested Build projection emitted by the Advanced Planner
  - planning economy ledger counts from real template economy metadata
- planned and projected structures render directly inside orbital/ground slot lanes.
- missing slot prediction data renders explicit unknown slots instead of fake counts.
- missing economy metadata renders as unavailable/no contribution rather than mock values.
- the Attached Structures column remains removed.
- the old Simulation Preview/Suggested Builds/list-editor stack remains behind Advanced Planner and is not mounted by default.

Default-resolution/readability pass:

- planner route layout now uses a responsive planner-first data layout:
  - wide real canvas first
  - selected-body editor/detail surface second
  - readable telemetry/project rail on the right at larger widths
- the selected-body middle surface uses larger body titles, more readable structure names, stronger line-height, and less all-caps microtext for important content.
- telemetry keeps red negative / green positive zero-centred bars and real planning economy mix copy.

Still not production-final:

- planning economy remains the frontend planning ledger, not a validated Preview result.
- strength values are only shown from available real template metadata; the UI does not invent reference planner-style bonus magnitudes when the data is missing.
- project save/load remains browser-local.
- Suggested Build generation, candidate load, and Preview remain explicit actions.

## Stage 17M Two-Region Planner Canvas

Stage 17M removes the permanent three-column planner split. The previous left map + middle selected-body editor + right telemetry layout kept separating the selected body from the system topology, so the middle column did not justify its permanent width and made the planner feel like disconnected panels again.

The dedicated planner route now uses two primary regions:

- main whole-system build canvas: body tree, orbital/ground slots, planned structures, projected ghost structures, economy microbars, and inline selected-body expansion
- right telemetry/context panel: system telemetry, economy mix, selected body context, selected planned/projected structure detail, projection status, warnings, and compact project summary

Selecting a body keeps the whole-system canvas in view and expands that body row inline. The expansion reuses the body slot planner with larger lane maps, add orbital/surface/flexible actions, body economy, planned/projected structures, and overflow or compatibility warnings. Selecting another body moves the expansion instead of navigating to a separate middle surface.

Selecting a structure highlights it in the canvas and updates the telemetry context. Planned structures show full template name, lane/body, economy contribution, CP strength, and build order where available. Projected Suggested Build structures are selectable as ghost/projected context but remain projection-only; they do not load into the Build Plan, run Preview, or trigger generation.

Remaining reference planner gaps: no drag/drop slot editing, no true material/hauling workflow, no Architect-observed slot truth storage, no rich orbital path animation, and Suggested Builds remain deterministic editable starts rather than a full strategy advisor.

## Stage 17N Right-Panel Density And Docking

Stage 17N refines the Stage 17M shape without reopening the three-column split. The right region is now a single context stack: desktop keeps it sticky and scrollable, while narrower layouts present a bottom-docked Telemetry toggle that opens the same telemetry and summary content. This gives mobile/tablet users an intentional dock rather than relying on the right region falling below the canvas.

The telemetry panel now has projection comparison controls for Bodies, Economy, and Slots. These controls make Suggested Build ghosts easier to evaluate before any load action: bodies compare current Build Plan coverage with projected ghost bodies, economy shows planned plus projected counts by template economy, and slots summarize projected orbital/ground/unknown lane pressure and overflow risk. The controls are read-only and do not run Preview, generate, load, save, import, mutate observations, or call reference planner.

The summary rail is compact by default, showing save state, build counts, warning count, focus, projection label, and economy strip. Local project controls remain available only after manual expansion.

## Stage 17N.1 Core Interaction Repair

Stage 17N.1 makes the whole-system planner canvas a working manual editing surface, not only a viewer.

Implemented behavior:

- visible planner row add controls and empty slot clicks open a lane-aware structure picker
- the picker displays the selected body, requested orbit/surface lane, compatible count, structure name, category/type, economy, tier, pad, and location metadata
- water-world and non-landable surface attempts show disabled reasons instead of silently doing nothing
- incompatible templates are hidden and counted
- template selection writes through the same local Build Plan placement state used by Advanced Planner
- added structures immediately render in the planner whole-system lane and the selected-body inline detail
- project unsaved state updates from the same placement snapshot

Explicit non-behavior:

- opening the picker does not mount Advanced Planner
- adding a structure does not run Preview
- adding a structure does not generate Suggested Builds
- projected ghost slot clicks remain selection/context only and do not load a candidate

Remaining manual editing gaps:

- no drag/drop placement movement
- no explicit slot index persistence
- no per-placement lane storage for truly flexible/unknown structures; lane-specific pickers therefore only show templates that the current placement model can render reliably into that lane
- no Architect observed slot storage

## Stage 17N.1b Add Flow UX And Catalogue Coverage

Stage 17N.1b keeps the Stage 17N.1 direct-add architecture and makes the interaction clearer and more complete.

Implemented behavior:

- the planner canvas title is now `System Build Map`; the subtitle is `Plan structures directly into predicted orbital and surface slots.`
- body controls select bodies, occupied planned slots select placements, projected ghost slots select projected placement context, and visible `+ Add` controls open the structure picker
- passive slot/capacity boxes no longer use misleading hover or pointer-style treatment
- the picker no longer treats `both + is_port` as orbital-only or `both + !is_port` as surface-only, so valid outposts, installations, hubs, settlements, ports, and variants remain available for compatible lanes
- facility template responses now include catalogue prerequisite metadata and economy-effect metadata for frontend display and warnings
- missing prerequisites are shown as warnings in the picker, structure slots, selected structure context, status/telemetry, and plan health, but they do not block adding planned structures
- true invalid placement still blocks with a visible reason, including surface builds on water worlds and non-landable bodies
- station/port templates without direct economy metadata show contextual economy and role copy instead of blank economy fields
- successful adds report the structure, body, and lane in the canvas feedback message

Explicit non-behavior:

- no Advanced Planner requirement for manual planner adds
- no automatic Preview run
- no automatic Suggested Build generation
- no projected candidate auto-load
- no invented station economy values

Remaining manual editing gaps:

- missing-prerequisite warnings do not yet include a one-click prerequisite insertion action
- slot index and explicit lane storage are still absent from the simulation request model
- prerequisite matching is based on catalogue descriptions/tokens until normalized prerequisite target IDs are available

## Stage 17N.1c Graphical Declutter And Lane Correctness

Stage 17N.1c keeps the same manual planner add flow but changes how the canvas communicates it. The goal is that the build map can be scanned visually before the user has to read detail copy.

Implemented behavior:

- unselected body rows are primarily passive map rows: body marker, body name, compact slot indicators, planned/projected structure pills, and warnings
- selected body rows expose the clear add targets for manual editing: `Add Orbit`, `Add Surface`, and selected empty-slot `+` targets
- passive empty capacity is represented by compact dots or no visible box; inert empty boxes do not look like buttons
- zero-slot lanes render no fake empty boxes and no add target; selected rows show a compact no-slot state when useful
- the canvas and selected-body detail share the same lane classifier
- orbital-only templates are displayed only in orbit lanes, surface-only templates only in surface lanes
- dual-location placements added from the planner picker keep the selected lane as a local lane hint
- dual-location placements without a reliable lane hint are shown as `Needs lane` rather than guessed into ground
- selected-structure telemetry reports `needs lane` for unresolved flexible placements
- the picker now uses `Add to [body]`, lane chips, compatible counts, and search across display name, variant/name, family, category, economy, tier, pad, location, and prerequisite text

reference planner visual direction adopted:

- structure state is carried by slot pills, small status chips, economy micro-bars, warning chips, and tree/slot geometry rather than long repeated sentences
- longer explanations such as contextual station economy and prerequisite details remain available in tooltips, selected structure detail, telemetry, or plan health
- compact `CTX` and `REQ` chips mark contextual economy and prerequisite warning states on the main canvas

Safety and passivity:

- clicking projected ghost slots selects projection context only
- opening the picker does not open Advanced Planner
- adding from the picker does not run Preview, generate a Suggested Build, or load a projected candidate
- prerequisites remain warnings, not blockers
- hard-invalid physical placement remains blocked by lane/body compatibility checks

Remaining manual editing gaps:

- no drag/drop or slot index persistence
- no backend-persisted per-placement lane field
- no one-click prerequisite insertion action
- no Architect observed slot storage

## Stage 17N.1e Slot Box Truth, Physical Compatibility, And Inherited Station Baseline

Stage 17N.1e cleans up the residual visual ambiguity in the planner whole-system canvas, separates physical compatibility from free-text prerequisites, and gives contextual stations a usable inherited economy baseline before Preview is run.

Implemented behavior:

- the default planner canvas no longer renders the small cyan/green dot strip next to body names; the helper `SlotCapacityDots` is retained only for the Advanced drawer
- every body row renders real, capacity-accurate slot boxes on both selected and unselected rows; empty slots stay passive `<span>` elements and only the row-level `Add Orbit` / `Add Surface` controls open the picker
- lane capacity chips use the format `Orbit N` and `Surface N` with the count rendered in a larger display font and `tabular-nums`, so the count is unambiguous and never reads as a padded `02`
- known-zero and unknown lanes still fall through to the compact `No orbital slots` / `No surface slots` / `? slots` state; known positive capacity always renders boxes
- physical compatibility is now first-class: `templatePhysicalIncompatibilityReason(template, body, lane)` in `structurePlanningRules.ts` is the single source of hard-invalid placements
  - Asteroid Station templates (detected via id/name/category tokens) require `is_ringed === true` and are hidden by the picker on non-ringed bodies, never surfacing as a missing prerequisite
  - water-world and non-landable surface rules route through the same helper
- catalogue free-text prerequisite descriptions that describe slot/lane/ringed-body conditions (for example `orbital slot available`, `requires a ringed body`, `landable body`, `water world`) are filtered out of structure prerequisite warnings; slot/lane truth is enforced by capacity and physical-compat rules instead, eliminating the false `needs orbital slot` warning class
- the overflow slot now reports `Orbital capacity exceeded` / `Surface capacity exceeded` copy in its tooltip and adds to the row warning indicator, recommending Architect Mode verification rather than blocking planning
- contextual stations and ports without direct economy metadata now show an inherited baseline economy micro-bar. Stage 17N.2e replaces the original system-economy/body heuristic with ED-Finder's Mega Guide-derived body economy profile formula and Preview body-profile weights; the chip and tooltip continue to flag the value as inherited/contextual and not a final Preview outcome

Explicit non-behavior:

- no automatic Preview, Suggested Build, or projected candidate load
- no Advanced Planner requirement for direct manual adds
- no invented CP magnitudes. Inherited baseline percentages are shown only when the body-profile formula can derive them from available body data; no-rule cases remain unavailable instead of fabricating values
- prerequisites remain warnings, not blockers
- empty slot boxes stay passive — only the row-level `Add Orbit` / `Add Surface` controls open the picker

Remaining manual editing gaps:

- baseline economy still does not include CP yellow/green magnitudes, contamination risk, weak/strong link analysis, or pass-through composition; those continue to require Preview
- backend prerequisite metadata is not yet typed for "structure prerequisite" vs "slot/lane condition" — the frontend filter is a token allow-list and should migrate to a typed field once the catalogue exposes it
- Architect observed slot truth and a first-class ringed-body field remain a later stage

## Stage 17N.1f Planner Canvas Micro-Polish

Implemented behaviours:

- visible `PLAN`, `CTX`, and `REQ` text labels removed from structure boxes on the main canvas; structure kind is communicated through styling (border colour, gradient, dashing) not label clutter; underlying testids and `sr-only` content preserved for accessibility
- body names now use `text-silver-lt` for better contrast; body subtype uses `text-silver/85`; structure labels use `text-[11px]` with `text-silver-lt`
- Orbit/Surface lane chip label upsized to `text-[11px] font-semibold`, count to `text-[15px] font-bold` so both scan as one coherent unit
- selected row inset border widened to 4px; Add Orbit / Add Surface buttons use `text-[11px] font-semibold` with increased padding/opacity for clear primary action affordance
- economy micro-bar height increased from `h-1` (4px) to `h-2` (8px) for readable segmented colours and reliable hover target; tooltip preserved for both direct and inherited baseline bars

Explicit non-behaviour:

- empty slot boxes remain passive `<span>` elements on all rows — they do not present hover/click button styling
- no new visible labels introduced as replacements for removed PLAN/CTX/REQ
- no layout changes: map dominance, no inline body expansion, no stacked panels above map

---

## Stage 17N.2 — Rating and Distance Trust Recovery

### Rating display

The `RatingRadar` component was rewritten to surface the full rating contract:

- **Headline**: "Best-build potential" with overall score (replaces bare "Overall" hex centre)
- **Score explanation**: "Based on body mix, economy fit, strategic value, and slot potential."
- **Extraction**: 7th radar axis and economy bar (was missing from original 6-axis display)
- **Top pair**: "Top pair: Refinery + Industrial (82)" chip parsed from `score_breakdown.top_pair`
- **Primary / secondary economy**: chips from breakdown or system-level fields
- **Confidence**: coloured tier badge (High/Medium/Low + percentage) or "Confidence unknown"
- **Rationale**: border-left blockquote when available
- **Expandable dimensions**: Slots, Strategic, Safety, Terraforming, Diversity bars behind toggle
- **Graceful degradation**: missing breakdown → no toggle; missing top pair → no chip; all-zero scores → render nothing

### Distance display

**Backend root cause**: `_build_system_record` used `float(row.get("dist", 0) or 0)` — galaxy-wide searches emitted `dist_expr = "0.0"` for every row, coercing unknown distance to `0.00 LY`.

**Backend fix**: `_safe_distance()` returns `None` for `None`, non-finite, and `≤ 0` values.

**Frontend root cause**: `ResultCard` passed `0` through `toFixed(2)` as `0.00`; fallback was `?` instead of consistent `—`.

**Frontend fix**: `formatDistance()` in `lib/format.ts` — returns `null` for unknown, used by all distance display sites. Zero treated as unknown unless `allowZero: true`.

### Planner canvas

No changes to planner canvas layout, slot boxes, add flow, station economy baseline, picker compatibility, or map dominance. Existing planner tests pass unchanged.



