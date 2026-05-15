# Stage 8A Prep - Colony Planner Guided Workflow / Suggested-Builds UX Audit

## Executive Summary

Stage 8A should reframe Colony Planner around a guided, suggested-builds-first workflow. The current implementation already has the main mechanics: recommended builds, editable build plans, optimiser candidates, explicit preview execution, stale-preview detection, observed evidence, validation, and review guidance. The problem is not missing simulation depth; it is that the player path is buried, split across several adjacent panels, and still uses some implementation-first language.

Recommended Stage 8A direction:

- Make "Open Colony Planner" / "Evaluate in Colony Planner" a prominent action from system detail and search-result contexts.
- Make suggested builds the default first-run path.
- Preserve blank/manual planning as an advanced secondary path.
- Rename user-facing "Optimiser Candidates" to "Suggested Builds" where it appears in the planner flow, while keeping backend/internal optimiser terminology unchanged.
- Turn Preview Result into an interpreted outcome: verdict, why, warnings, CP/buildability summary, assumptions, and next steps.
- Add visible edit feedback: placement count, update notices, "Preview not run yet", and "Preview is stale" states.
- Keep Stage 8A frontend-only where possible. Backend mechanics, scoring, endpoints, validation, observations, and Search Tuning should not change in Stage 8A.

## Source Materials Reviewed

### Spreadsheet

Reviewed local file:

- `C:\Users\brian\Downloads\Copy of Colonization Construction v3 (By DaftMav)(1).xlsx`

The workbook was available and inspected directly with `openpyxl`.

Workbook structure:

- 26 sheets total.
- `Changelog`
- `Settings`
- `Lists`
- `Commodities`
- `Stats`
- `Cargo Hauling`
- `Colony1` through `Colony20`

Key inspected workbook facts:

- `Settings` has 100 rows x 17 columns, including search parameters, ship/cargo capacity values, colony tab names, system names, orbital slots, planetary slots, and OCR commodity input.
- `Stats` has 75 rows x 24 columns and acts as facility metadata: structure, max pad, prerequisites, system/strong-link unlock notes, T2/T3 point effects, stat deltas, facility economy, economy influence, and population data.
- `Cargo Hauling` has 78 rows x 21 columns. It lets the user select a colony tab, pulls active constructions, calculates commodity totals, and tracks carrier/ship/delivered/still-needed quantities.
- `Commodities` has 74 rows x 90 columns. Named ranges include `Com.Names`, `Com.Items`, `Com.BuildTotals`, and `Com.Structures`; this is the structure-by-commodity cost matrix.
- `Lists` has 729 rows x 140 columns. Named ranges include `List.Structures`, `List.Layouts`, `List.Pads`, `List.Score`, `List.PopMax`, `List.Bugs`, `List.Type`, `List.TaxNames`, `List.Tax`, and layout/variant ranges.
- Each `Colony` tab has 505 rows x 42 columns, with repeated build rows and formulas for active/done state, prerequisites, layout variants, max population, score, pads, warnings, CP, stats, starport buff/debuff handling, facility economy, economy influence, and initial population.

Representative named ranges inspected:

- `Set.Tabs = Settings!$B$18:$B$37`
- `Set.Systems = Settings!$C$18:$C$37`
- `Set.SlotsOrb = Settings!$D$18:$D$37`
- `Set.SlotsPlan = Settings!$E$18:$E$37`
- `Set.OCR = Settings!$L$10:$M$60`
- `Stats.Structures = Stats!$A$2:$A$75`
- `Stats.Prereq = Stats!$C$2:$C$75`
- `Stats.T2 = Stats!$F$2:$F$75`
- `Stats.T3 = Stats!$G$2:$G$75`
- `Stats.Stats = Stats!$I$2:$O$75`
- `Stats.Economy = Stats!$N$2:$O$75`
- `Com.Items = Commodities!$P$8:$CK$74`
- `Com.BuildTotals = Commodities!$P$7:$CK$7`
- `List.StructureLayouts = Lists!$A$48:$B$210`

### Mega Guide

Reviewed local file:

- `C:\Users\brian\Downloads\Elite Dangerous Colonization Mega Guide.docx`

The guide was available and inspected directly with `python-docx`.

Relevant sections inspected:

- "Making a Claim & Selecting the Primary Port" around paragraphs 165-178.
- "Introduction To Building Up A System" and CP explanations around paragraphs 269-277.
- "Before You Start: CP-Cost Increases For Tier 2 And Tier 3 Ports" around paragraphs 280-305.
- "How To Effectively Plan For System Construction" around paragraphs 307-345.
- "The Value Of Space Versus Ground Slots" around paragraphs 348-362.
- "How Do Colony-Type Ports Gain Economies?" around paragraphs 524-554.
- "What Are Strong & Weak Links?" around paragraphs 557-619.
- "What To Consider When Selecting A Primary Port?" around paragraphs 695-727.
- "Which Economies Are Compatible With Each Other?" around paragraphs 765-846.
- "How To Haul Effectively And Make Best Use Of Carriers?" around paragraphs 889-916.
- Appendix A advanced strategies around paragraphs 1126-1151.

