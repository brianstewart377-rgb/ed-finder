# Stage 9A - Full App UX / Navigation Forensic Review

## Executive Summary

ED-Finder now reads as one mostly coherent app: Finder discovers systems, System Detail inspects one system, Colony Planner evaluates build plans for that system, Advanced Search Tuning temporarily re-prioritises current Finder results, and Pinned / Watchlist / Compare / Map organise systems after discovery.

The biggest remaining UX risk is not broken behaviour. It is information architecture density. The top navigation has many first-level surfaces, and System Detail is doing heavy work as the hub for inspection, recommended plans, Colony Planner, evidence, and validation. Stage 8C made the Colony Planner workflow understandable, but Stage 9B should decide whether the app needs a larger navigation cleanup or a dedicated planner workspace.

Tiny fixes applied in Stage 9A:

- Top nav `FC` is now `FC Planner`.
- Top nav `Colony` is now `Colony Tracker` to avoid confusion with embedded Colony Planner.
- App footer now says `prototype` instead of `proof of concept`, avoiding a noisy user-facing `proof` match.
- Advanced Search Tuning copy now says it builds a temporary tuned order rather than `reranks`.
- Advanced Search Tuning handoff copy now says it does not run `Preview`, matching Stage 8 planner language.
- Recommended Builds fallback copy now says `Estimated body option` instead of `Estimated body candidate`.
- Hash-route tests now cover every top-level tab, child system modal routes, legacy `#optimizer/system/{id64}`, external `#system/{id64}`, unknown fallback, and modal close.

No backend mechanics, scoring, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, persistence, or route architecture changed.

## Current App Map

| route/tab | visible label | purpose | primary user action | related components/files |
|---|---|---|---|---|
| `#finder` | Finder | Discover systems with filters and ratings. | Run search, expand result cards, open details, evaluate in Colony Planner, pin/watch/compare/map. | `frontend/src/App.tsx`, `frontend/src/features/search/SearchForm.tsx`, `frontend/src/components/ResultCard.tsx`, `frontend/src/features/search/useSearch.ts` |
| `#watchlist` | Watchlist | Server-backed saved systems list. | Refresh, sort, remove, open detail, show on map. | `frontend/src/features/watchlist/WatchlistTab.tsx`, `frontend/src/features/watchlist/useWatchlist.ts`, `frontend/src/components/SystemTable.tsx` |
| `#pinned` | Pins | Local shortlist stored in browser. | Sort, export JSON, clear, unpin, open detail, show on map. | `frontend/src/features/pinned/PinnedTab.tsx`, `frontend/src/features/pinned/usePinned.ts`, `frontend/src/components/SystemTable.tsx` |
| `#compare` | Compare | Side-by-side comparison for selected systems. | Compare metrics, open detail, remove, export CSV. | `frontend/src/features/compare/CompareTab.tsx`, `frontend/src/features/compare/useCompare.ts` |
| `#search-tuning` | Advanced Search Tuning | Temporarily re-prioritise current Finder results. | Adjust weights, show tuned order, inspect/evaluate tuned rows. | `frontend/src/features/search-tuning/AdvancedSearchTuningTab.tsx`, `frontend/src/features/search-tuning/useSearchTuning.ts` |
| `#optimizer` | no nav label; legacy alias | Backward-compatible alias for Advanced Search Tuning. | Old links still render Advanced Search Tuning. | `frontend/src/hooks/useHashRoute.ts`, `frontend/src/hooks/useHashRoute.test.ts` |
| `#fc` | FC Planner | Fleet Carrier route, hop, tritium, and cost planning. | Add waypoints, tune carrier config, export CSV. | `frontend/src/features/fc-planner/FcPlannerTab.tsx`, `frontend/src/features/fc-planner/useFcPlanner.ts` |
| `#colony` | Colony Tracker | Local tracker for claimed colonisation projects. | Track system, update phase/progress, export CSV. | `frontend/src/features/colony/ColonyTab.tsx`, `frontend/src/features/colony/useColony.ts` |
| `#map` | Map | Spatial view of current Finder results. | Pan/zoom, select plotted system. | `frontend/src/features/map/MapTab.tsx`, `frontend/src/features/map/GalacticMap.tsx` |
| `#admin` | Admin | Ops console and profile sync controls. | Set token, refresh status, run admin actions, configure sync key. | `frontend/src/features/admin/AdminTab.tsx`, `frontend/src/features/admin/useAdmin.ts`, `frontend/src/features/profile-sync/useProfileSync.ts` |
| `#{route}/system/{id64}` | System Detail modal over current tab | Inspect one system without losing current tab context. | Close/backdrop/Escape, save/pin/compare, open Colony Planner. | `frontend/src/hooks/useHashRoute.ts`, `frontend/src/features/system-detail/SystemDetailModal.tsx` |
| `#system/{id64}` | System Detail over Finder | External or direct system deep link. | Opens Finder with modal selected. | `frontend/src/hooks/useHashRoute.ts` |
| fixed bottom chrome | EDDN live feed | Ambient live system/event ticker. | Filter event types, click an event to open system detail. | `frontend/src/features/eddn/EddnTicker.tsx`, `frontend/src/features/eddn/useEddnFeed.ts` |

