# Reference Planner Clean-Room Economy Reference (Stage 17G/17H)

## Boundary

The reference planner was used only as a clean-room functional reference from the local Stage 17F evidence pack.

Used evidence:

- `.codex-context/stage17f/stage17f_codex_evidence/README.md`
- `.codex-context/stage17f/stage17f_codex_evidence/docs/stage_17f_codex_prompt.md`
- reference planner walkthrough video and extracted frames
- ED-Finder current-interface walkthrough video and extracted frames
- reference planner screenshots
- ED-Finder screenshots

The reference planner API was not required for this implementation. The temporary local key was not read, printed, echoed, logged, committed, or used.

## Observed Functional Behaviours

Clean-room product behaviours observed from the local evidence:

- reference planner makes the left/system surface the primary build map, not a simple text list.
- The user can scroll the whole system and see useful build state without clicking every body.
- Per-body orbital/ground capacity and placements are attached directly to body rows.
- Planned structures occupy visible body-local slots.
- Candidate/projected structures are visually distinct from committed/current structures.
- Economy/stat consequences are visible while planning, before an explicit final action.
- A compact persistent stats/economy panel supports planning without becoming the main editor.

## ED-Finder Stage 17G Interpretation

ED-Finder implements equivalent functional behaviour in its own code and visual language:

- whole-system left slot map in `ColonyTopologyRail.tsx`
- selected-body slot editor in `BodySlotPlanner.tsx`
- compact economy strips in `PlanningEconomyStrip.tsx`
- deterministic economy ledger from ED-Finder facility-template metadata in `planningEconomy.ts`
- Suggested Build projection into left map, centre lanes, summary rail, and candidate details

No reference planner source code, CSS, assets, icons, de-minified code, or proprietary implementation details are copied.

## Stage 17H Replacement Interpretation

Stage 17H exists because Stage 17F/17G still allowed the old ED-Finder report/card stack to define the default experience. The clean-room functional comparison made the gap clear:

- reference planner's left side acts as the whole-system build map.
- ED-Finder's prior default still felt like a planner dashboard with an advanced card stack.
- reference planner lets users understand body capacity and planned/proposed structures without clicking every body.
- ED-Finder needed visible orbital/ground lanes, planned occupancy, ghost projection, overflow, and economy strips directly in the left panel.

Stage 17H ED-Finder mapping:

- default route: `WholeSystemColonyPlanner.tsx`
- left system map: `SystemSlotMapPanel.tsx` / `ColonyTopologyRail.tsx`
- centre body editor: `SelectedBodyPlannerCanvas.tsx` / `BodySlotPlanner.tsx`
- compact status/economy: `PlannerStatusStrip.tsx`
- old stack demotion: `AdvancedPlannerDrawer.tsx`

This is a functional adaptation only. ED-Finder keeps its own dark sci-fi/orange/silver style, component structure, copy, CSS, icons, and data model.

Remaining clean-room gaps after Stage 17H:

- no drag/drop slot movement
- no permanent Architect-observed slot survey storage
- no reference planner logistics/project sync
- no advanced cargo/commander/project mutation flows
- no automatic plan synthesis or AI mutation

## Planning Economy Ledger

Stage 17G planning economy is intentionally lightweight:

- each planned structure contributes one count to its facility template `economy`, where metadata exists
- each projected Suggested Build structure contributes one projected count to its template `economy`, where metadata exists
- planned and projected contributions are visually distinct
- structures without economy metadata are counted as unknown metadata in expanded ledgers

Required wording:

`Planning economy mix — run Preview for validated outcome.`

The ledger does not replace Simulation Preview:

- no CP formula changes
- no port economy propagation changes
- no service graph changes
- no optimiser scoring/ranking changes
- no automatic Preview execution
- Preview remains explicit and authoritative

## Stage 17N.2e Economy Bar Contract

Stage 17N.2e keeps reference planner as a functional reference only: readable,
body-local economy bars and useful hover breakdowns. ED-Finder implements this
with its own code, colours, and mechanics.

Central colour mapping:

| Economy | Colour |
| --- | --- |
| Agriculture | `#4ade80` |
| Refinery | `#fbbf24` |
| Industrial | `#ff7a14` |
| HighTech | `#7dd3fc` |
| Military | `#f87171` |
| Tourism | `#c084fc` |
| Extraction | `#94a3b8` |
| Terraforming | `#2dd4bf` |
| Contextual / Unknown | neutral blue-grey/grey |

Planner bar rules:

- per-structure bars are 8-10px tall so they can be scanned and hovered
- all planner bars, projected bars, selected-body slots, RatingRadar economy
  bars, and the retained prototype use the same central mapping
- direct facility economy comes from ED-Finder catalogue/template metadata
- direct CP totals are shown only from real template `yellow_cp_generated` and
  `green_cp_generated` values
- station/port baseline bars are calculated from ED-Finder's own Mega
  Guide-derived body economy profile formula, not copied reference planner logic
- if no documented formula can produce a baseline, no fake percentage is shown
- Preview remains the final validation step for economy order, CP, links,
  services, pass-through, contamination, and build-order effects

## reference planner API Notes Kept For Future Work

The user-provided reference planner API concepts are recorded only as future reference for logistics/project interop:

- `buildId` is primary project key
- projects can be queried by `systemAddress` and/or `marketId`
- commodity names are lower-case and language agnostic
- commander names are lower-cased internally
- OpenAPI is available at `/openapi/v1.json`
- project APIs cover create/get/update/link/assign/contribute/supply/ready/complete/stats
- system APIs can find active/completed projects
- commander APIs can link commanders and assigned commodities
- fleet carrier APIs can manage carrier/cargo data

Stage 17G does not implement reference planner logistics sync and must not make mutating reference planner calls.


