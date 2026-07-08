# Stage 17A — Colony Planner Intelligence / Source Alignment / Forward Plan

> Historical reference only. This forward plan is preserved as stage rationale,
> not as the active control queue. Use `docs/ROADMAP.md` for current priorities
> and `docs/colonisation-redesign/README.md` for the active read order.

Stage 17A is a report and planning stage only. It does not implement app behavior, change backend mechanics, change scoring, alter CP formulas, add ingestion, or change Colony Planner UI behavior.

## Executive Summary

ED-Finder's Colony Planner has reached the point where more features should not be added until the source strategy, trust fixes, surface-slot prediction evidence, picker roadmap, visual planning direction, external ingestion boundary, and reference planner product boundary are aligned in one place.

The next build phase should prioritize trust before expansion:

1. Fix or classify the rating-rationale issue around phrases such as `Strong Refinery via 2 ELW / WW`.
2. Explain or remove the ambiguous Finder score bar.
3. Implement the user-supplied surface slot prediction heuristic as a labelled prediction helper, not confirmed truth.
4. Expand the structure picker and variant table using existing catalogue fields first, then enrich catalogue data deliberately.
5. Keep reference planner as inspiration and a possible handoff target, not a workflow to clone.

The requested committed reference pack path `docs/reference/colonisation/` was not present on latest `main` during this review. A user-supplied archive was then provided at `C:\Users\brian\Downloads\ed-finder-colonisation-reference-pack.zip`; this report uses that archive inventory and its source-priority notes, while still noting that the pack itself is not committed on latest `main`.

## Current State

This audit is based on latest `main` at `f52446d` (`Stage 16B: workspace cleanup before role implementation`) and the merged Stage 16 PR history.

| Area | Current status | Confidence |
|---|---|---|
| Colony Planner workspace | Dedicated `#colony-planner/system/{id64}` workspace exists. System Detail is now an overview/entry surface rather than the full embedded planner. | High |
| Suggested Builds | Existing optimiser-backed Suggested Builds remain explicit user action. Stage 15F added frontend usefulness filtering and workspace loading copy without backend ranking/scoring changes. | High |
| Build Plan List view | List view remains the canonical edit surface. Structure picker and replacement review are attached to List view rows. | High |
| Layout view | Read-only body-grouped graphical planning readout exists, with body cards, placement cards, topology context, strategic guidance, and selected body/placement detail. | High |
| Selected body / placement detail panel | Layout selection detail exists and is read-only; edits remain in List view. | High |
| Structure picker/table foundation | Stage 12A-12C added table, filters, grouping, replacement comparison, and warning deltas using existing template/body data. | High |
| Local-only project persistence | Stage 15G added localStorage saved Colony Projects. Stage 16B clarified this is local to the browser and not cloud synced. | High |
| Evidence / Validation drawers | Stage 15H moved Observed Evidence and Validation into explicit drawers/modes. Stage 16B moved controls into the persistent summary rail while content remains in the central planner boundary. | High |
| Workspace summary rail | Stage 16B split the rail into compact Project, Plan Health, Selection, Architect, Workspace Modes, and save-state cards. | High |
| Role / planning model work | Stage 16A is a report-only role model plan. Stage 16B is cleanup before role implementation. Role editing, badges, migration, and persistence remain deferred. | High |
| Reference pack | Not committed on latest `main`, but a user-supplied archive was available during Stage 17A. It contains the expected `docs/reference/colonisation/` layout, source-priority notes, guides, DaftMav workbook, diagrams, reference planner screenshots, and UI issue screenshots. | High |
| Known trust issues | Surface slot prediction, bad rating rationale, and score-bar ambiguity are user-reported and should be planned before wider intelligence expansion. | High |

Uncertainty: no committed source pack files were available at the requested path on latest `main`. The local archive was inventory-checked and its README, source-priority, prompt snippet, guide text samples, workbook sheet names, and UI/reference planner screenshot metadata were inspected. This is enough for Stage 17A source alignment, but later mechanics stages should still read the committed pack directly before making mechanics claims.