## User Journey Map

| journey | entry point | current behaviour | friction | recommendation | priority |
|---|---|---|---|---|---|
| New user lands on Finder | Empty hash or `#finder` | App loads Finder, health status, SearchForm, and default search run. | Top nav is dense for a first visit. | Stage 9B can evaluate grouping secondary tools under an overflow or workspace switcher. | Medium |
| User runs a search | Finder form | Filters and presets drive `useSearch`; results render as collapsible cards. | Search form is comprehensive but long. | Defer broad form simplification; consider a compact/basic mode later. | Medium |
| User opens a result | Result card `Details` or row/table click | Opens `SystemDetailModal` over current tab via `#{route}/system/{id64}`. | Cards require expansion before Details/Evaluate actions are visible. | Result-card action polish pass could expose one primary action on collapsed cards. | Medium |
| User evaluates in Colony Planner | Result card or Search Tuning `Evaluate in Colony Planner` | Opens system detail and focuses/highlights embedded Colony Planner. | Planner still lives below Buildability/Recommended Builds inside a large modal. | Dedicated Colony Planner workspace remains a Stage 9B+ option. | High |
| User uses Suggested Builds | Colony Planner `Show Suggested Builds` then `Generate Suggested Builds` | Focuses Suggested Builds first; generation remains explicit. | The older Recommended Builds panel above Colony Planner is still a second suggestion concept. | Keep copy distinction; later decide whether Recommended Builds should fold into Suggested Builds. | Medium |
| User runs Preview | Colony Planner `Run Preview` | Explicitly evaluates current Build Plan and shows Preview Result guidance first. | Dense detailed panels follow the verdict. | Keep current sequence; a future visual hierarchy pass can collapse advanced details. | Low |
| User understands next steps | Preview Result verdict | Branches into not-run, stale, needs-work, estimate, viable states. | Good enough after Stage 8C. | No immediate change. | Low |
| User records Observed Evidence later | Colony Planner later-step panel | Records manually observed evidence after in-game checking. | Embedded late in a long planner stack. | If planner gets a workspace, later-step panels could become secondary tabs. | Medium |
| User validates prediction later | Validation / Review Guidance | Compares Preview Result with recorded evidence and provides advisory review. | Name `Validation` can imply proof if isolated from advisory copy. | Keep conservative copy; audit again when validation expands. | Medium |
| User uses Advanced Search Tuning | `#search-tuning` nav or legacy `#optimizer` | Uses current Finder results, builds temporary tuned order, can open/evaluate systems. | Advanced top-level tab is powerful but niche. | Consider grouping with Finder tools in Stage 9B. | Medium |
| User pins/watches/compares systems | Result card or modal actions | Pinned local, Watchlist server/account-like, Compare local matrix. | Watchlist vs Pins distinction is explained in empty states/tooltips but still subtle. | Add a short comparison note in nav/help later if support confusion appears. | Low |
| User views map | Result card Map action or `#map` | Shows current Finder results only. | Map does not open detail from selected star; it only shows a side panel. | Add an `Open detail` action in Map selection panel in a later map audit. | Medium |
| User uses Fleet Carrier planner | `#fc` | Route planner with autocomplete waypoints and tritium/cost summary. | Previous nav label `FC` was terse. | Fixed to `FC Planner`. | Fixed |
| User sees EDDN ticker | Bottom ticker | Ambient live feed; pips open system detail. | Persistent bottom chrome may distract during modal-heavy work. | Defer; consider collapse/pause setting in production-readiness QA. | Low |
| User opens Admin | `#admin` | Token-gated ops actions and profile sync controls. | Admin is top-level and visible to all users. | Stage 9B should decide whether Admin belongs in secondary nav or dev-only environment gating. | High |

