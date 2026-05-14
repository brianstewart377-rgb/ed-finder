# Stage 5.9B Forensic Structural, UX, and Wiring Review

## 1. Executive Summary

This review finds that ED-Finder’s post-Stage-5 implementation is **functionally coherent and technically safer than it looks at first glance**, but the product surface is now ahead of the navigation and workspace structure. The top-level app now distinguishes **Finder** and **Search Tuning** clearly: Finder searches systems, while Search Tuning reranks the current Finder result set. The Stage 5 colony optimiser/planner is also technically distinct from Search Tuning, but it is currently **buried too far down** inside the System Detail modal, inside the Colony Planning section, inside Simulation Preview, and finally below the manual preview editor/result grid.

The backend Stage 5 structure is comparatively strong. The package `apps/api/src/optimiser/` contains separated generation, ranking, model, rule, dedupe, facility-selection, and preview-summary code. The FastAPI router `apps/api/src/routers/optimiser.py` is small and explicit: it normalises the target archetype, calls candidate generation, optionally attaches ranking, and validates the public response. This is a good foundation and should not be rewritten before Stage 6.

The frontend structure is also better than a monolith, because Simulation Preview has already been decomposed under `frontend-v2/src/features/system-detail/simulation-preview/`. However, the orchestration component `SimulationPreview.tsx` now owns manual preview state, candidate-origin state, candidate loading, run-preview state, error state, target-archetype state, recommended-build loading, and the embedded optimiser panel. This is manageable now, but it is the next structural pressure point.

> **Headline verdict:** ED-Finder is ready for a Stage 5.9 cleanup pass before Stage 6. It should not start observed-vs-predicted validation work until the planner surface is renamed, moved into a clearer workspace, and covered by one or two stronger end-to-end wiring tests.

## 2. Overall Verdict

The application now has two distinct concepts that are no longer both called “Optimizer”, which solves the immediate naming collision. Search Tuning is now clear enough to keep temporarily as a top-level route, but it should eventually move under Finder as an advanced reranking tool. The Stage 5 colony optimiser/planner should become a first-class workspace inside System Detail, preferably named **Colony Planner**, with Simulation Preview as one internal mode rather than the container for all planning activity.

| Primary Question | Direct Answer |
|---|---|
| Does the app distinguish Finder, Search Tuning, System Detail, Simulation Preview, and the colony optimiser/planner? | **Partly.** Top-level Finder and Search Tuning are now distinct. System Detail and Simulation Preview are distinct in code. The colony optimiser is still visually nested under Simulation Preview, so the product distinction is not strong enough. |
| Is Stage 5 buried too far down? | **Yes.** The route is Finder/Search Tuning/etc.; Stage 5 is only reached after opening a system, scrolling into Colony Planning, opening/using Simulation Preview, and then reaching the optimiser section at the bottom. |
| Should Stage 5 get its own dedicated internal space? | **Yes.** It should become a System Detail-level or Colony Planner-level internal space, not a bottom section inside Simulation Preview. |
| What should the user-facing term be? | **Colony Planner** for the broad workspace; **Optimiser Candidates** for the candidate-generation sub-panel; **Simulation Preview** for the explicit preview run/result sub-mode. |
| Does the current Stage 5 UI explain generate/rank/compare/load semantics? | **Mostly.** The safety copy is good, especially “nothing is committed in-game” and comparison is advisory. The target-archetype and estimated-data controls still need stronger context. |
| Are there stale optimizer references? | **Internally, yes, intentionally.** `frontend-v2/src/features/optimizer/` and route `optimizer` remain as low-risk compatibility names for Search Tuning. User-facing stale top-level “Optimizer” wording appears addressed. |
| Does `SimulationPreview.tsx` own too much orchestration/state? | **Yes, next-stage concern.** It is not broken, but it is now the main frontend refactor candidate. |
| Are tests sufficient? | **Good but not complete.** Backend optimiser and frontend panel tests are strong. Missing coverage remains around full generate → compare → load → edit → run, navigation labels, and target-archetype changes. |
| Should Search Tuning stay? | **Yes, for now.** Keep it, but later demote it under Finder/Advanced Search Tuning and improve explanations/presets/rank movement. |
| What should happen before Stage 6? | Stage 5.9C layout/naming cleanup, Stage 5.9D planner workspace refactor, and Stage 5.9E wiring test hardening. |