### Repo Code, Docs, And Tests

Inspected frontend:

- `frontend-v2/src/features/system-detail/SystemDetailModal.tsx`
- `frontend-v2/src/features/system-detail/SimulationPreviewPanel.tsx`
- `frontend-v2/src/features/system-detail/RecommendedBuildsPanel.tsx`
- `frontend-v2/src/features/system-detail/BuildPlanCard.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanSection.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/BuildPlanEditor.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/PreviewResultSection.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/SimulationResult.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/ColonyPlannerHeader.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/ColonyPlannerSectionNav.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/StartModes.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/hooks/useSimulationPreviewPlan.ts`
- `frontend-v2/src/features/system-detail/simulation-preview/hooks/useSimulationPreviewRun.ts`
- `frontend-v2/src/features/system-detail/simulation-preview/hooks/usePlacementEditor.ts`
- `frontend-v2/src/features/system-detail/simulation-preview/optimiser/`
- `frontend-v2/src/features/system-detail/simulation-preview/observations/`
- `frontend-v2/src/features/system-detail/simulation-preview/validation/`
- `frontend-v2/src/features/search-tuning/AdvancedSearchTuningTab.tsx`

`frontend-v2/src/features/system-detail/SystemDetailView.tsx` was requested but is not present.

Inspected backend/docs/tests:

- `apps/api/src/routers/simulate.py`
- `apps/api/src/routers/simulation.py`
- `apps/api/src/routers/optimiser.py`
- `apps/api/src/routers/observations.py`
- `apps/api/src/models.py`
- `apps/api/src/simulation/`
- `apps/api/src/optimiser/`
- `apps/api/src/observations/`
- `apps/api/src/recommendations/`
- `tests/test_simulation_preview.py`
- `tests/test_optimiser.py`
- `tests/test_recommended_builds.py`
- `tests/test_stage6c_comparison.py`
- `tests/test_stage6e_review.py`
- `frontend-v2/src/features/system-detail/simulation-preview/**/*.test.*`
- `docs/api-contracts.md`
- `docs/colonisation-redesign/engine-roadmap.md`
- `docs/colonisation-redesign/stage-8a-colony-planner-ux-backlog.md`

## Current Colony Planner Flow

### 1. User finds a system

Where it appears:

- Finder/search surfaces and Advanced Search Tuning can open system detail.
- Advanced Search Tuning rows include `Open system detail` and `Evaluate in Colony Planner` buttons in `frontend-v2/src/features/search-tuning/AdvancedSearchTuningTab.tsx`.

Action:

- User opens a system detail modal through a search result or tuning row.

Feedback:

- The modal opens system detail. The Search Tuning copy explicitly says the handoff does not run Simulation Preview or generate builds.

Unclear:

- `Evaluate in Colony Planner` currently opens the same system detail modal as `Open system detail`; it does not jump to Colony Planner or focus the planner.

Player-friendly language:

- The Search Tuning handoff language is mostly clear, but "Evaluate in Colony Planner" over-promises because the next screen is still general system detail.

### 2. User opens system detail

Where it appears:

- `SystemDetailModal.tsx`.

Current order:

- Rating profile.
- System info.
- Bodies.
- Stations.
- Estimated exploration value.
- Colony Planning section.
- External links.

Feedback:

- System detail loads with a sticky modal header and standard sections.

Unclear:

- Colony Planning is lower in the detail stack, after dense body/station/exploration content. A user interested in colonisation can miss it.

Player-friendly language:

- General system detail is understandable; Colony Planner-specific language is not surfaced near the top.

### 3. User finds or misses Colony Planner / Simulation Preview

Where it appears:

- The "Colony Planning" section inside `SystemDetailModal.tsx`.

Contained panels:

- `BuildabilityPanel`
- `RegionalPositionPanel`
- `RecommendedBuildsPanel`
- `SimulationPreviewPanel`
- `SlotPredictionPanel`

Feedback:

- Buildability and recommended builds appear before the embedded Colony Planner.

Unclear:

- "Colony Planning" is a section heading, not a prominent entry point. The actual `Colony Planner` header lives inside `SimulationPreviewPanel`, which is below Recommended Builds.
- The flow has both `Recommended Builds` and `Optimiser Candidates`, so users may not know which suggestions are the main path.

Player-friendly language:

- `Recommended Builds` is player-friendly.
- `Optimiser Candidates` is more technical and should not be the main label for new users.

### 4. User creates or loads a Build Plan

Where it appears:

- `SimulationPreview.tsx` renders `BuildPlanSection`.
- `BuildPlanSection.tsx` renders `StartModes` and `BuildPlanEditor`.
- `useSimulationPreviewPlan.ts` auto-loads recommended placements when buildability data is available and no blank plan was started.

Action:

- User can use recommended build, edit recommended build, start blank advanced simulation, load an optimiser candidate, or manually add facilities.