## Source Priority And Reference Pack

### Source Hierarchy

| Priority | Source class | Use |
|---|---|---|
| 1 | Elite Dangerous Colonization Mega Guide | Primary mechanics authority. If another source conflicts, prefer the Mega Guide and document the conflict. |
| 2 | User-supplied empirical findings and spreadsheet analysis | High-value empirical evidence, especially the surface slot prediction dataset and formula. Use as prediction evidence until confirmed by independent observed/imported data. |
| 3 | DaftMav Colonization Construction spreadsheet | Catalogue, construction, and structure comparison support. Useful for picker/table enrichment. |
| 4 | OASIS Guide for Bootstrapping a Bubble | Supporting planning workflow context and bootstrapping strategy. |
| 5 | Fandom System Colonisation PDF, Frontier Forum strong/weak link PDF, AetherWave PDFs, construction prerequisite image, link diagrams, infographics | Secondary clarification, visualization, and cross-checking. Do not silently merge conflicting claims. |
| 6 | reference planner screenshots/tooling | UI and workflow inspiration, possible handoff target, and logistics comparison boundary. Not mechanics authority for ED-Finder scoring. |
| 7 | Future external sources: EDMC, EDDiscovery, EDSM, EDDN, Spansh, reference planner plugin data | Imported evidence/source data with trust, staleness, and review controls. Not automatic mechanics truth. |

### Conflict Rule

When sources conflict:

1. Prefer the Mega Guide.
2. Record the conflict explicitly.
3. Use supporting sources only to clarify, visualize, or provide newer verified evidence.
4. Do not silently average, merge, or hide conflicting claims.

### Reference Pack Status

Expected source-pack paths were checked on latest `main` and were not present there:

- `docs/reference/colonisation/README.md`
- `docs/reference/colonisation/source-priority.md`
- `docs/reference/colonisation/codex-reference-prompt-snippet.md`
- `docs/reference/colonisation/guides/`
- `docs/reference/colonisation/spreadsheets/`
- `docs/reference/colonisation/diagrams/`
- `docs/reference/colonisation/ravencolonial-ui/`
- `docs/reference/colonisation/ui-issues/`

The user-provided archive `C:\Users\brian\Downloads\ed-finder-colonisation-reference-pack.zip` was then inspected and contains:

- `docs/reference/colonisation/README.md`
- `docs/reference/colonisation/source-priority.md`
- `docs/reference/colonisation/codex-reference-prompt-snippet.md`
- `docs/reference/colonisation/guides/elite-dangerous-colonization-mega-guide.docx`
- `docs/reference/colonisation/guides/oasis-guide-for-bootstrapping-a-bubble.docx`
- `docs/reference/colonisation/guides/fandom-system-colonisation.pdf`
- `docs/reference/colonisation/guides/frontier-forums-strong-weak-links.pdf`
- `docs/reference/colonisation/guides/aetherwave-*.pdf`
- `docs/reference/colonisation/spreadsheets/daftmav-colonization-construction-v3.xlsx`
- `docs/reference/colonisation/diagrams/`
- `docs/reference/colonisation/ravencolonial-ui/`
- `docs/reference/colonisation/ui-issues/`
- `docs/reference/colonisation/user-docs/`

Archive inspection notes:

- `source-priority.md` explicitly marks the Elite Dangerous Colonization Mega Guide as the mechanics bible.
- `codex-reference-prompt-snippet.md` gives the intended future prompt rule for mechanics, planner warnings, picker validity, CP logic, strong/weak links, dependencies, and economy influence.
- The Mega Guide text sample identifies it as `Elite Dangerous Colonization Mega Guide Version 2.3.0` with a revision-history note for 2.4.0 WIP.
- The OASIS text sample says it was last updated on 2025-10-29 and warns that ELW/WW T3 intrinsic value changed from earlier assumptions.
- The DaftMav workbook contains sheets including `Changelog`, `Settings`, `Lists`, `Commodities`, `Stats`, `Cargo Hauling`, and `Colony1` through `Colony20`.
- The UI issue screenshots include `finder-score-bar-ambiguity.png` and `incorrect-refinery-rationale-elw-ww.png`.
- The reference planner screenshots cover hauling tracker, colony builder system map, structure picker dropdown, and structure picker table.
- A separate surface-slot analysis spreadsheet was not visible in the archive inventory by that name; until such a file is committed or attached, the surface-slot dataset remains a user-provided empirical finding.

Result: the reference pack was available for this Stage 17A report as a user-supplied archive, but it should be committed under `docs/reference/colonisation/` before mechanics-heavy implementation stages rely on it.

### Future Codex Prompt Rule

Future implementation prompts should start with:

> Inspect `docs/reference/colonisation/README.md` and `docs/reference/colonisation/source-priority.md` first. Treat the Elite Dangerous Colonization Mega Guide as the primary mechanics source. If it conflicts with OASIS, DaftMav, Fandom, Frontier forum PDFs, AetherWave PDFs, diagrams, spreadsheets, or screenshots, prefer the Mega Guide and document the conflict. Treat reference planner as UI/tooling inspiration and possible handoff target only.

## Surface Slot Prediction Heuristic

### User-Provided Formula Summary

The user supplied a candidate JavaScript heuristic:

```js
function predictSurfaceSlots3(bodyRow) {
  if (bodyRow[SurfaceTempIndex] > 700
    || bodyRow[GravityIndex] > 2.7
    || !bodyRow[LandableIndex]) {
    return 0;
  }

  const radius = bodyRow[RadiusIndex];
  let predictedSlots = radius < 1500 ? 1
    : radius < 3750 ? 2
    : radius < 6000 ? 3
    : 4;

  if (bodyRow[BodySubtypeIndex] === "High metal content world") predictedSlots++;

  let modifierBonus = 0;
  if (bodyRow[TerraformableIndex]) modifierBonus++;
  if (bodyRow[VolcanismIndex] || bodyRow[GeoIndex]) modifierBonus++;
  if (bodyRow[AtmosphereIndex] !== "No atmosphere") modifierBonus += 2;

  predictedSlots += Math.min(modifierBonus, 3);
  return Math.min(predictedSlots, 7);
}
```

Formula behavior:

- Rejects non-landable, too-hot, or too-heavy bodies as `0`.
- Starts from radius buckets: `<1500 => 1`, `<3750 => 2`, `<6000 => 3`, otherwise `4`.
- Adds one slot for High metal content worlds.
- Adds up to three modifier slots for terraformability, volcanism/geology, and atmosphere.
- Caps total predicted surface slots at `7`.

### Dataset Summary

User-provided evidence:

- Original claim: 94.72% accuracy on 4,654 landable bodies.
- Later spreadsheet analysis found only four apparent mismatches.
- Two of those four were data typos.
- Therefore only two real mismatches remain.

This deserves implementation, but as a prediction heuristic, not confirmed truth.

### Implementation Recommendation

ED-Finder should implement the heuristic, but in a deliberately bounded way:

| Question | Recommendation |
|---|---|
| Should ED-Finder implement it? | Yes, because the user-provided evidence is strong and the planner needs slot context. |
| Frontend, backend, or shared? | Start as a pure shared/domain helper if the repo has an appropriate shared mechanics layer; otherwise backend helper plus frontend type exposure. Keep UI display thin. |
| Where first? | Layout view body detail, topology/summary rail, and Structure Picker body context. |
| Should it feed Layout view? | Yes, as `Predicted surface slots` or `Estimated slots`. |
| Should it feed structure picker validity? | Yes, as advisory capacity context only. It may warn about likely slot pressure but should not block selection initially. |
| Should it feed Suggested Builds? | Not in the first implementation. Candidate generation and ranking need separate scope and validation. |
| Should it feed search ranking? | No. Do not use it in Finder or Search Tuning scoring until separately scoped, validated, and explained. |
| How to label it? | Use `Predicted surface slots`, `Estimated surface slots`, or similar. Never `Known slots` or `Confirmed slots`. |
| Override rule | Observed/imported Architect slot counts override predictions wherever both exist. |