## Terminology Findings

| term | location/type | issue | recommended wording | action taken/deferred |
|---|---|---|---|---|
| Optimiser / optimiser candidates | Internal API/types/tests/docs under `frontend/src/lib/api.ts`, `simulation-preview/optimiser/`, docs | Backend/internal vocabulary remains necessary; visible planner UI mostly uses Suggested Builds. | User-facing: Suggested Builds. Internal: optimiser is acceptable. | Deferred internal rename; not worth contract churn. |
| Optimizer | `#optimizer` route alias and tests | Legacy route name could confuse if surfaced. It is not visible in nav. | Preferred route: `#search-tuning`. | Kept for compatibility; tests added for `#optimizer/system/{id64}`. |
| Rerank / reranked | API helper, tests, backend route, some data fields | Backend term is accurate but user-facing copy should say temporary tuned order. | Advanced Search Tuning, tuned order, temporary tuned score. | User-facing copy changed; internal/API/test names retained. |
| Simulation Preview | Docs, API comments, some internal labels | Still valid as backend/API concept; Stage 8 user path prefers Preview / Preview Result. | User-facing planner: Preview / Preview Result. | Search Tuning helper changed to `Preview`; docs classify backend usage. |
| Candidate | Internal optimiser types and some generated labels from test fixtures/API data | API response uses candidate IDs/labels; current UI labels the section Suggested Builds. | Suggested build. | No broad rename; backend-generated labels may still contain candidate when returned by API/test data. |
| Observed facts | API/docs/internal comments | Backend contract term. User-facing UI uses Observed Evidence. | Observed Evidence. | Deferred internal rename; docs explicitly distinguish. |
| Mechanics trace | System detail detailed panels and docs | Advanced detail panel is technical but appropriate after Preview Result. | Keep as advanced mechanics detail. | Deferred; no user-facing top-level nav issue. |
| proof / wrong / guaranteed / optimal | Tests/comments/historical docs and old footer | Validation copy deliberately avoids these as verdicts. Footer `proof of concept` created a user-facing grep hit. | prototype, needs review, estimate, likely. | Footer changed; remaining hits are comments/tests/historical/developer docs. |
| Copy to Build Plan / Optimiser Candidates | Historical docs and internal docs | Historical docs preserve old stage context. Current UI uses Copy to Build Plan / Suggested Builds. | Copy to Build Plan / Suggested Builds. | Deferred historical docs rewrite; current UI is clean. |

## Routing Findings

| route/deep link | current behaviour | test coverage | issue | recommendation |
|---|---|---|---|---|
| empty hash / unknown hash | Falls back to Finder. | Added in `useHashRoute.test.ts`. | Good. | Keep. |
| top-level tabs | `finder`, `watchlist`, `pinned`, `compare`, `map`, `search-tuning`, `fc`, `colony`, `admin`. | Added all-route parse coverage. | Good; many top-level tabs. | IA cleanup later. |
| `#{route}/system/{id64}` | Opens System Detail modal over parent tab. | Added child-route coverage. | Good. | Keep. |
| `#system/{id64}` | Opens System Detail over Finder. | Added coverage. | Good external fallback. | Keep. |
| `#optimizer` | Legacy alias to `search-tuning`. | Existing and expanded coverage. | Good compatibility; should stay invisible. | Keep alias, prefer `#search-tuning`. |
| `#optimizer/system/{id64}` | Legacy alias with modal. | Added coverage. | Good. | Keep. |
| close modal | Removes `system/{id64}` and preserves parent tab. | Added coverage. | Good. | Keep. |
| navigate while modal open | `navigate()` preserves open selected system. | Existing hook design; not newly tested. | Could surprise users if changing tabs with modal open. | Documented; revisit only if users report confusion. |

