# Stage 10C - Graphical Body Layout Planner Foundation

## Summary

Stage 10C evolves the Stage 10B body-grouped Build Plan into a more graphical, information-dense planner foundation while keeping the existing List view as the default editing surface.

The implementation is intentionally frontend-only. It does not change backend scoring, Simulation Preview mechanics, optimiser generation/ranking, Search Tuning, CP formulas, economy mechanics, service unlocks, buildability, Observed Evidence, Validation, saved-build persistence, auto-run behaviour, auto-generation, auto-loading, or hauling/material workflows.

## Implemented

- Renamed the body readout toggle to **Layout view**.
- Kept **List view** as the default and canonical detailed editor.
- Added a compact layout summary panel using existing frontend data:
  - system name
  - target archetype
  - total placements
  - assigned placements
  - unassigned placements
  - bodies used
  - primary-port status
  - total warning count
  - visible yellow/green CP generated and needed
  - Preview status: not run, stale, running, or current
- Added body-level layout cards with:
  - body name
  - body type/subtype and known tags
  - placement count
  - primary-port-body badge
  - body-level warning count
  - body-level CP generated/needed badges
- Added placement warning chips using existing plan/body/template data only:
  - no primary port selected
  - multiple primary ports selected
  - placement has no body
  - placement body ID does not match a known body
  - facility template missing
  - template uses estimated data
  - body metadata is sparse
  - surface facility on water world
  - surface facility on non-landable body
  - orbital suitability unclear when body metadata is too sparse
  - CP needs may exceed visible CP generation
  - Preview is stale
- Kept unassigned and unknown-body placements visible in the needs-review group.
- Removed destructive move/remove actions from Layout view so it remains a visual planning readout. Move/remove/edit actions remain in List view.
- Split pure grouping, summary, status, and warning logic into `buildPlanLayoutUtils.ts`.

## Data Used

Stage 10C uses only data already available in the Colony Planner frontend:

| Data | Source |
|---|---|
| System name | `SystemDetail.name` |
| Target archetype | `BuildPlanSection` local props |
| Placements | `SimulateBuildPlacement[]` |
| Body assignment | `placement.local_body_id` |
| Build order | `placement.build_order` |
| Primary port | `placement.is_primary_port` |
| Body name/type/subtype/tags | `SystemBody[]` |
| Template name/category/tier/economy/location/pad/confidence | `FacilityTemplate[]` |
| CP generated/needed | `FacilityTemplate` CP fields |
| Preview status | existing `previewResult`, stale flag, and running flag |

## Data Still Missing

Stage 10C does not invent data that ED-Finder does not have. These remain deferred:

- completed vs under-construction vs missing in-game colony facility state
- authoritative colony site/port inventory per body
- exact pre-preview prerequisite validity per body
- exact body-slot availability
- material requirements
- carrier stock
- hauling progress
- trip estimates
- saved build persistence
- account/profile persistence
- EDMC/journal ingestion

## Spansh Import Feasibility

Verified sources:

- `https://docs.spansh.co.uk/` exposes an OpenAPI document for the Spansh API.
- Current documented endpoints include:
  - `GET /api/system/{id64}`
  - `GET /api/dump/{id64}`
  - `GET /api/body/{id64}`
  - `GET /api/station/{marketId}`
- `GET https://spansh.co.uk/api/system/263303726260` returns a system record with bodies and stations for Alcor.
- `GET https://spansh.co.uk/api/search?q=Alcor` returns name-search results.
- `HEAD https://downloads.spansh.co.uk/galaxy.json.gz` and `HEAD https://downloads.spansh.co.uk/galaxy_stations.json` return 200.
- ED-Finder already has a Spansh dump importer using `galaxy.json.gz`, `galaxy_populated.json.gz`, and `galaxy_stations.json.gz`.

Conclusion:

| Category | Conclusion |
|---|---|
| Safe now | Continue using existing ED-Finder backend-imported bodies/stations for read-only planner layout. |
| Possible but needs backend support | Explicit user-triggered `Import / refresh system layout from Spansh` could be added later as a backend endpoint that fetches/caches Spansh data, validates it, and never silently overwrites user plans. |
| Needs more research | Station/site-to-body mapping reliability, Spansh API rate limits/terms/caching expectations, and how colonisation construction states should map into ED-Finder concepts. |
| Not safe to implement yet | Frontend-direct Spansh import, silent background refresh, or automatic overwriting of planner data. |

Recommended future shape:

- Import should be backend-side.
- Imported records should be cached in Postgres.
- The user should trigger refresh manually.
- ED-Finder should show what changed before using imported data to alter planner-facing state.
- Imported system layout should not mutate Build Plan placements without explicit user action.

## Why This Remains Low Risk

- The change is a frontend readout on top of existing plan/body/template props.
- It does not fetch data.
- It does not call Preview.
- It does not generate Suggested Builds.
- It does not load Suggested Builds.
- It does not mutate Observed Evidence or Validation.
- It does not change backend mechanics, scoring, formulas, ranking, or Search Tuning.
- List view remains the default editor.

## Tests

Stage 10C adds/updates tests for:

- List view remains default.
- Toggling to Layout view does not run Preview.
- Toggling to Layout view does not fetch Suggested Builds.
- Layout summary counts total, assigned, unassigned, and bodies-used values.
- Primary-port states: none, one, and multiple.
- Missing template warnings.
- Unknown body warnings.
- Estimated template warnings.
- Surface facility on water world warnings.
- Surface facility on non-landable body warnings.
- Preview stale warnings.
- Sparse body metadata handling.
- Unassigned placements remain visible.

## Deferred Work

- Structure picker/table.
- Facility variant picker.
- Right-side planner summary with selected body/site details.
- Actual graphical orbital/body map rendering.
- Saved builds.
- EDMC/journal ingestion.
- Spansh refresh endpoint and cache workflow.
- RavenColonial/SrvSurvey handoff/export feasibility.
- Material, commodity, carrier, hauling, and trip planning.

## Next Recommended Stage

Stage 10D should either add a richer selected-body/selected-placement details panel or begin the structure picker/table work if the catalogue data is ready. Spansh import should remain a separate backend-supported stage because it has data ownership, caching, and overwrite-safety implications.

## Stage 10D Follow-Up

Stage 10D follows the selected-detail path. Layout view now supports local, read-only selection of body groups and placement cards:

- Selecting a body highlights that body group and opens a detail panel with body tags, placement count, primary-port-on-body state, CP generated/needed from visible templates, body-level warnings, and a compact placement list.
- Selecting a placement highlights that placement card and opens a detail panel with facility/template name, build order, assigned/unassigned/unknown body state, primary-port flag, allowed location, tier, pad, economy, role/category, CP generated/needed, confidence, placement warnings, and the guidance to use List view for editing.
- The default summary state invites users to select a body or placement and repeats plan-level counts, primary-port status, warning count, Preview status, and next safe action.

Stage 10D remains frontend UX/layout work only. Selection does not mutate the Build Plan, does not run Preview, does not generate or load Suggested Builds, does not fetch new layout data, and does not change backend scoring, CP formulas, economy/service/buildability mechanics, optimiser generation/ranking, Search Tuning, Observed Evidence, Validation/Review, persistence, or hauling/material workflows.

The structure picker/table, variant comparison, add/replace workflow, facility selection from Layout view, Spansh refresh workflow, saved builds, external ingestion, and material/commodity/carrier/trip planning remain deferred.

## Stage 11A Follow-Up

Stage 11A keeps the Stage 10C/10D planner mechanics intact and starts a visual redesign foundation pass:

- stronger workflow hierarchy across Suggested Builds, Build Plan, and Preview Result
- clearer later-step framing for Observed Evidence and Validation
- cleaner planner copy and section signposting
- visual polish for workspace/header/readout cards while preserving List view as the editing surface and Layout view as read-only planning output

Stage 11A does not add hauling/material execution tracking and does not change simulation scoring, optimiser generation/ranking, Search Tuning, or backend mechanics.

## Stage 11B - Layout Cards, Detail Panel, and Workflow Hierarchy Polish

Stage 11B deepens Layout readout clarity without altering planner behavior:

- Added further card-level polish to `BuildPlanBodyView.tsx`:
  - clearer body group headers and metadata rows
  - stronger selected-state contrast for selected groups and placements
  - tighter warning and metadata chip rhythm
  - improved unassigned/needs-body presentation
- Expanded `BuildPlanLayoutDetailPanel.tsx` grouping:
  - explicit planning-readout section headers for summary/body/placement context
  - compact metric and warning sections
  - stronger “use List view to edit” guidance
- Improved section hierarchy in `ColonyPlannerSectionNav.tsx` so primary planning steps are visually emphasized and Observed Evidence / Validation are clearly later steps.
- Preserved all Stage 11A safeguards:
  - List view remains canonical for edits
  - Layout view remains read-only planning readout
  - no Preview auto-run, no Suggested Builds generation/load side effects, no backend mechanics changes.