### Required Body Fields

The helper needs normalized body data for:

- surface temperature
- gravity
- landable flag
- radius
- subtype, specifically High metal content world
- terraformable flag
- volcanism
- geological signal count or equivalent geo marker
- atmosphere, specifically No atmosphere vs any atmosphere

### Normalization Required

Before implementation, normalize:

- `High metal content world` casing and spelling.
- `No atmosphere` casing, empty/null atmosphere values, and thin atmosphere labels.
- `is_landable`, including null/unknown.
- `is_terraformable`, including string and boolean variants if importer data differs.
- Volcanism labels, including `No volcanism`, empty strings, null, and any non-empty volcanic activity.
- Geo/bio fields, especially whether `GeoIndex` maps to geological signals only or combined biological/geological signals.
- Radius units and temperature units.
- Gravity units, including whether source values are already in G.

### Tests Required

When implemented:

- Unit tests for every threshold boundary: `700`, `2.7`, `1500`, `3750`, `6000`, cap at `7`, HMC bonus, atmosphere bonus, volcanism/geo bonus, terraformable bonus.
- Null/unknown normalization tests.
- Dataset-derived validation tests from the spreadsheet.
- Fixture rows for the two real mismatches, marked expected mismatches so future changes do not pretend perfect accuracy.
- Override tests proving observed/imported Architect slot counts win over predictions.
- UI tests proving predicted labels never say confirmed/known.
- No-side-effect tests proving prediction does not alter scoring, Suggested Builds ranking, Simulation Preview scoring, Search Tuning, or buildability mechanics.

### Repo Dataset Recommendation

Commit a small validation fixture under a future source-pack path, for example:

- `docs/reference/colonisation/spreadsheets/surface-slot-prediction-validation-notes.md`
- `tests/fixtures/colonisation/surface_slot_prediction_cases.json`

The fixture should include anonymized or source-permitted rows covering thresholds, representative matches, the two real mismatches, and the corrected typo cases if redistribution is allowed.

## Trust-Critical Bug: Rating Rationale Audit

User-observed bad rationale copy:

> Strong Refinery via 2 ELW / WW

Issue:

- The wording is misleading.
- It was supposed to have been fixed.
- It may be an active rationale generation bug, stale DB rationale, or frontend display issue.

This is trust-critical because it affects whether users believe ED-Finder's scoring explanations.

Recommended Stage 17B audit:

1. Search backend/frontend for:
   - `Strong Refinery`
   - `ELW`
   - `WW`
   - `earth-like`
   - `water world`
   - `rationale`
   - `score_refinery`
   - `displayRationale`
2. Determine whether the phrase is generated now or stored from older ratings.
3. If active generator: fix generator and add focused tests.
4. If stale data: document refresh/recompute path and add UI copy that does not pretend the frontend fixed the source.
5. Avoid blindly hiding rationale unless there is no safer option.

Near-term acceptance:

- A developer can reproduce whether the phrase comes from code or data.
- Tests cover the corrected branch.
- Stale stored rationale has an explicit refresh/recompute plan.

## Small UI Fix: Finder Score Bar

User observed a green horizontal bar on the right side of a Finder result row.

Issue:

- No tooltip or explanation.
- It likely duplicates the numeric score such as `EXCELLENT 97`.
- It may be redundant visual noise.

Recommended Stage 17B fix:

- Decide whether the bar adds value beyond the numeric score.
- If it adds value, add a title/tooltip and accessible label such as `Rating score: 97/100`.
- If it does not add value, remove it.
- Add a focused UI test for the final decision.