## 3. Structural Findings

| Severity | Evidence | Issue | Recommendation | Timing |
|---|---|---|---|---|
| Medium | `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` renders one broad `Section title="Colony Planning"` containing Buildability, Regional, Recommended Builds, Simulation Preview, and Slot Prediction. | The System Detail modal has no internal planner navigation. Colony planning is a vertical stack, so the Stage 5 workflow is hard to discover. | Add internal System Detail/Colony Planning modes or tabs, with **Colony Planner** as the broad workspace. | Next stage |
| High | `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx` owns target archetype, placements, result, errors, recommended loading, candidate-origin state, candidate edit tracking, run-preview behavior, and embeds `OptimiserCandidatePanel`. | The file is not yet unmaintainable, but it is now the highest-risk frontend state owner. Future Stage 6 validation or saved builds will increase complexity sharply. | Extract planner state and optimiser-candidate orchestration into hooks such as `useSimulationPreviewPlan` and `useOptimiserCandidateLoading`, or move the optimiser into a sibling workspace. | Next stage |
| Low | `apps/api/src/optimiser/` contains `candidate_generator.py`, `ranker.py`, `models.py`, `archetype_rules.py`, `facility_selection.py`, `dedupe.py`, and `preview_summary.py`. | Backend Stage 5 ownership is clean and does not need urgent structural change. | Keep backend package. Do not rename `apps/api/src/optimiser/` until there is a strong reason, because it is internally coherent and British spelling matches Stage 5 docs. | Do not fix now |
| Medium | `frontend-v2/src/features/optimizer/OptimizerTab.tsx`, `useOptimizer.ts`, and route key `optimizer` now present as Search Tuning. | User-facing wording is fixed, but internal names remain “optimizer”. This is acceptable short-term, but it will confuse new contributors if left forever. | Later rename the folder to `search-tuning/` and keep a route alias if routing cleanup exists. Do this as a small migration, not during Stage 6. | Later |
| Medium | `frontend-v2/src/lib/api.ts` contains both `/optimiser/candidates` and `/ratings/rerank` wrappers. | The API client correctly separates backend paths, but colocating both in one broad API file makes naming drift easy. | Add section comments that say “Colony planner optimiser” versus “Search Tuning rerank”, or later split API helpers by feature. | Next stage |
| Low | `frontend-v2/src/features/system-detail/simulation-preview/optimiser/comparison/` is a separate comparison subfolder. | Comparison logic is well isolated from rendering and does not need a rewrite. | Keep this folder, but consider moving it under a future `colony-planner/` workspace if the optimiser becomes first-class. | Later |
| Low | `docs/colonisation-redesign/optimiser-candidate-generator.md` starts with Stage 5A/5B scope caveats and later includes Stage 5C–5F. | The document is accurate in sections, but the first paragraph can read stale because it says Stage 5A/B are not comparison UI/apply flow before later describing Stage 5D–5F. | Add a current-status paragraph at the top explaining that Stage 5A–5F now exist, while the early section describes the original foundation. | Fix now or next stage |

## 4. Stage 5 Wiring Findings

The backend flow is clear and bounded. `OptimiserCandidatesRequest` reaches `apps/api/src/routers/optimiser.py`, where `target_archetype` is normalised from either `target_archetype` or `target_archetype_key`, catalogue data is loaded, and `generate_candidates(...)` is called. If `include_ranking` is true, `rank_candidates(...)` runs over the generated candidates and is attached as a top-level `ranking` object before Pydantic response validation.

