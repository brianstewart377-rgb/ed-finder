# Stage 17A/17B Colony Architect Report

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

The rescue is functional rather than visual. It keeps ED-Finder's dark/orange brushed-steel style while borrowing the useful RavenColonial workflow principle that the body tree is the primary navigation surface.

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

## Stage 17E RavenColonial-Style Functional Build Planner Rebuild

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

## Stage 18 direction

Stage 18 should build a constrained Colony Architect assistant shell on top of Stage 17E:

- natural-language intent capture
- deterministic constraint translation
- explicit user review/acceptance
- no silent build mutation
- Preview remains the validation authority