Feedback:

- `StartModes.tsx` shows three mode cards.
- `ModeIntro` explains the selected mode.
- Optimiser-candidate origin copy is shown after loading a candidate.
- Initial assumptions are shown if passed from a selected recommended build.

Unclear:

- The first-run choice is inside the larger embedded panel rather than framed as the main workflow decision.
- Recommended plan auto-loading is useful but implicit; users may not understand what was loaded or why.
- Blank advanced simulation has equal visual weight with safer suggested paths.

Player-friendly language:

- "Use recommended build" and "Build Plan" are good labels.
- "Start blank advanced simulation" is accurate, but should stay visually secondary.

### 5. User adds economy/building/placements

Where it appears:

- `BuildPlanEditor.tsx`.

Action:

- User changes facility template, body assignment, primary port flag, order, or removes a row.
- User changes target archetype in `BuildPlanSection.tsx`.

Feedback:

- Rows update in place.
- Chips show tier, economy, allowed location, and yellow/green CP generation.
- If a recommended plan is edited, start mode changes to `edit_recommended`.
- If an optimiser candidate was edited, origin copy changes to say the plan has been edited.

Unclear:

- There is no obvious transient feedback such as "Build Plan updated".
- There is no placement count.
- There is no persistent "Preview not run yet" / "Preview stale" status near the editor.
- Field-level help is limited; users may not know why archetype, primary port, body, or order matter.

Player-friendly language:

- The CP chip uses compact `Y+` / `G+`, which assumes the user already understands yellow/green CP.

### 6. User runs Preview

Where it appears:

- `ColonyPlannerHeader.tsx` has the `Run Preview` button.

Action:

- User clicks `Run Preview`.

Feedback:

- Button changes to `Running`.
- `useSimulationPreviewRun.ts` calls `simulateBuild`.
- Preview result is cleared when the plan is replaced and marked stale when the fingerprint differs after edits.

Unclear:

- The action is visible in the header, but after editing rows the CTA is not specially highlighted.
- If the plan has zero placements, the disabled state does not provide a focused checklist of what to do.

Player-friendly language:

- `Run Preview` is good. The surrounding language still says "Simulation Preview" more than "what happens if I build this?"

### 7. User sees Preview Result

Where it appears:

- `PreviewResultSection.tsx` renders `SimulationResult.tsx`.

Feedback:

- Before preview: ghost metrics for Score, Build, and Confidence.
- After preview: final score, build complexity, confidence, composition score, buildability score, data confidence, observed-vs-predicted summary, economy bars/stack, port economies, topology, CP, CP repair, services, strengths, warnings, recommendations, links, and mechanics trace.
- If stale: a warning says to run Preview again.

Unclear:

- The result is rich, but it is not framed as a verdict or guided next step.
- Users see many advanced panels at once without an opening interpretation.
- `recommendations` appears later and is not positioned as the answer to "what should I do next?"

Player-friendly language:

- Some panel titles are friendly (`Why this works`, `Warnings`, `Next steps`).
- Some titles are mechanics-first (`Port Economy`, `Inherited Economy`, `Mechanics Trace`).

### 8. User may generate optimiser candidates

Where it appears:

- `OptimiserCandidatePanel.tsx`, rendered after Build Plan and before Preview Result.

Action:

- User selects max candidates, estimated-data option, and clicks `Generate candidates`.

Feedback:

- Generated parameters are shown.
- Controls-changed warning appears when target/max/estimated settings differ from generation.
- Candidate cards show rank, tier, score, preview summary, warnings, CP risk, and rationale.

Unclear:

- "Optimiser Candidates" is technical. For users, this is probably "Suggested Builds".
- The panel sits after an already-present recommended-build section, causing duplicate suggestion concepts.
- The button says candidate generation does not run the main Simulation Preview, but it still uses lightweight preview summaries internally. This is accurate but cognitively heavy.

Player-friendly language:

- Candidate cards are useful, but "candidate", "optimiser", and "rank" are less natural than "suggested build", "why suggested", and "risk".

### 9. User may load/tweak a candidate

Where it appears:

- `OptimiserCandidateDetails.tsx`.

Action:

- User clicks `Load into preview`.
- If the current plan is non-empty or candidates are stale, user confirms replacement.

Feedback:

- Copy explains it copies the candidate into editable Simulation Preview and does not commit in-game.
- Replacement and stale-candidate confirmations are present.
- The Build Plan origin marker appears after load.

Unclear:

- "Load into preview" does not clearly say "copy this into your editable Build Plan".
- After loading, the next step should be louder: tweak if needed, then Run Preview.

Player-friendly language:

- Safety copy is strong. The action label should be more user-task-oriented.

### 10. User may record Observed Evidence

Where it appears:

- `ObservedEvidencePanel.tsx`, after Preview Result.

Action:

- User records, filters, edits, or deletes manually observed facts.

Feedback:

- Passive-evidence copy is clear: it does not change scoring, optimiser ranking, or generated candidates.
- Summary counts, filters, CRUD states, and error states are present.