The candidate generator then resolves an archetype rule, loads preview context/body rows, selects body anchors, generates bounded candidates by strategy, deduplicates ordered placement fingerprints, optionally runs Simulation Preview to attach lightweight preview summaries, and captures preview failures as candidate warnings rather than aborting the full response. This is a robust flow for a v1 optimiser foundation.

| Flow Step | Evidence | Assessment |
|---|---|---|
| Request model | `models.py` public `OptimiserCandidatesRequest`; internal `apps/api/src/optimiser/models.py` `CandidateGenerationRequest`. | Clear enough. Compatibility with `target_archetype_key` is preserved. |
| Candidate generation | `apps/api/src/optimiser/candidate_generator.py`. | Bounded, deterministic, deduped, and non-exhaustive by design. Good. |
| Preview summary | `candidate_generator.py` `_attach_preview_summary`; `apps/api/src/optimiser/preview_summary.py`. | Preview failures are isolated. Full preview payloads are not embedded. Good. |
| Ranking | `apps/api/src/optimiser/ranker.py`; `apps/api/src/optimiser/models.py` ranking dataclasses. | Ranking is non-mutating and top-level by `candidate_id`. Good. |
| Endpoint serialization | `apps/api/src/routers/optimiser.py`. | Small and explicit. Good. |
| Frontend request | `OptimiserCandidatePanel.tsx` sends `run_preview: true` and `include_ranking: true`. | Correct for Stage 5C–5F UI. |
| Candidate render | `OptimiserCandidatePanel.tsx`, `OptimiserCandidateCard.tsx`, `OptimiserCandidateDetails.tsx`. | Works, but the panel sits too low in the page. |
| Comparison | `OptimiserCandidateDetails.tsx` uses `compareBuildSources(...)` from `comparison/`. | Good separation. Comparison does not auto-run preview. |
| Load candidate | `SimulationPreview.tsx` `loadOptimiserCandidateIntoPreview(...)`; `OptimiserCandidateDetails.tsx` confirmation flow. | Safe and explicit. Existing plan confirmation exists. |
| Manual edit after load | `SimulationPreview.tsx` `markOptimiserCandidateEdited()`. | Good safety signal, but this state belongs in a hook or planner controller later. |

What is robust: the backend makes no hidden exhaustive-search claim, the frontend explicitly sends ranking/preview flags, candidate loading clears stale simulation result/error state, and comparison is advisory. The test `SimulationPreview.optimiser.test.tsx` verifies loading a candidate does **not** auto-run `simulateBuild`, which directly protects one of the highest-risk workflow semantics.

What is fragile: selected candidate state can become stale if the target archetype changes after generation; the panel still shows the old response until the user generates again. The panel displays `Target: {targetArchetype}`, but it does not clearly say whether existing candidates were generated for the old target or current select value. Comparison uses current placements via props and recalculates with `useMemo`, which is good, but the UI does not visually stamp comparisons with “generated against target X” versus “current preview target Y” until the detailed comparison section notes a target change.

| Fragility | Evidence | Recommended Fix | Timing |
|---|---|---|---|
| Candidate response can visually survive a target archetype change. | `OptimiserCandidatePanel.tsx` stores `response` and `selectedId`, while `targetArchetype` is a prop from `SimulationPreview.tsx`. | Add a generated-parameter stamp and a warning when current target differs from response target, or reset response on target change. | Next stage |
| The optimiser panel is visually below the manual editor and result area. | `SimulationPreview.tsx` renders `OptimiserCandidatePanel` after the main preview grid at the bottom. | Move to an internal planner tab or a top “Generate Plans” mode. | Next stage |
| Target archetype explanation is thin. | `SimulationPreview.tsx` label is just “Target archetype”; `OptimiserCandidatePanel.tsx` shows `Target: ...`. | Add copy: “This guides candidate generation and ranking; it does not overwrite in-game data.” | Fix now or next stage |
| Estimated data checkbox lacks consequence explanation. | `OptimiserCandidatePanel.tsx` “Include estimated data”. | Add helper text explaining candidate breadth vs confidence risk. | Fix now |
| Full workflow tests stop before edit → run. | `SimulationPreview.optimiser.test.tsx` verifies load/no-auto-run, not edit/run after load. | Add a second integration test for load → edit → run preview payload. | Next stage |

