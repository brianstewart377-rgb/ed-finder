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