## Navigation / IA Findings

| severity | finding | evidence | recommendation |
|---|---|---|---|
| High | Admin is a first-level user-visible tab despite being ops/dev oriented. | `NavBar.tsx` always renders `⚙️ Admin`; `AdminTab.tsx` includes token-gated ops actions. | Stage 9B should decide whether Admin is dev-only, secondary, or gated by environment/role. |
| High | Colony Planner and Colony Tracker are distinct but close enough to confuse. | Planner lives inside `SystemDetailModal`; tracker is top-level `#colony`. | Fixed nav label to `Colony Tracker`; consider help text if confusion remains. |
| Medium | Advanced Search Tuning is correctly labelled but probably belongs conceptually under Finder. | It uses current Finder results only, but appears as a peer of Finder. | Stage 9B IA option: group as Finder tool or secondary action from Finder results. |
| Medium | Top nav breadth is high. | Nine tabs plus density/status controls and bottom EDDN ticker. | Stage 9B navigation cleanup should evaluate grouping lower-frequency tools. |
| Medium | Map currently visualises Finder results but cannot open full detail from its selection panel. | `MapTab.tsx` has `SelectionPanel` only. | Later map audit: add explicit `Open detail` if routing callback is threaded in. |
| Low | Watchlist vs Pins distinction exists but requires reading. | Nav tooltips and empty states explain server/account vs local. | Keep; add help only if user confusion appears. |

## System Detail / Modal Findings

| severity | finding | evidence | recommendation |
|---|---|---|---|
| High | System Detail is the app's central hub and is dense. | `SystemDetailModal.tsx` includes rating, system info, bodies, stations, exploration, buildability, regional position, recommended builds, Colony Planner, slots, external links, actions. | Dedicated planner route/workspace remains the most valuable larger deferred change. |
| Medium | Recommended Builds and Suggested Builds remain two suggestion concepts. | `RecommendedBuildsPanel.tsx` appears above the embedded Colony Planner; Suggested Builds inside planner. | Stage 8C copy helps; later decide whether to fold Recommended Builds into planner. |
| Medium | Modal focus/scroll is robust after Stage 8, but modal route state can persist across tab changes. | `useHashRoute.navigate()` preserves `selectedSystemId`. | Keep for now; if confusing, consider closing modal on tab navigation. |
| Low | Keyboard/backdrop/body-scroll behaviour is covered. | `SystemDetailModal.test.tsx` covers close paths and focus. | No change. |

## Workflow Boundary Findings

| boundary | current state | risk | recommendation |
|---|---|---|---|
| Finder vs Advanced Search Tuning | Copy says Advanced Search Tuning uses current Finder results and does not run a new search. | Medium: still top-level peer. | Consider Finder sub-tool placement later. |
| Advanced Search Tuning vs Colony Planner | Evaluate action focuses planner but does not run Preview or generate builds. | Low after Stage 8C/9A copy. | Keep. |
| Suggested Builds vs Search Tuning | Suggested Builds lives inside planner and generates build plans; Search Tuning reorders Finder results. | Low. | Keep clear section labels. |
| Preview Result vs Observed Evidence | Preview Result is prediction; evidence is later user-recorded observation. | Low after Stage 8. | Keep later-step copy. |
| Validation / Review Guidance vs automatic correction | Copy says advisory/passive and does not change mechanics. | Medium as validation grows. | Re-audit when Stage 6E+ expands. |
| Compare vs Colony Planner comparison | Compare tab compares systems; planner comparison compares build plans/suggested builds. | Medium. | If planner workspace is added, name build-plan comparison explicitly. |
| Colony Tracker vs Colony Planner | Tracker is local project status; planner evaluates a build. | Medium. | Fixed nav label to Colony Tracker. |

## Test Coverage Findings