Unclear:

- This is advanced for a first-run user. It appears before the user has necessarily understood the Preview Result.

Player-friendly language:

- "Observed Evidence" is good. The form remains mechanics-heavy by necessity.

### 11. User may view Validation / Review Guidance

Where it appears:

- `ValidationPanel.tsx`, after Observed Evidence.
- `ValidationReviewPanel.tsx`, inside Validation when review data exists.

Action:

- User views comparison and clicks Refresh validation when needed.

Feedback:

- No-preview copy instructs user to run Preview.
- Stale-preview warning tells user to run Preview again.
- Validation and review are passive and do not auto-run preview.

Unclear:

- Validation is conceptually downstream of "I checked something in-game"; first-run users may interpret it as a required planning step.

Player-friendly language:

- Conservative labels are good, but "Validation" and "Review Guidance" should be positioned as later steps in Stage 8A.

## Source-Material UX Lessons

### Spreadsheet-derived lessons

- Planning is row-based. DaftMav's `Colony` tabs model a build as facility rows with active/done flags, body/slot context, primary row, prerequisites, layout variant, CP, stats, economy, and population. ED-Finder already has row-based placements in `BuildPlanEditor.tsx`, but needs more feedback around row count, primary-port risk, and stale preview status.
- Planning starts with system context. `Settings` captures colony tab names, system names, slot counts, cargo capacity, source-search filters, and OCR input. ED-Finder already has system detail and body data, but the planner does not open with a visible "planning context" summary.
- Slots matter separately. The workbook tracks orbital and planetary slots as separate values. ED-Finder has topology/slot prediction panels, but Stage 8A should bring orbital vs planetary capacity into the first-run planner summary rather than leaving it lower or separate.
- CP is a build-order problem. `Stats.T2`, `Stats.T3`, `List.TaxNames`, and `List.Tax` feed formulas that alter CP costs as rows accumulate. ED-Finder already has CP timeline/repair output, but the editor needs plain-language hints about why order matters before the user runs into warnings.
- Prerequisites are visible per row. `Stats.Prereq` and formula-derived `Prerequisites` columns appear on Colony rows. ED-Finder already models services/buildability, but the Build Plan editor does not show prerequisite/dependency status per placement.
- Economy is not one field. `Stats.Economy`, `Stats.Stats`, `List.Influence`, and `List.Type` show economy and influence as derived planning dimensions. ED-Finder has economy stack/port economy panels, but the first-run flow should explain top-two economy focus and contamination risk.
- Hauling is a first-class workflow. `Cargo Hauling` turns active builds into commodity totals, then lets users track carrier stock, ship stock, delivered cargo, and still-needed amounts. ED-Finder does not currently surface build material totals or trip estimates in the Colony Planner UI. Stage 8A should note this as deferred unless existing response data already supports it.
- Suggested variants are normal. `Lists` includes structure-layout variants and warnings. ED-Finder already has recommended builds and optimiser candidates, but it should present suggestions as the primary route rather than an optional technical panel.

### Mega Guide-derived lessons

- Primary port is an irreversible decision once built. The guide repeats this in the claim and build-up sections. Stage 8A should make primary-port selection a warning-rich step, not just a checkbox.
- Yellow/green CP language needs translation. The guide uses yellow CP for Tier 2 construction points and green CP for Tier 3 construction points because in-game terminology is confusing. ED-Finder should explain `Y` and `G` near chips and CP summaries.
- T2/T3 port order matters. The guide recommends building intended T3 ports before T2 ports for large systems because T3 escalation is harsher. ED-Finder already has CP timeline and repair suggestions; Stage 8A should surface "order matters" before Preview.
- Primary port does not count toward the T2/T3 escalation. The UI should explain why a T3 primary can be powerful for capital systems, while an outpost may be safer for bridges or solo players.
- Market design should focus on one or two primary economies. The guide's top-two economy protection and contamination discussion imply a UX need for "primary market focus" and "extra economy risk" labels.
- Orbital and planetary choices are tradeoffs. Orbital ports are convenient and enable some goods/links; planetary sites enable other goods, hubs, T3 planetary stats, and compact multi-site work. ED-Finder should explain what a body/placement choice changes.
- Users need tools because the system is hard to reason about manually. The guide explicitly points players toward Raven Colonial and DaftMav's spreadsheet for simulation, dependencies, and CP requirements. ED-Finder should own that role with a guided workflow.
- Hauling effort changes the right answer. The guide's primary-port advice considers cutter-load counts, four-week primary build window, carrier use, and travel distance. ED-Finder currently surfaces build complexity but not enough material/trip effort in the main flow.

These source lessons should be treated as UX/product inputs, not unreviewed game-truth. Where the guide marks mechanics as uncertain or potentially bugged, ED-Finder copy should use cautious terms such as "risk", "likely", "estimated", or "needs in-game verification".

## User-Raised UX Issues

The user-raised concerns are valid after repo inspection, with nuance:

- Colony Planner is buried inside system detail.
- Search Tuning has an `Evaluate in Colony Planner` action, but it opens generic system detail and does not jump to or focus Colony Planner.
- Simulation Preview is clearer than earlier stages, but the first-run purpose is still spread across header copy, Build Plan copy, Preview Result copy, and downstream panels.
- Adding facilities does update rows, but there is no explicit feedback/status that the Build Plan changed and needs preview.
- Running Preview produces many panels, but not a headline verdict or a clear "what changed / what next" interpretation.
- Suggested builds are present, but there are two suggestion concepts: `Recommended Builds` above the planner and `Optimiser Candidates` inside the planner.
- Blank planning is available and visually peer-level with recommended options.
- Observed Evidence and Validation are correctly passive, but they can feel advanced if shown before the user has a basic preview workflow.

## Problem Findings

| Severity | Issue | Evidence | Affected files/components | Recommended Stage 8A fix | Backend needed? |
|---|---|---|---|---|---|
| High | Colony Planner is too buried in system detail. | `SystemDetailModal.tsx` renders Colony Planning after Rating profile, System info, Bodies, Stations, and Exploration value. User concern matches current layout. | `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` | Add prominent top-of-modal CTA/jump link: `Open Colony Planner`. Keep embedded section for Stage 8A; jump/focus it from the CTA. | No |
| High | `Evaluate in Colony Planner` does not actually land in the planner. | `AdvancedSearchTuningTab.tsx` calls `onOpenDetail(r.id64)` for both `Open system detail` and `Evaluate in Colony Planner`. Docs say it only opens system detail. | `frontend-v2/src/features/search-tuning/AdvancedSearchTuningTab.tsx`, `frontend-v2/src/App.tsx`, `SystemDetailModal.tsx` | Preserve no-auto-run semantics, but pass intent/focus so system detail opens scrolled to Colony Planner or with planner highlighted. | No |
| High | Suggested-build path is split between Recommended Builds and Optimiser Candidates. | `RecommendedBuildsPanel.tsx` exists before `SimulationPreviewPanel`; `OptimiserCandidatePanel.tsx` exists inside the planner with technical label. | `RecommendedBuildsPanel.tsx`, `SimulationPreview.tsx`, `OptimiserCandidatePanel.tsx`, `ColonyPlannerSectionNav.tsx` | Reframe user-facing candidate UI as `Suggested Builds`; make initial planner choice "Generate Suggested Builds" / "Use recommended plan" / "Start blank". Keep backend optimiser names. | No |
| High | Preview Result lacks a headline interpretation. | `SimulationResult.tsx` renders many panels but starts with metrics rather than a verdict and next-step summary. | `PreviewResultSection.tsx`, `SimulationResult.tsx`, panels under `simulation-preview/panels/` | Add top summary block: verdict, risk level, why, and next recommended action. Reuse existing result fields: score, buildability, confidence, strengths, warnings, recommendations, CP summary. | No |
| High | Build Plan edits do not loudly indicate "needs preview". | `usePlacementEditor.ts` mutates placements; `useSimulationPreviewRun.ts` can mark stale result, but the editor itself does not show placement count/update/stale state. | `BuildPlanSection.tsx`, `BuildPlanEditor.tsx`, `usePlacementEditor.ts`, `useSimulationPreviewRun.ts` | Add visible status near Build Plan: placement count, "Preview not run yet", "Build Plan updated", and "Preview is stale - run again". | No |
| High | Primary port risk is under-translated. | Build rows have a `Primary port` checkbox; guide says the primary port is irreversible and selection should consider intent, body, distance, slots, solo/community scale, and hauling effort. | `BuildPlanEditor.tsx`, `StartModes.tsx`, `SimulationResult.tsx`, `CpSummary.tsx` | Add primary-port hint and warning copy around the first/primary placement. Recommended builds should explain why their primary port is safe or risky. | Mostly no; deeper effort estimates may need later backend data |
| Medium | CP/yellow/green language assumes prior knowledge. | `BuildPlanEditor.tsx` chip says `Y+... G+...`; `CpSummary`/timeline are available after preview. Guide emphasizes yellow/green terminology because in-game tiers are confusing. | `BuildPlanEditor.tsx`, `CpSummary.tsx`, `CpTimelinePanel.tsx`, `StartModes.tsx` | Add compact help text/tooltips: yellow CP builds T2, green CP builds T3; order can change port costs. | No |
| Medium | Build order is not explained before it matters. | Reordering controls exist, CP timeline appears after preview. Guide stresses T3-before-T2 in large systems and CP escalation on laid-down ports. | `BuildPlanEditor.tsx`, `CpTimelinePanel.tsx`, `CpRepairPanel.tsx` | Add pre-preview copy near order controls and post-preview next-step warnings when CP or order is risky. | No |
| Medium | Hauling/build effort is not surfaced enough. | Spreadsheet `Cargo Hauling` makes hauling a major workflow; guide primary-port section uses hauling loads as a deciding factor. Current preview shows build complexity but not material totals/trips in the main planner. | `BuildPlanCard.tsx`, `SimulationResult.tsx`, backend response if material totals are absent | Stage 8A should add copy placeholders/deferrals: "Build effort estimate not yet material-aware." Later stage can add material/trip calculations. | Maybe later; no for Stage 8A if copy-only |
| Medium | Economy contamination is advanced and buried. | Current panels show economy bars/stacks/port economies. Guide says top two economies are protected and economy 3+ can contaminate markets. | `EconomyBars.tsx`, `EconomyStackPanel.tsx`, `PortEconomyPanel.tsx`, `BuildPlanCard.tsx` | Add player-facing labels: "Primary market focus", "extra economy risk", "likely contamination source". | No if derived from existing order/warnings |
| Medium | Observed Evidence and Validation may appear too early conceptually. | `SimulationPreview.tsx` always renders Observed Evidence and Validation after Preview Result. They are correct and passive, but advanced. | `SimulationPreview.tsx`, `ObservedEvidencePanel.tsx`, `ValidationPanel.tsx`, `ColonyPlannerSectionNav.tsx` | Position as later-step sections: collapsed or visually subordinate until a preview exists, with copy "after in-game check". | No |
| Medium | Start blank has equal visual weight. | `StartModes.tsx` uses a three-column grid where blank advanced is one of three peers. | `StartModes.tsx`, `BuildPlanSection.tsx` | Make suggested-build options primary; make blank advanced secondary/collapsed. Keep manual path. | No |
| Medium | "Optimiser Candidates" is too technical for primary user journey. | Panel title, aria labels, generated copy, and section nav use Optimiser terminology. | `OptimiserCandidatePanel.tsx`, `OptimiserCandidateCard.tsx`, `OptimiserCandidateDetails.tsx`, `ColonyPlannerSectionNav.tsx`, tests | User-facing rename to `Suggested Builds`; keep function/type/API names. | No |
| Low | API docs are accurate but Stage 8A should note new terminology split. | `docs/api-contracts.md` already distinguishes Search Tuning, Colony Planner optimiser, Simulation Preview, Observed Evidence, and Validation. | `docs/api-contracts.md` | No large API rewrite. Later Stage 8A implementation should add a short note that UI says Suggested Builds while API remains optimiser candidates. | No |