## 5. UX Findings

The main user journeys are now understandable in isolation. Finder is the search surface. Search Tuning is now labelled as a reranking tool. System Detail is the inspection modal. Simulation Preview lets users edit and run a build preview. Stage 5 adds candidate generation, ranking, comparison, and loading into preview. The problem is not functional incoherence; it is **spatial incoherence**. The planner workflow has grown into a multi-step product, but it still appears as a sub-panel under “Simulation Preview”.

| Journey | What Works | What Is Confusing | Priority |
|---|---|---|---|
| Finder | Top-level route and search form are clear. | Finder-to-System-Detail-to-Planning handoff depends on modal discovery. | Low |
| Search Tuning | Recent copy now clearly says it reranks current Finder results and does not generate colony builds. | It remains top-level even though it is dependent on Finder results. | Medium |
| System Detail | Modal contains rating, bodies, stations, and Colony Planning. | Colony Planning is a long vertical stack without internal navigation. | High |
| Manual Simulation Preview | “Run Preview” and editable placements are clear. | “Simulation Preview” now includes more than previewing; it contains candidate generation below it. | Medium |
| Stage 5 Colony Optimiser | Safety copy is strong: load is preview-only, comparison is advisory, and nothing is committed in-game. | Candidate generation is hidden low, target archetype purpose is under-explained, and “Optimiser candidates” is a technical section name rather than a user journey. | High |

The ED orange/brushed steel style is consistent. The UI feels visually coherent, but it now feels like a pile of panels because the System Detail modal has no internal information architecture. The strongest immediate UX improvement would be to convert Colony Planning from a vertical stack into an internal workspace with modes.

Suggested user-facing copy changes are small and safe. “Optimiser candidates” should become **Plan Candidates** or **Optimiser Candidates** under a larger **Colony Planner** heading. The “Generate candidates” button should gain helper text such as: “Creates a few bounded build-plan candidates for this system using the selected archetype. It does not save or run anything in-game.” The “Target archetype” label should explain that it guides generation/ranking and may differ from the current preview target until a candidate is loaded.

## 6. Stage 5 Layout Recommendation

**Firm recommendation:** Do **Option 5** in product framing and **Option 3** in implementation sequence. Reframe the broader workspace as **Colony Planner**, then implement internal tabs/modes inside that workspace: **Build Plan**, **Optimiser Candidates**, and **Preview / Comparison**. Do not add another top-level app nav item yet. Do not leave the optimiser permanently at the bottom of Simulation Preview.

| Option | Pros | Cons | Complexity | UX Clarity | Risk | Recommendation |
|---|---|---|---|---|---|---|
| 1. Keep optimiser at bottom of Simulation Preview | No code movement. Lowest risk. | Stage 5 remains buried; Simulation Preview name becomes misleading. | Low | Low | Low | Do not choose beyond short-term. |
| 2. Move optimiser into collapsible section near top of Simulation Preview | Improves discoverability with modest change. | Still frames planner generation as a Simulation Preview sub-feature. | Low-Medium | Medium | Low | Acceptable quick win only. |
| 3. Add internal tabs inside Simulation Preview: Build Plan, Optimiser Candidates, Results/Comparison | Clearer task separation; contained refactor. | “Simulation Preview” still names the whole workspace unless renamed. | Medium | High | Medium | Recommended implementation step. |
| 4. Add System Detail-level tabs: Overview, Bodies, Simulation Preview, Colony Planner, Regional Context, Dependencies | Best long-term modal IA. | Larger refactor; touches more of System Detail. | High | Very high | Medium-High | Good later target after internal planner modes. |
| 5. Rename/reframe Simulation Preview as broader Colony Planner workspace with internal modes | Best product language. Fits current capability. | Requires careful migration of headings/tests/docs. | Medium | Very high | Medium | **Firm recommendation.** |