This is smaller than the rationale bug, but it belongs in the same trust/UI stage because both affect user confidence in scoring.

## Structure Picker / Variant Table Roadmap

### Existing Foundation

Based on current docs, the picker foundation includes:

- Dedicated `StructurePickerTable`.
- Search and location filters: All, Orbital, Surface, Both.
- Existing columns: structure, location, tier, pad, economy, role, CP gives/needs, confidence, validity, action.
- Body-context hints and conservative warnings.
- Grouping by derived categories from existing catalogue fields.
- Replacement review with current/proposed comparison and warning deltas.

### Fields Available Now

The picker can use current frontend template/body data:

- template id/name/category/tier/economy
- port/support flags
- allowed location
- pad size
- confidence
- notes
- yellow/green CP generated and needed
- body name/type/subtype
- landable, terraformable, ELW/WW/AW style flags where present
- bio/geo signal counts if available
- predicted surface slots once Stage 17C lands

### Near-Term Expansion

Stage 17D should add:

- Better family/variant grouping.
- Compact variant rows under family headers.
- Sort controls for location, CP, economy, tier, validity, and confidence.
- Body-context panel beside the table.
- Predicted surface slot support once Stage 17C exists.
- Clear validity labels: `Allowed`, `Likely risky`, `Incompatible`, `Needs body`, `Unknown`.
- Replacement comparison retained as the deliberate apply step.

### Validity Hardening

Stage 17E should harden:

- Surface facility on non-landable body.
- Surface facility on water world.
- Likely surface slot pressure from predicted slots.
- Unknown/observed Architect slot override logic.
- Sparse metadata and estimated template data.
- Primary-port guidance remains read-only and evidence-backed.

### Catalogue Enrichment Needed

Deferred catalogue work:

- Stable structure family metadata.
- Variant display names.
- Prerequisite details.
- Population/max-pop/security/wealth/technology/standard-of-living/development impacts if source-backed.
- Material/commodity requirements only as future handoff/export context, not ED-Finder logistics execution.

## Visual Planner / Body Map Roadmap

Current Layout view is a read-only card/tree planning view. It is not yet a true spatial body/orbital/ground map.

Future work should be staged:

1. Richer Layout cards: tighter body role badges, predicted/observed slot chips, warning density controls, source-backed tooltips.
2. Right-side selected body/site panel: summarize selected body, planned placements, predicted slots, observed slots, warnings, and next action.
3. Inline link/CP/economy warnings: keep explanations near the placement/body they affect.
4. Source-backed popovers: show which rule/source explains a warning without turning the page into a wall of text.
5. Topology/strong/weak link visualization: only after source pack and current mechanics docs agree on what can be shown honestly.
6. Primary-port and local-body strategy clarity: show Architect status as unknown/predicted/observed, never arbitrary user truth.
7. Actual visual body map: separate stage, with mobile/desktop layout verification and no scoring changes.

Do not over-scope the next implementation. Stage 17C/17D should improve the current planner surfaces before a map-like canvas is attempted.

## External Data Ingestion Roadmap

Future ingestion sources to audit:

- EDMC
- EDDiscovery
- EDSM
- EDDN
- Spansh
- reference planner / reference planner EDMC plugin

Rules:

- Imported data is evidence/source data, not silent mechanics truth.
- Track source, timestamp, freshness, confidence, and import method.
- No automatic scoring rewrite.
- No automatic CP/economy/service/buildability mechanics mutation.
- No silent Build Plan mutation.
- Manual review before changing planner-facing state.
- API keys, commander data, journal paths, and plugin data must be protected.
- Imported observations should flow into Observed Evidence / Validation concepts before they affect recommendations.

Recommended Stage 18A:

- Feasibility report only.
- Map each source to data classes ED-Finder could use.
- Define security/privacy posture.
- Define staleness/trust model.
- Identify licensing and redistribution constraints.
- Decide what belongs in ED-Finder vs a reference planner handoff.

## reference planner Boundary And Handoff Options