## Recommended Stage 8A Direction

Stage 8A should implement a guided Colony Planner workflow without changing mechanics:

1. User opens Colony Planner from a prominent CTA.
2. User sees "How do you want to start?"
3. Primary path: `Generate Suggested Builds`.
4. Secondary path: `Use recommended plan` when ED-Finder already has one.
5. Advanced path: `Start blank`.
6. Suggested-build cards show rationale, warnings, assumptions, expected preview summary, CP risk, primary-port rationale, and economy focus.
7. User loads one into the Build Plan deliberately.
8. Build Plan shows what changed and highlights `Run Preview`.
9. Preview Result explains what happened and what to do next.
10. Observed Evidence, Validation, and Review Guidance are presented as later steps after the user checks the prediction in-game.

Proposed user-facing labels:

- `Colony Planner`
- `Suggested Builds`
- `Build Plan`
- `Preview Result`
- `Observed Evidence`
- `Validation`
- `Review Guidance`
- `Open Colony Planner`
- `Evaluate in Colony Planner`

Terminology guidance:

- Use `Suggested Builds` in user-facing flow.
- Keep backend/API/internal names such as optimiser/candidate/ranking unless a later code-rename stage is explicitly scoped.
- Use `Build Plan` for the editable list that the user can run through Preview.
- Use `Preview Result` for a completed explicit run.

## Entry Point / Layout Recommendation

### Option A - Keep embedded in system detail but add prominent jump link/CTA near top

Pros:

- Lowest risk.
- Preserves current modal and section architecture.
- No routing change.
- No backend change.
- Addresses the "buried" complaint quickly.
- Works with existing Search Tuning handoff.

Cons:

- Colony Planner remains inside a dense system-detail surface.
- Deep planner work still competes with bodies/stations/exploration content.

Complexity:

- Low to medium.

Risk:

- Low.

Stage 8A recommendation:

- Primary approach for Stage 8A. Add top CTA and scroll/focus behavior. Add a planner anchor and highlight state when opened from "Evaluate in Colony Planner".

### Option B - Open Colony Planner in a large drawer/panel from system detail

Pros:

- Makes the planner feel like a focused workspace.
- Keeps system detail context nearby.
- Avoids a full route migration.

Cons:

- Requires more state choreography.
- Potential layout complexity inside an already modal-heavy UI.
- Could become a redesign rather than a prep-following implementation.

Complexity:

- Medium.

Risk:

- Medium.

Stage 8A recommendation:

- Good fallback after Option A if embedded section still feels buried. Do not start here unless Stage 8A explicitly allows UI restructuring.

### Option C - Dedicated route/workspace, such as `#colony-planner/system/{id64}`

Pros:

- Best long-term platform shape.
- Clear shareable deep link.
- Makes Colony Planner a headline feature.

Cons:

- Highest frontend routing and state complexity.
- Requires decisions about system loading, back navigation, modal coexistence, and existing `SystemDetailModal` reuse.
- More likely to become a redesign stage.

Complexity:

- High.

Risk:

- Medium to high.

Stage 8A recommendation:

- Defer. This is plausible for a later full Colony Planning Platform stage.

### Option D - Search result card direct action: `Evaluate in Colony Planner`

Pros:

- Strong discoverability from the point where users choose systems.
- Stage 7D already introduced this in Advanced Search Tuning.

Cons:

- If it only opens generic system detail, it can feel misleading.
- Needs consistent behavior across normal search results and Search Tuning.

Complexity:

- Low to medium if wired to Option A focus behavior.

Risk:

- Low.

Stage 8A recommendation:

- Pair with Option A. Search-result direct actions should open system detail with Colony Planner focused, not merely open the modal at the top.

Recommended primary approach:

- Option A plus Option D handoff focus.

Safe fallback:

- Option A only: top CTA inside `SystemDetailModal.tsx` that scrolls to existing Colony Planning.

## Suggested Builds First-Run Flow

Ideal Stage 8A first-run flow:

1. User clicks `Open Colony Planner` near the top of system detail, or `Evaluate in Colony Planner` from a result row.
2. System detail scrolls/focuses the existing Colony Planner area.
3. Planner opens with "How do you want to start?"
4. Primary card: `Generate Suggested Builds`.
   - Explains this creates candidate plans for the current target.
   - Does not auto-load anything.
   - Does not commit in-game.
5. Secondary card: `Use recommended plan`.
   - Available when existing recommended build data exists.
   - Explains this is the safe starter plan ED-Finder already selected.
6. Advanced card/link: `Start blank`.
   - Lower visual weight.
   - Copy: "For commanders who already know the facility sequence they want to test."
7. Suggested-build cards show:
   - Plain label.
   - Intended role/archetype.
   - Why suggested.
   - Primary port assumption and risk.
   - Expected economy focus.
   - CP/buildability snapshot.
   - Main warning.
   - Confidence/estimated-data note.
   - `Copy into Build Plan` button.
8. Loading a suggestion:
   - Requires confirmation if replacing non-empty plan.
   - Shows "Copied into Build Plan. Review or tweak, then Run Preview."
9. Build Plan:
   - Shows placement count.
   - Shows primary port row and warning/help.
   - Shows CP chip help.
   - Shows "Preview not run yet" or "Preview stale".
10. Preview Result:
   - Starts with a verdict and next step.
   - Then exposes deeper mechanics panels.
11. Observed Evidence and Validation:
   - Appear as "After in-game check" or later-step sections.

## Preview Result UX Plan

Preview Result should answer four questions:

- What happened?
- Is this good or risky?
- Why?
- What should I do next?

Proposed sections:

- Headline verdict.
- Score cards.
- Predicted economy mix.
- Predicted services.
- CP summary.
- Buildability summary.
- Strengths.
- Warnings.
- Recommendations.
- Assumptions.
- Mechanics notes.
- Suggested next steps.

Suggested next-step logic using existing state:

- No preview result: "Run Preview to see the predicted economy, CP, services, and risks for this Build Plan."
- Preview stale: "Run Preview again; this result no longer matches the edited Build Plan."
- Weak buildability or CP warnings: "Adjust the plan or generate suggested builds."
- Low confidence: "Treat this as a rough estimate; record observed evidence after checking in-game."
- Viable result: "Compare suggested builds, tweak the plan, or record observed evidence after an in-game check."
- Evidence exists or validation has data: "Refresh validation/review after recording evidence."

No scoring changes are required. The UI can use existing fields:

- `final_score`
- `build_complexity`
- `confidence`
- `composition_score`
- `buildability_score`
- `strengths`
- `warnings`
- `recommendations`
- `cp`
- `cp_timeline`
- `cp_repair_suggestions`
- `economy_order`
- `economy_composition`
- `services`
- `port_service_states`
- `observation_summary`

## Suggested Builds UX Plan

Audit result:

- `RecommendedBuildsPanel.tsx` already provides a recommended-build path above the planner.
- `OptimiserCandidatePanel.tsx` already generates bounded candidates, ranks them, compares them to the editable Build Plan, and supports deliberate load into preview.
- Current UI has two suggestion surfaces and one uses technical naming.

Stage 8A plan:

- Use `Suggested Builds` as the user-facing name for optimiser candidate generation.
- Keep `Recommended Builds` only if it clearly means precomputed/default recommendations; otherwise fold the experience into a unified "Suggested Builds" entry inside Colony Planner.
- Place Suggested Builds above manual Build Plan for first-time users.
- Do not auto-generate candidates on page load unless performance and API cost are confirmed safe in a later implementation review.
- Do not auto-load a suggestion.
- Keep confirmation before replacing a non-empty Build Plan.
- Explain ranking as "why ED-Finder suggests this", not as an opaque optimiser score.
- Show each card's:
  - Purpose.
  - Primary port choice.
  - Body/slot assumptions.
  - Economy focus.
  - CP risk.
  - Build complexity.
  - Main warning.
  - Confidence and estimated-data status.
  - "Copy into Build Plan" action.