Stage 5.9C implemented the first low-risk version of this recommendation by reframing the existing planning surface as **Colony Planner**, adding visible **Build Plan**, **Optimiser Candidates**, and **Preview Result** structure, and moving the optimiser candidate area above the preview-result block without a broad state refactor. Stage 5.9D then reduced the main composition pressure by extracting plan state into `hooks/useSimulationPreviewPlan.ts`, preview execution into `hooks/useSimulationPreviewRun.ts`, and the header, Build Plan, section labels, and Preview Result into focused presentational components. A deeper System Detail tab/workspace refactor remains deferred.

## 7. Naming Findings

Search Tuning is the right name for the old Finder-result reranker. It is precise, low-drama, and does not imply build-plan generation. It should remain top-level temporarily because it already has a route and recent tests, but its best long-term home is under Finder as an **Advanced Search Tuning** panel.

For Stage 5, the best broad user-facing name is **Colony Planner**. “Build Optimiser” is accurate but sounds more algorithmic and risks overclaiming optimality. “Colony Optimiser” is acceptable but carries the same overclaim risk. “Optimiser Candidates” is a good sub-section name, not a workspace name. “Candidate Planner” is less natural.

| Name | Recommendation | Reason |
|---|---|---|
| Search Tuning | Keep for legacy reranker. | It accurately describes weighting/reordering Finder results. |
| Colony Planner | Use as broad workspace name. | Covers manual plans, generated candidates, preview, comparison, and later validation. |
| Optimiser Candidates | Use as sub-section. | Good for the generated-candidate panel. |
| Simulation Preview | Keep as an action/result mode. | It should mean the explicit simulation run/result, not the whole planner workspace. |
| Build Optimiser / Colony Optimiser | Avoid as top-level label for now. | It implies stronger optimality than bounded heuristic candidates provide. |

Code naming should evolve later, not now. `apps/api/src/optimiser/` is acceptable because it is a backend package and British spelling is consistent with Stage 5 code. `frontend-v2/src/features/optimizer/` should eventually become `search-tuning/`. `frontend-v2/src/features/system-detail/simulation-preview/optimiser/` should eventually move under `colony-planner/optimiser/` if the workspace is renamed.

## 8. Refactor Candidates

| Item | File(s) | Problem | Suggested Refactor | Risk | Priority | Recommended Stage |
|---|---|---|---|---|---|---|
| Planner workspace shell | `SystemDetailModal.tsx`, `SimulationPreviewPanel.tsx`, `simulation-preview/SimulationPreview.tsx` | Colony Planning is a vertical stack and Stage 5 is buried. | Introduce a `ColonyPlannerPanel` wrapper with internal modes/tabs. | Medium | High | Stage 5.9C |
| Simulation Preview state owner | `simulation-preview/SimulationPreview.tsx`, `hooks/useSimulationPreviewPlan.ts`, `hooks/useSimulationPreviewRun.ts` | Stage 5.9D extracted plan state and preview execution into focused hooks while leaving the public composition component in place. | Keep this boundary; only consider further extraction if Stage 6 validation or saved-build work adds new state domains. | Medium | Medium | Later |
| Optimiser panel parameter lifecycle | `OptimiserCandidatePanel.tsx` | Stage 5.9C now stamps generated candidates with target archetype, max candidate count, and estimated-data setting, and warns when controls differ. | Keep the warning, then consider reset-on-change or stronger stale-load affordances later if user testing shows confusion. | Low-Medium | Medium | Stage 5.9E |
| Search Tuning internal folder name | `frontend-v2/src/features/optimizer/` | Internal name conflicts with new user-facing Search Tuning terminology. | Rename to `search-tuning/` in a focused route-safe PR. | Medium | Medium | Stage 7 |
| API client feature boundaries | `frontend-v2/src/lib/api.ts` | Broad API file contains both Search Tuning rerank and Stage 5 candidate generation. | Add clearer comments now; later split feature-specific API helpers. | Low | Medium | Stage 5.9C / Later |
| Docs current-state framing | `docs/colonisation-redesign/optimiser-candidate-generator.md` | Early Stage 5A/B wording can read stale now that 5C–5F exist. | Add a current-state summary at top and a “scope by stage” table. | Low | Medium | Stage 5.9C |
| System Detail internal IA | `SystemDetailModal.tsx` | Rating/profile/bodies/stations/planning all appear in one scroll. | Later add modal-level tabs: Overview, Bodies, Colony Planner, Regional Context, Dependencies. | High | Medium | Later |
| Frontend API types breadth | `frontend-v2/src/types/api.ts` | API type file is growing with every simulation and optimiser field. | Split by domain or add generated-type guardrails after current work stabilises. | Medium | Low | Later |