reference planner is excellent for:

- construction logistics
- hauling/materials
- carrier stock
- project progress
- trip estimates
- execution tracking

ED-Finder should not clone that workflow.

ED-Finder should focus on:

- finding systems
- planning/intelligence
- Suggested Builds
- Build Plan layout
- structure choice
- predicted/observed comparison
- warnings/rationale
- validation

Possible future handoff:

- Export current system, body, planned placements, structure ids/names, role intent, predicted/observed slot context, and notes if format and licensing are feasible.
- Deep-link or file export to reference planner if reference planner supports it.
- Investigate reference planner EDMC plugin/source only for interoperability boundaries, not cloning.
- Never expose API keys or private commander data.
- Do not add carrier stock, commodity hauling progress, or trip planning inside ED-Finder unless a future product decision explicitly changes the boundary.

## Recommended Next Stages

| Stage | Name | Purpose | Scope | Non-goals |
|---|---|---|---|---|
| 17B | Trust/UI fixes | Fix trust-critical scoring/rationale issues before adding planner intelligence. | Rationale forensic audit/fix; Finder score bar explain/remove; focused tests. | No scoring formula changes unless the active rationale generator is proven wrong and separately tested. |
| 17C | Surface Slot Prediction Heuristic | Implement predicted surface slot helper and display it honestly. | Pure helper, normalization, unit tests, dataset fixtures, Layout/body detail/picker labels, observed override. | No Suggested Builds ranking, Finder ranking, Simulation Preview scoring, or buildability mechanics changes. |
| 17D | Structure Picker / Variant Table Expansion | Make structure choice easier using current catalogue fields. | Family/variant grouping, sorting, body context, predicted slot display if 17C is done. | No backend catalogue migration unless separately scoped; no logistics/material workflow. |
| 17E | Structure Picker Validity Hardening | Improve pre-preview placement warnings and trust copy. | Validity labels, slot-pressure warnings, observed-vs-predicted slot override handling, tests. | No hard blocking unless source-backed and explicitly scoped; no scoring changes. |
| 17F | Visual Planner / Body Map Feasibility | Define the next visual map step without overbuilding. | Map/canvas feasibility, selected body/site panel design, source-backed popovers, responsive verification plan. | No immediate canvas rewrite; no reference planner visual clone. |
| 17G | Role Model Implementation Slice | Resume Stage 16 role work after trust and slot context are stable. | Read-only role badges or explicit user-declared role controls, depending readiness. | No role-aware optimiser scoring/ranking. |
| 17H | Durable Project Persistence Feasibility | Revisit the currently pencilled durable persistence stage with role/slot data included. | Backend/cloud persistence plan, export/import JSON, migration from localStorage, privacy model. | No silent autosave; no loss of local projects; no mechanics changes. |
| 18A | External Data Ingestion Feasibility | Plan imported evidence and source data before adding integrations. | EDMC, EDDiscovery, EDSM, EDDN, Spansh, reference planner/plugin audit; trust/staleness/security model. | No ingestion implementation, no automatic planner mutation, no mechanics mutation. |
| 18B | reference planner Handoff Feasibility | Define whether ED-Finder can export or hand off planning outputs. | Export/deep-link investigation, data shape, privacy boundaries. | No logistics clone, no carrier stock/trip planning. |

## Final Recommendation

Stage 17A should become the map before the next build phase. The immediate next stage should be Stage 17B, because bad rationale copy and unexplained score visuals undermine trust more than missing planner intelligence does. Stage 17C should then implement the surface slot prediction heuristic as a labelled estimate with observed/imported override behavior and strong tests. Structure picker and visual planner expansion should follow after the slot prediction and trust fixes are in place.

The user-supplied reference pack should be committed under `docs/reference/colonisation/` before any mechanics-heavy Stage 17 implementation. Until then, future work should explicitly state whether it used the committed pack or an attached/local archive and should not claim direct source verification where the repo does not provide it.