- After copy/load, show a status message and highlight `Run Preview`.

Backend scope:

- No Stage 8A backend generation or ranking expansion.
- If future UI needs material totals/trip estimates not present in responses, defer that as a later backend stage.

## Build Plan Feedback Plan

Expected feedback when the user edits:

| User action | Current behavior | Stage 8A feedback recommendation | Suggested tests |
|---|---|---|---|
| Adds a facility | Row appears in `BuildPlanEditor`. | Show placement count increment, "Build Plan updated", and "Preview not run yet" or "Preview stale". Highlight `Run Preview`. | Add placement updates count/status and enables Run Preview. |
| Changes target economy/archetype | Select value changes; candidates may become stale separately. | Explain that target affects suggested builds/ranking/preview scoring, not in-game state. Mark existing preview stale. | Changing archetype marks preview stale after a prior run. |
| Changes port/facility type | Row select changes; chips update. | Show what the field affects: CP, economy, service unlocks, primary-port eligibility, allowed location. | Facility change updates chips and status copy. |
| Changes primary port | Checkbox updates and clears other primary flags. | Show irreversible-choice warning and primary-port help. | Primary-port checkbox renders warning/help and only one row remains primary. |
| Loads a suggested build | Placements replace current plan after confirmation if needed. | Show "Copied into Build Plan", placement count, source label, and "Run Preview next". | Loading suggestion shows origin/status and clears previous preview. |
| Edits a loaded suggestion | Existing origin marker says edited. | Keep marker, add "This no longer exactly matches the suggestion". | Editing loaded suggestion changes origin status. |
| Removes a placement | Row disappears and resequences. | Show placement count decrement and preview stale/not-run state. | Removing row resequences and marks status. |

Do not implement these tests in this prep pass; add them when Stage 8A UI changes are made.

## Proposed Tests for Stage 8A

Frontend tests:

- `SystemDetailModal` renders `Open Colony Planner` near the top when system data loads.
- Clicking `Open Colony Planner` focuses or scrolls to the Colony Planner section without running preview or generating builds.
- Search Tuning `Evaluate in Colony Planner` opens system detail with planner focus intent and still does not run preview or generate builds.
- First-run planner shows Suggested Builds as the primary path and blank as advanced/secondary.
- User-facing `Suggested Builds` label replaces `Optimiser Candidates` in visible planner copy while API helpers remain unchanged.
- Empty Build Plan shows "Preview not run yet" and disabled/available next-step guidance.
- Editing a placement after preview marks the result stale and highlights Run Preview.
- Loading a suggested build into a non-empty plan requires confirmation.
- Preview Result renders a headline verdict and next-step block from existing result fields.
- Observed Evidence and Validation remain passive and do not call `simulateBuild` or `fetchOptimiserCandidates` except through their existing explicit flows.

Backend tests:

- None required for Stage 8A if implementation remains frontend-only.

Docs/API tests:

- Keep `git diff --check`.
- Existing frontend test suites should run only if implementation changes touch frontend code.

## Strict Non-Goals for Stage 8A

- Do not redesign the full Colony Planner mechanics.
- Do not change Simulation Preview scoring.
- Do not change optimiser candidate generation.
- Do not change optimiser ranking.
- Do not change validation/review mechanics.
- Do not change backend mechanics.
- Do not add endpoints.
- Do not add EDMC/journal ingestion.
- Do not add saved builds.
- Do not add account/profile persistence.
- Do not add automatic learning.
- Do not alter Search Tuning.
- Do not remove manual planning.
- Do not auto-run preview.
- Do not auto-load suggested builds.

## Deferred Work

- Dedicated Colony Planner route/workspace.
- Material totals, hauling trip estimates, carrier workflow, and commodity source integration.
- Saved builds and build comparison history.
- EDMC/journal ingestion.
- Automatic learning from observations.
- Service-aware recommendation scoring beyond current rules.
- Full route-level redesign of system detail.
- Candidate-vs-candidate comparison selector UI.
- Rich visual graph rendering for economy/link topology.

## Final Recommendation

Stage 8A should be a focused frontend UX implementation based on this audit:

- Keep the existing embedded planner for now.
- Add prominent planner entry/focus.
- Reframe the first-run path around Suggested Builds.
- Preserve blank/manual planning as advanced.
- Turn Preview Result into a clear interpreted outcome.
- Add edit feedback and stale-preview guidance.
- Position Observed Evidence, Validation, and Review Guidance as later advisory steps.

This direction aligns ED-Finder with how players actually plan colonisation: choose a system intent, avoid irreversible primary-port mistakes, manage CP/order/slot constraints, protect economy focus, estimate effort, preview the result, and only then validate against in-game evidence.