## 9. Test Coverage Findings

Current test coverage is strong for many critical pieces. Backend `tests/test_optimiser.py` covers bounded candidate counts, deterministic candidate IDs, build-order sequencing, primary-port constraints, catalogue-only facilities, deduplication, fallback behavior, preview on/off, preview failure isolation, conversion helpers, endpoint response shape, and response cleanliness. Frontend `OptimiserCandidatePanel.test.tsx` covers candidate sorting, ranking display, comparison rendering, read-only mode, load confirmation, warning/reason separation, loading/error/empty states, and API request flags. `SimulationPreview.optimiser.test.tsx` verifies the most important safety behavior: loading a candidate into preview does **not** auto-run the simulation.

| Coverage Area | Current Strength | Missing or Weak Test | Priority |
|---|---|---|---|
| Backend generation | Strong. `tests/test_optimiser.py` covers deterministic generator contracts. | No full database-backed integration test with real fixture DB. | Medium |
| Backend ranking | Good heuristic coverage through backend tests. | Add explicit test that ranking IDs always refer to returned candidate IDs after all filters/dedupe. | Medium |
| Frontend candidate panel | Strong component coverage. | Add stale-generated-target warning/reset test after implementing that UI. | High |
| Load into preview | Good no-auto-run test. | Add load → edit → run preview test asserting edited placements are sent to `simulateBuild`. | High |
| Comparison engine | Strong pure-function tests. | Add UI-level accessibility checks for show/hide comparison and keyboard navigation. | Medium |
| Search Tuning | Rename tests exist. | Add nav-label test if a navigation test harness exists. | Medium |
| Full happy path | Partial. | Add integration-style test: recommended/manual plan → generate → compare → load → edit → run. | High |
| Route/nav regression | Thin. | Add tests that top-level `nav-optimizer` visibly says Search Tuning and that Stage 5 remains inside System Detail/Planner. | Medium |

## 10. Docs Findings

The docs are better than average for a fast-moving feature, but they now need a consolidation pass. `optimiser-candidate-generator.md` accurately documents Stages 5A–5F, but its opening language still frames Stage 5A/B as not including UI/load/comparison before later sections describe those stages. `engine-roadmap.md` now distinguishes Search Tuning from the Stage 5 colony optimiser, which is good. `frontend-v2/README.md` correctly identifies Search Tuning as legacy Finder-result reranking.

| Severity | Evidence | Issue | Recommendation | Timing |
|---|---|---|---|---|
| Medium | `docs/colonisation-redesign/optimiser-candidate-generator.md` | Current-state framing should be updated so readers immediately understand Stage 5A–5F are implemented. | Add a top “Current status after Stage 5F” section. | Next stage |
| Low | `docs/colonisation-redesign/simulation-preview-ui-architecture.md` | It documents decomposed Simulation Preview architecture, but the product has moved toward broader Colony Planner semantics. | Add note that Simulation Preview may become a sub-mode of Colony Planner. | Next stage |
| Low | `frontend-v2/README.md` | Search Tuning distinction is now present. | Keep as is; update only after folder rename if that happens. | Do not fix now |
| Medium | No dedicated “Colony Planner workspace” doc yet. | Stage 5 planner IA is not captured as a product architecture decision. | Add a short Stage 5.9C layout/naming doc before moving UI. | Next stage |
| Low | Search Tuning future rework note exists in roadmap and README. | Adequate for now. | Do not implement rework now. | Do not fix |