| area | current coverage | gap | action |
|---|---|---|---|
| Route parsing | `useHashRoute.test.ts` covered Search Tuning alias only. | Missing full route/deep-link matrix. | Added broad route/deep-link tests. |
| Nav labels | `NavBar.test.tsx` covered Advanced Search Tuning. | Did not protect clarified FC/Colony labels. | Added assertions for `FC Planner` and `Colony Tracker`. |
| Finder result actions | `ResultCard.test.tsx` covers Details, Evaluate, watch/map/pin/compare/copy. | Good. | No change. |
| Search Tuning route/handoff | `App.test.tsx`, `AdvancedSearchTuningTab.test.tsx`. | Copy assertion needed update. | Updated. |
| System Detail modal | CTA/focus/close/timer tests exist. | Good. | No change. |
| Colony Planner workflow | Suggested Builds, Build Plan status, Preview guidance, Evidence/Validation tests exist. | Good. | No change. |
| Map | No route smoke test; component behavior likely untested. | Map selection/open-detail workflow needs later audit. | Deferred. |
| Compare/Pinned/Watchlist | Hook tests and shared table coverage; tab smoke coverage is limited. | Could add tab smoke tests later. | Deferred. |
| FC Planner | Hook tests exist. | UI smoke limited. | Deferred. |
| Admin | App route smoke absent. | Admin visibility decision should precede more tests. | Deferred. |

## Tiny Fixes Applied

- `frontend/src/components/NavBar.tsx`: changed `FC` to `FC Planner` and `Colony` to `Colony Tracker`.
- `frontend/src/components/NavBar.test.tsx`: added assertions for the clarified labels.
- `frontend/src/App.tsx`: changed footer `proof of concept` to `prototype`.
- `frontend/src/features/system-detail/BuildPlanCard.tsx`: changed `Estimated body candidate` fallback copy to `Estimated body option`.
- `frontend/src/features/search-tuning/AdvancedSearchTuningTab.tsx`: changed user-facing `reranks a copy` copy to `builds a temporary tuned order`; changed handoff helper from `Simulation Preview` to `Preview`.
- `frontend/src/features/search-tuning/AdvancedSearchTuningTab.test.tsx`: updated copy assertion.
- `frontend/src/hooks/useHashRoute.ts`: updated stale route parser comment.
- `frontend/src/hooks/useHashRoute.test.ts`: added route/deep-link/fallback/close coverage.

## Deferred Work

- Decide whether Admin should be hidden, secondary, or environment-gated.
- Evaluate a grouped navigation model for advanced/secondary tools.
- Consider moving Advanced Search Tuning into the Finder workflow instead of a top-level peer.
- Consider a dedicated Colony Planner workspace or route once the embedded modal surface becomes too dense.
- Decide whether Recommended Builds should be folded into Suggested Builds.
- Add an `Open detail` action from Map selection.
- Add focused UI smoke tests for Map, Watchlist, Pinned, Compare, FC Planner, Colony Tracker, and Admin after IA decisions.
- Run a production-readiness QA pass for EDDN ticker distraction, mobile nav wrapping, and modal density.

## Recommended Stage 9B Options

| option | scope | why |
|---|---|---|
| Navigation / IA cleanup | Group secondary tools, decide Admin visibility, consider Finder-adjacent placement for Advanced Search Tuning. | Highest app-coherence payoff. |
| Result-card/action polish | Improve collapsed-card action discoverability and reduce action clutter. | Finder remains the primary entry point. |
| Map / Compare / Pinned / Watchlist audit | Harden organisation workflows and cross-links. | These are now mature enough for workflow QA. |
| Dedicated Colony Planner workspace | Move planner from dense modal into a larger focused surface. | Highest value if Colony Planner becomes a primary repeated workflow. |
| Hauling/material planning audit | Review missing build effort/material/trip planning. | Repeatedly deferred and likely important for real colony use. |
| Production-readiness QA | Mobile nav, Admin visibility, EDDN ticker controls, status messaging. | Needed before broader release. |

## Final Recommendation

Stage 9A should be treated as a map, not a rebuild. The current app is coherent enough to keep shipping targeted hardening, but the next major UX work should be an IA/navigation decision: either group secondary tools around Finder/System Detail, or split Colony Planner into a dedicated workspace. Do not start new mechanics or persistence work before that navigation decision is made.