Deferred beyond Stage 11B:

- deeper body-map visualizations
- structure picker/table interaction enhancements
- saved plans/project persistence
- hauling/material execution workflow

## Stage 11C - Colony Planner Visual Redesign QA / Final Polish

Stage 11C performs final UX QA on the dedicated planner before Stage 12:

- Polished Planner workflow signalling in `ColonyPlannerSectionNav.tsx` so `Suggested Builds → Build Plan → Preview Result` reads as the active path while Observed Evidence and Validation remain visually later.
- Fixed visual separator/encoding issues in the workflow path and improved layout wrapping around chips on medium and narrow widths.
- Kept Selection and keyboard interaction boundaries:
  - List view is still the default and editable surface.
  - Layout view remains a read-only planning readout.
  - body/placement selection still works in Layout view without side effects.
- Applied small readability/accessibility tweaks in `BuildPlanLayoutDetailPanel.tsx` (focus treatment and clearer selected-state framing).
- Preserved all mechanical boundaries:
  - no automatic Preview run
  - no automatic Suggested Builds generation/load
  - no backend scoring or optimiser ranking changes
  - no hauling/material execution flow added

## Stage 11D - Reviewer-Driven Visual Hierarchy Refinement

Stage 11D keeps the 11C planning surface intact and applies reviewer-driven copy and hierarchy nudges:

- Strengthened workflow labeling around `Suggested Builds -> Build Plan -> Preview Result`.
- Kept `Observed Evidence` and `Validation` as clearly marked later steps.
- Preserved the separate interactive controls model (`Layout view` body selection and placement selection).
- Reaffirmed no backend or mechanics changes from this polish.

## Stage 11E - Interaction & Copy Hardening

Stage 11E is a focused micro-polish to harden interaction clarity, copy consistency, and spacing on top of the 11D baseline:

- Tightened planner copy in workspace header and section nav so planning intent and workflow are explicit.
- Kept `List view` as the canonical edit path and `Layout view` as the readout path, with explicit read-only guidance.
- Confirmed layout interaction safety remains unchanged (no nested interactive regions, no preview/candidate side effects on selection).
- Updated test focus for nav wording, `List` / `Layout` framing copy, and selection behavior.
- No new mechanics, backend API, scoring, or planning simulation changes were made.

## Deferments after Stage 11E

- Facility variant workflows and deeper table-based picker enhancements.
- Body map / orbital visualization beyond current card layout.
- Execution/logistics features (carrier stock, hauling, commodity planning).
- Build persistence/account/state products and automatic learning.
- Legacy `ratings.rationale` text may remain from older imports; no frontend scoring rule changes are being made in this stage. If stale `Strong Refinery; via ...` phrasing appears, rebuild that system’s rating through the importer or maintenance path that writes `rationale` (not UI-only text stripping) before relying on it as an authoritative explanation.

## Stage 11F - Micro-Polish and QA Guardrails

Stage 11F is a narrow UX polish and wording alignment pass over the existing Colony Planner visual workflow before deeper planning interaction work resumes.

- Preserved the established boundaries: `List view` remains the canonical edit surface; `Layout view` remains a read-only planning readout.
- Reconfirmed primary flow clarity (`Suggested Builds -> Build Plan -> Preview Result`) and later-step framing for `Observed Evidence` and `Validation`.
- Preserved safe selection and keyboard behavior for body/placement interactions.
- Kept all mechanical surfaces unchanged (no scoring, no optimiser behavior changes, no backend mechanics edits, no hauling/logistics features).

## Stage 11G - Workflow Label Consistency and Header Micro-Polish

Stage 11G is a mechanics-safe cleanup for label and header consistency after 11F wording alignment.

- Normalized planner and header workflow labels to the same planner naming and reduced redundant / inconsistent phrasing.
- Added explicit checks to keep `Observed Evidence` and `Validation` visually secondary and non-primary in flow copy.
- Preserved all interaction constraints: no auto-preview triggers, no suggested-build side effects, and no backend behavior changes.

## Stage 11H - Layout Import Staleness Guardrail

Stage 11H is a narrow follow-up to clear stale layout-import UI state when switching systems.

- Reset layout-import status in `BuildPlanSection` on system ID changes so old import errors/results do not persist into a new system view.
- Maintained mechanics safety: no simulation/mechanics/autoload behavior changes.

Chronology note:

- Stage 11F happened before Stage 11G, and Stage 11H follows Stage 11G.