## 11. Recommended Next Stages

| Stage | Goal | Why It Matters | Scope | Non-goals | Rough File Areas | Risk | Dependencies |
|---|---|---|---|---|---|---|---|
| Stage 5.9C — Navigation / Naming / Layout Cleanup | Reframe System Detail planning as **Colony Planner** with visible Build Plan, Optimiser Candidates, and Preview Result sections. | Solves immediate discoverability and terminology issues before Stage 6 adds validation complexity. | Product copy, headings, lightweight planner structure, generated-parameter stamp, stale-control warning, docs. | No generation/ranking/scoring changes. | `simulation-preview/SimulationPreview.tsx`, `OptimiserCandidatePanel.tsx`, docs. | Medium | Current Stage 5F + Search Tuning rename. |
| Stage 5.9D — Simulation Preview / Colony Planner Workspace Refactor | Extract state ownership from `SimulationPreview.tsx`. | Reduces risk before saved builds or observed validation. | Implemented hooks for plan state and preview execution plus focused presentational sections. | No backend or scoring changes. | `simulation-preview/SimulationPreview.tsx`, `hooks/`, `BuildPlanSection.tsx`, `PreviewResultSection.tsx`, `ColonyPlannerHeader.tsx`. | Medium | 5.9C layout decision. |
| Stage 5.9E — Stage 5 Workflow and Stale-State Hardening | Add end-to-end-ish frontend tests for generate → compare → load → edit → run and make stale generated candidates / stale preview results explicit. | Protects the highest-risk user workflow before Stage 6. | Workflow tests, stale generated/current parameter copy, stale Preview Result warning, and no-auto-run assertions. | No backend, scoring, routing, Search Tuning, or Stage 6 changes. | `SimulationPreview.optimiser.test.tsx`, `OptimiserCandidatePanel.tsx`, `OptimiserCandidateDetails.tsx`, `useSimulationPreviewRun.ts`, `PreviewResultSection.tsx`. | Low-Medium | Stable UI copy from 5.9C and hook boundaries from 5.9D. |
| Stage 5.9F — Candidate Parameter Staleness Guard | Make generated candidates visibly tied to request parameters. | Prevents users comparing/loading stale target-archetype results. | Generated request stamp, stale warning/reset behavior, tests. | No backend formula changes. | `OptimiserCandidatePanel.tsx`, tests. | Low-Medium | Can run before or after 5.9D. |
| Stage 6 — Observed vs Predicted Validation Loop | Start actual observation validation after planner IA and stale-state safety are clear. | Validation will add complexity; planner should be understandable and stale-safe first. | Observation ingestion/validation workflow as planned. | Do not mix with layout or workflow-stale refactors. | Observations backend/frontend. | Medium-High | 5.9C–5.9E preferred. |
| Stage 7 — Search Tuning Rework | Demote/refine Search Tuning with presets, rank movement, and explanations. | Search Tuning remains useful, but it is advanced Finder functionality. | Folder rename, Finder integration, before/after movement, presets. | No colony optimiser changes. | `features/optimizer` → `features/search-tuning`, Finder route. | Medium | After planner naming stabilizes. |

## 12. Quick Wins

The fastest safe improvement is a copy-only Stage 5.9C-lite change: rename the visible “Optimiser candidates” heading to “Plan Candidates” or “Optimiser Candidates” under a new “Colony Planner” wrapper, add helper text under Target Archetype, and add a generated-parameter summary in the candidate panel. These changes would improve user comprehension without touching backend logic.

| Quick Win | File(s) | Benefit | Risk |
|---|---|---|---|
| Add target archetype helper text. | `SimulationPreview.tsx`, `OptimiserCandidatePanel.tsx` | Users understand why the selector matters. | Low |
| Add generated-parameter stamp. | `OptimiserCandidatePanel.tsx` | Implemented in Stage 5.9C; candidates now show generated target, max count, estimated-data state, and stale-control warning. | Low |
| Rename broad heading to Colony Planner while keeping Simulation Preview as subheading. | `SimulationPreviewPanel.tsx` or wrapper. | Clarifies workspace purpose. | Medium |
| Add nav-label test for Search Tuning. | `NavBar` test or app-level test. | Prevents regression to old top-level label. | Low |
| Update Stage 5 docs current-status intro. | `optimiser-candidate-generator.md` | Reduces docs drift. | Low |

## 13. Risks if Ignored

If the current structure remains unchanged, the main risk is not a code crash; it is user misunderstanding. Users may not find the candidate generator, may think Simulation Preview automatically applies plans, may compare stale generated candidates against a changed target, or may misunderstand Search Tuning as related to colony planning despite the recent rename.

The engineering risk is that Stage 6 observed-vs-predicted validation would add another complex layer to an already crowded Simulation Preview workspace. If validation UI, observation facts, candidate generation, candidate comparison, manual plan editing, and preview results all live in the same vertical stack, future work will become slower and more brittle.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stage 5 remains undiscovered. | Medium | High | Give Colony Planner its own internal space. |
| Stale candidate results are loaded after target changes. | Medium | Medium | Add generated-request stamp/reset warning. |
| Simulation Preview becomes a state monolith again. | High | Medium | Extract plan and optimiser-loading hooks. |
| Search Tuning confusion returns. | Low-Medium | Medium | Eventually move Search Tuning under Finder/Advanced. |
| Stage 6 validation overwhelms planner UI. | High | High | Complete 5.9C–5.9E before Stage 6. |

## 14. Do-Not-Do List

Do not start Stage 6 until the planner surface has a clearer workspace name and at least one stronger end-to-end workflow test. Do not rewrite backend candidate generation or ranking, because the current bounded deterministic implementation is structurally sound. Do not rename backend `apps/api/src/optimiser/` during the UX cleanup. Do not remove Search Tuning. Do not move Search Tuning under Finder in the same PR that refactors Colony Planner, because that would mix two product moves. Do not introduce saved builds, commander accounts, journal upload, EDMC integration, or automatic observed-vs-predicted validation during the layout cleanup.

## Review Evidence File Index

| Area | Key Files Reviewed |
|---|---|
| App/nav structure | `frontend-v2/src/App.tsx`, `frontend-v2/src/components/NavBar.tsx` |
| System Detail placement | `frontend-v2/src/features/system-detail/SystemDetailModal.tsx`, `SimulationPreviewPanel.tsx` |
| Simulation Preview orchestration | `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx` |
| Stage 5 frontend | `frontend-v2/src/features/system-detail/simulation-preview/optimiser/OptimiserCandidatePanel.tsx`, `OptimiserCandidateDetails.tsx`, `OptimiserComparisonPanel.tsx` |
| Stage 5 backend | `apps/api/src/routers/optimiser.py`, `apps/api/src/optimiser/candidate_generator.py`, `ranker.py`, `models.py` |
| Search Tuning | `frontend-v2/src/features/optimizer/OptimizerTab.tsx`, `useOptimizer.ts`, `OptimizerTab.test.tsx` |
| Tests | `tests/test_optimiser.py`, `OptimiserCandidatePanel.test.tsx`, `SimulationPreview.optimiser.test.tsx`, `comparisonEngine.test.ts`, `OptimizerTab.test.tsx` |
| Docs | `docs/colonisation-redesign/optimiser-candidate-generator.md`, `simulation-preview-ui-architecture.md`, `engine-roadmap.md`, `frontend-v2/README.md` |
