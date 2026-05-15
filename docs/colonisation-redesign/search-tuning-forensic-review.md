# Stage 7A - Search Tuning / Finder Rerank Forensic Review

## Executive Summary

Search Tuning currently reranks the systems already returned by Finder. It does not run a new search, change `/api/local/search` ordering, persist preferences, generate colony build plans, or feed into Colony Planner. The user chooses an optional economy preference and six weights; the frontend sends up to 500 current Finder `id64`s to `POST /api/ratings/rerank`; the backend reads existing rows from `ratings`, computes a temporary weighted score, sorts the returned subset, and returns an explanatory result list.

The feature is useful as an advanced Finder-analysis tool, but it is still too prominent and internally named too close to the colony optimiser. Current UI copy is much clearer than the legacy "Optimizer" framing, but the route/folder/hook names still say `optimizer`, and the top-level tab can make a Finder-dependent helper look like a main workflow. Stage 7B should reframe it as **Advanced Search Tuning** inside or adjacent to Finder, improve before/after rank explanations and presets, and preserve `/api/ratings/rerank` as the internal/backend name.

## Stage 7B Implementation Addendum

Stage 7B reframed the user-facing surface as **Advanced Search Tuning** while preserving the backend/internal ratings rerank terminology and behaviour. The feature still sends current Finder result IDs to `POST /api/ratings/rerank`, receives a temporary sorted subset, and renders that tuned order separately from Finder.

The Stage 7B UI now states that Advanced Search Tuning:

- re-prioritises the current Finder results only
- reranks a copy of those results
- does not run a new search
- does not save preferences or persist tuning weights
- does not change stored ratings
- does not alter normal `/api/local/search` ordering
- does not change Colony Planner
- does not use Observed Evidence / Validation output

Stage 7B also clarifies that economy selection is a scoring emphasis, not a filter; weight sliders apply only to the current tuning run; tuned score is temporary; and stored rationale comes from existing rating data rather than a new tuned-score explanation. Result rows now show original Finder rank, tuned rank, and movement up/down/unchanged using a frontend-only source-rank snapshot captured when the tuning run starts. Rank movement does not read from live Finder results after the run, so a later Finder search cannot change the displayed original rank for existing tuned results. `/api/ratings/rerank`, `RerankRequest`, and `RerankResponse` remain valid backend/internal names.

The preferred route alias is `#search-tuning`; legacy `#optimizer` remains supported for direct-link compatibility. Internal names such as `OptimizerTab`, `useOptimizer`, and the `optimizer` route are deferred compatibility debt for a later route-safe cleanup.

Deferred follow-up candidates include small local/static presets and deeper contribution explanations. Those remain separate from persistence, automatic learning, LLM-driven reranking, Colony Planner changes, and validation-evidence ranking changes.

## Stage 7C Implementation Addendum

Stage 7C completed the internal frontend rename that Stage 7B deferred. Advanced Search Tuning now lives under `frontend-v2/src/features/search-tuning/` with `AdvancedSearchTuningTab`, `useSearchTuning`, `UseSearchTuning`, `SearchTuningState`, and `SearchTuningSourceSnapshot`. Feature test IDs now use the `search-tuning-*` prefix.

The preferred route is `#search-tuning`. Legacy `#optimizer` direct links remain supported, but the hash router normalizes that legacy alias to the `search-tuning` route internally so future navigation uses the preferred path.

Backend rerank terminology remains unchanged: `/api/ratings/rerank`, `RerankRequest`, `RerankResponse`, and `RerankWeights` still describe the API contract. Stage 7C did not change backend scoring, normal Finder search ordering, Colony Planner, Stage 5 optimiser logic, Stage 6 validation/review logic, persistence, or evidence usage.

## Stage 7D Implementation Addendum

Stage 7D adds deterministic row explanations and a clearer Finder-to-planner handoff. `/api/ratings/rerank` now includes additive optional row fields:

- `contributions`: pre-confidence weighted contributions for the six rerank dimensions.
- `signals`: stored/raw rating signals used by the rerank row.

The backend score formula, request shape, economy fallback behaviour, and result sorting are unchanged. Contributions are shown as pre-confidence values; final temporary tuned score may still reflect the existing confidence multiplier.

The frontend renders "Why this tuned position?" with top contributors, weaker signals, and a confidence note when available. Rows now expose "Open system detail" and "Evaluate in Colony Planner" actions. Both actions only open system detail for inspection; they do not auto-run Simulation Preview, generate builds, mutate Colony Planner, persist preferences, change Finder ordering, or consume validation/review evidence.

## Current Implementation Map

### Backend

| Area | Files | Notes |
|---|---|---|
| Normal Finder search | `apps/api/src/routers/search.py`, `apps/api/src/local_search.py`, `apps/api/src/search_economies.py`, `apps/api/src/models.py` | `POST /api/local/search` validates `LocalSearchRequest`, converts it to a dict, caches by the full request body, delegates to `local_db_search`, and returns `SearchResponse`. Normal ordering is `display_score_col DESC, dist ASC` when `sort_by == "rating"`, otherwise distance. |
| Ratings rerank used by Search Tuning | `apps/api/src/routers/ratings.py`, `apps/api/src/models.py`, `apps/api/src/search_economies.py` | `POST /api/ratings/rerank` accepts a bounded list of IDs, optional `RerankWeights`, and optional economy. It reads existing `ratings` rows and returns a temporary sorted subset. |
| Adjacent archetype rerank API | `apps/api/src/routers/archetypes.py`, `apps/api/src/models.py` | `POST /api/archetypes/rerank` reranks supplied IDs by archetype weights/profiles from archetype tables. It is not wired into the current Search Tuning tab. |
| Router registration | `apps/api/src/main.py` | Includes `ratings_router`, `search_router`, and `archetypes_router`. `main.py` comments explicitly preserve `routers/ratings.py` as v3.1 rerank. |

`POST /api/ratings/rerank` request shape:

```json
{
  "id64s": [12345, 67890],
  "weights": {
    "economy": 0.42,
    "slots": 0.23,
    "strategic": 0.18,
    "safety": 0.10,
    "terraforming": 0.05,
    "diversity": 0.02
  },
  "economy": "Tourism"
}
```

`id64s` is required, `min_length=1`, `max_length=500`. `weights` is optional and defaults to the v3.1 weights in `routers/ratings.py`; supplied weights are clamped to `[0, 1]` then normalized server-side. `economy` is optional. If present and recognized, the economy dimension uses that per-economy score column. If omitted or unrecognized, the backend uses the greatest available per-economy score and reports the stored `economy_suggestion` per row.

Response shape:

```json
{
  "weights_applied": {
    "economy": 0.42,
    "slots": 0.23,
    "strategic": 0.18,
    "safety": 0.10,
    "terraforming": 0.05,
    "diversity": 0.02
  },
  "economy_used": "Tourism",
  "results": [
    {
      "id64": 12345,
      "reranked_score": 87,
      "original_score": 74,
      "confidence": 0.95,
      "rationale": "Stored ratings rationale",
      "economy_used": "Tourism"
    }
  ]
}
```

Backend data used by `/api/ratings/rerank`:

- `ratings.system_id64`
- `ratings.score`
- per-economy rating columns from `search_economies.ECONOMIES`
- `ratings.slots`
- `ratings.body_quality`
- `ratings.orbital_safety`
- `ratings.terraforming_potential`
- `ratings.body_diversity`
- `ratings.confidence`
- `ratings.rationale`
- `ratings.economy_suggestion`

Formula used by `/api/ratings/rerank`:

```text
reranked =
  eco_score * economy_weight +
  slots * slots_weight +
  body_quality * strategic_weight +
  orbital_safety * safety_weight +
  terraforming_potential * terraforming_weight +
  body_diversity * diversity_weight * (100 / 30)

if confidence is present:
  reranked *= confidence
```

The endpoint is read-only over database state. It does not persist weights, mutate ratings/search state, write cache entries, call Colony Planner, call optimiser candidate generation, call simulation, call observed-evidence validation, or change future search order. It is deterministic for a fixed database snapshot, request payload, and row set. Result cardinality is bounded by the 500-ID request limit. It can return fewer rows than requested if some IDs have no `ratings` row.

Error handling is thin: request validation handles empty/oversized ID lists; database errors are not wrapped in the problem-details style used by `routers/search.py`, so failures would surface as default FastAPI errors. Unknown economy strings silently fall back to "auto"/greatest per-economy behaviour because `ratings_score_column()` returns `score` for unknowns.

### Frontend

| Area | Files | Notes |
|---|---|---|
| Top-level entry | `frontend-v2/src/components/NavBar.tsx`, `frontend-v2/src/hooks/useHashRoute.ts`, `frontend-v2/src/App.tsx` | The visible tab label is "Advanced Search Tuning"; `search-tuning` is the preferred route and legacy `#optimizer` normalizes to it. |
| Advanced Search Tuning UI | `frontend-v2/src/features/search-tuning/AdvancedSearchTuningTab.tsx` | Renders the heading, source badge, economy scoring emphasis selector, six weight sliders, reset control, tuned-order button, loading/error/empty/results states, original Finder rank, tuned rank, movement labels, temporary tuned score, stored score/rationale labels, and row click to system detail. |
| Search Tuning state | `frontend-v2/src/features/search-tuning/useSearchTuning.ts` | Owns local weights/economy/state. `run(source)` slices current Finder results to 500 IDs, snapshots source rank/name, and calls `api.rerank`. |
| API helper | `frontend-v2/src/lib/api.ts` | `api.rerank(body)` posts to `/ratings/rerank`. The same file also contains `optimiserCandidates()`, which increases naming collision risk. |
| Types/defaults | `frontend-v2/src/types/api.ts`, `frontend-v2/src/types/api.gen.ts` | Exposes `RerankRequest`, `RerankResponse`, `RerankRow`, `RerankWeights`, and `DEFAULT_WEIGHTS`. |
| Finder source data | `frontend-v2/src/features/search/useSearch.ts`, `frontend-v2/src/features/search/SearchForm.tsx`, `frontend-v2/src/App.tsx` | Finder owns the actual search request/results. Search Tuning consumes `search.results`; it does not own search filters or trigger Finder search. |

Current user inputs:

- Finder result set from the last Finder search.
- Economy scoring emphasis: `Auto (per-row stored suggestion)`, `Agriculture`, `Refinery`, `Industrial`, `HighTech`, `Military`, `Tourism`, or `Extraction`.
- Weight sliders: Economy, Slots, Strategic, Safety, Terraforming, Diversity.
- Reset to v3.1 defaults.
- Show tuned order button.

Current user-visible outputs:

- Source count: "Source: N systems from current Finder results".
- Empty guidance when no Finder results exist.
- Loading copy: "Building tuned order...".
- Error message from the thrown API error.
- Tuned rows showing original Finder rank, tuned rank, movement, system name or fallback ID, stored rating rationale, economy used, confidence, temporary tuned score, original stored score, and original-to-tuned score delta.

The UI now says "Re-weight and reorder your current Finder results" and "This tunes Finder search results only. It does not generate colony build plans." That wording is accurate. The remaining ambiguity is placement and naming, not the core explanatory sentence.

### Tests

Existing backend tests:

- `tests/integration/test_phase6_api_coverage.py` covers `/api/ratings/rerank` default response shape, bounded score range, and `economy=Extraction`.
- `tests/test_search_economies_unit.py` covers canonical economy column mapping including `score_extraction`.
- `tests/integration/test_phase2_search_no_fallback.py`, `tests/integration/test_search_economy_enum.py`, and `tests/integration/test_search_query_safety.py` cover normal search routing/validation/safety, not Search Tuning specifically.

Existing frontend tests:

- `frontend-v2/src/features/optimizer/OptimizerTab.test.tsx` covers the Search Tuning heading, Finder-result scope copy, ready-state copy, source badge, and rerank button behaviour.
- Colony Planner optimiser tests under `frontend-v2/src/features/system-detail/simulation-preview/` cover the Stage 5/6 planner workflow and passivity, not Search Tuning.

Relevant docs:

- `frontend-v2/README.md` accurately describes Search Tuning as legacy Finder-result reranking via `/api/ratings/rerank`.
- `docs/colonisation-redesign/engine-roadmap.md` already distinguishes Stage 5 colony optimiser from Search Tuning and notes future Search Tuning work.
- `docs/colonisation-redesign/stage-5-9-forensic-structural-ux-wiring-review.md` calls out the old `optimizer` internal names and recommends moving Search Tuning under Finder/Advanced later.
- `docs/colonisation-redesign/COLONISATION_ENGINE_REDESIGN.md` contains useful historical API/rerank context, but section 10.5 overclaims optional `use_archetype_engine` support on `/api/ratings/rerank`; that field is not present in the current `RerankRequest`.

## User Expectation vs Actual Behaviour

| UI element / term | Likely user expectation | Actual behaviour | Confusion risk | Recommendation |
|---|---|---|---|---|
| Top-level "Search Tuning" tab | A main search workflow or persistent tuning area. | A dependent tool that reranks only the current Finder result IDs. | Medium | Stage 7B should move or visually nest it under Finder as **Advanced Search Tuning**. |
| Internal route/key `optimizer` | Contributors may expect Colony Planner optimiser logic. | Route renders Search Tuning; Colony Planner optimiser lives in system-detail simulation preview files. | Medium | Rename internals in a focused later migration or add compatibility alias comments first. |
| "Rerank results" button | May change Finder list order or future search scoring. | Calls `/api/ratings/rerank` and renders a separate reranked list; Finder results remain unchanged. | Medium | Add "Rerank copy" or "Show tuned order" style copy and show original Finder rank beside tuned rank. |
| Economy preference | May filter systems by economy. | Changes which per-economy score feeds the economy dimension for the supplied IDs. It does not remove nonmatching systems. | High | Rename control to "Economy scoring emphasis" or add inline copy: "scores, does not filter". |
| Weight sliders | May tune persistent app behaviour. | Local UI state sent for one rerank request only. Backend normalizes weights for that response. | Medium | Add short "applies to this rerank only" copy; preserve local state only as UI state. |
| Sum warning | User may think bad sums are rejected. | Backend accepts and normalizes. | Low | Keep warning but phrase as "normalized for this run". |
| Score delta | User may read as change to canonical rating. | Difference between returned temporary reranked score and stored original score. | Medium | Label as "tuned score delta" and show original Finder rank movement. |
| Rationale text | User may think rationale explains the tuned score. | It is the stored ratings rationale from the database, not a recomputed explanation of weight contributions. | Medium | Stage 7B should add a simple contribution breakdown or label it "stored rating rationale". |
| Empty state "Run a Finder search first" | Accurate. | Search Tuning cannot operate without current `search.results`. | Low | Keep. |
| "does not generate colony build plans" | Accurate. | No Colony Planner candidate generation or simulation is called. | Low | Keep, but avoid overusing negative copy once placement makes scope clear. |
| "Finder" | User-facing name for the main search surface. | Search Tuning consumes Finder output but is not visually part of Finder. | Medium | Stage 7B should make this relationship spatially obvious. |

## Naming Recommendation

Recommended user-facing name for Stage 7B: **Advanced Search Tuning**.

Rationale: the feature really is search-result tuning, but it is not the primary search workflow. "Advanced" correctly signals that it is optional, Finder-dependent, and power-user oriented. It also avoids promising persistence, automatic learning, or colony build planning.

Names to preserve internally/backend-side for now:

- `/api/ratings/rerank`
- `RerankRequest`, `RerankResponse`, `RerankWeights`
- database `ratings` terminology

Names to avoid as primary user-facing labels:

- **Finder Rerank**: accurate technically, but "rerank" is a backend/action word and may imply mutation of Finder order.
- **Search Strategy**: implies a broader goal-driven search plan, presets, or multi-step workflow that does not exist yet.
- **Search Priorities**: promising if Stage 7B builds presets, but may imply persistence.
- **Discovery Tuning**: softer but vague.
- **System Finder Tuning**: accurate but clunky.
- **Advanced Ranking**: too generic; could be confused with Colony Planner candidate ranking.
- **Search Lab**: acceptable only if treated as a debug/experimental surface, not the main product label.

Stage 7B should use **Advanced Search Tuning** for the UI section and "tuned order" / "tuned score" for outputs. Keep "rerank" in backend/API and developer docs.

## Relationship to Colony Planner

Search Tuning helps inspect and reorder candidate systems that Finder already found. It may help a user decide which systems to open next, but Colony Planner does not consume Search Tuning output directly. Colony Planner evaluates a specific selected system through Build Plan, Optimiser Candidates, Preview Result, Observed Evidence, Validation, and Review Guidance.

Recommended boundaries:

- **Finder** discovers candidate systems.
- **Advanced Search Tuning** reorders the current Finder candidates for one exploratory pass.
- **Colony Planner** evaluates a specific system and build plan.
- **Observed Evidence / Validation / Review Guidance** compare predictions against user-recorded observations for a specific system/build and remain passive.

Search results should eventually make the handoff clearer: "Open in Colony Planner" or "Inspect in System Detail" can help users move from discovery to evaluation. Search Tuning should not automatically call Colony Planner, mutate candidate ranking, or change validation confidence in Stage 7.

Future/deferred possibility: validation evidence could inform long-term confidence after explicit mechanics review, but not by automatically mutating search ranking. That belongs to a later evidence governance stage, not Stage 7B.

## Structural Findings

| Severity | Area | File(s) | Issue | Recommendation |
|---|---|---|---|---|
| High | Product placement | `frontend-v2/src/components/NavBar.tsx`, `frontend-v2/src/App.tsx` | Search Tuning is a top-level tab even though it depends entirely on current Finder results. | Stage 7B should demote it under Finder or render it as an advanced Finder panel. |
| Medium | Internal terminology | `frontend-v2/src/features/optimizer/`, `frontend-v2/src/hooks/useHashRoute.ts`, `frontend-v2/src/App.tsx` | User-facing label is Search Tuning, but route/folder/hook names remain `optimizer`, colliding with Colony Planner optimiser vocabulary. | Do a focused route-safe rename to `search-tuning` later, or add compatibility comments if route aliases are required. |
| Medium | API-client terminology | `frontend-v2/src/lib/api.ts` | `api.rerank()` and `api.optimiserCandidates()` sit near each other in a broad API file; comments still say "Optimizer / rerank". | In Stage 7B, clarify comments as "Search Tuning rerank" versus "Colony Planner optimiser". Split feature API helpers only if the app already moves that way. |
| Medium | Output explanation | `frontend-v2/src/features/optimizer/OptimizerTab.tsx` | Result rows show reranked score and delta but not original Finder rank or which weight dimensions drove the change. Stored `rationale` can look like tuned-score rationale. | Add original rank, tuned rank movement, and simple contribution labels. Mark stored rationale as such unless backend returns tuned breakdown. |
| Medium | Economy control semantics | `frontend-v2/src/features/optimizer/OptimizerTab.tsx`, `apps/api/src/routers/ratings.py` | "Economy preference" sounds like a filter; backend uses it only as the economy score dimension for supplied IDs. | Rename/copy as "Economy scoring emphasis"; explicitly say it does not filter or search. |
| Medium | Stale historical docs | `docs/colonisation-redesign/COLONISATION_ENGINE_REDESIGN.md` | Section 10.5 documents optional `use_archetype_engine`, `archetype`, and `profile` fields on `/api/ratings/rerank`, but current `RerankRequest` does not implement them. | Do not implement in Stage 7A. Add current contract docs and, later, mark the historical section superseded. |
| Low | Error handling consistency | `apps/api/src/routers/ratings.py`, `apps/api/src/routers/search.py` | Search endpoints wrap failures as problem-details 503; ratings rerank does not. | Stage 7B/7C can add a small problem-details wrapper if needed, without changing scoring semantics. |
| Low | Unknown economy fallback | `apps/api/src/routers/ratings.py`, `apps/api/src/search_economies.py` | Unknown `economy` silently falls back to auto/greatest per-economy scoring. | Decide whether to keep compatibility or reject invalid economy in a later contract-hardening step. |
| Low | Duplicate default weights | `apps/api/src/routers/ratings.py`, `frontend-v2/src/types/api.ts` | Backend and frontend both define v3.1 defaults. They match today but can drift. | Later derive frontend defaults from API metadata or add a thin test/contract note. |
| Low | Adjacent unused archetype rerank | `apps/api/src/routers/archetypes.py`, `apps/api/src/models.py` | `/api/archetypes/rerank` exists but current Search Tuning does not use it. | Document as API-only/adjacent unless Stage 7B deliberately chooses archetype-aware presets. |

No blocker findings were found. The current feature is not unsafe; the main problem is product framing and explanatory depth.

## Test Coverage Findings

| Area | Current coverage | Missing coverage | Recommended tests |
|---|---|---|---|
| `/api/ratings/rerank` shape | `tests/integration/test_phase6_api_coverage.py` checks default response and Extraction economy. | Weight normalization, clamping, missing ratings rows, deterministic sorting, no persistence/non-mutation. | Add focused backend tests with fake rows or a seeded DB fixture for normalized weights and sorted output. |
| Economy score mapping | `tests/test_search_economies_unit.py` covers `ratings_score_column`. | Unknown economy behaviour is implicit. | Add a contract test only if product decides unknown economy should reject rather than fall back. |
| Normal Finder search | Search integration tests cover no fallback, enum normalization, query safety. | Explicit assertion that Search Tuning does not alter `useSearch.results` ordering. | Add a frontend interaction test after Stage 7B UI placement changes. |
| Search Tuning UI copy | `OptimizerTab.test.tsx` checks heading/scope copy and rerank button. | Loading state, API error state, result row rendering, original/tuned rank movement, economy selector payload. | Add after Stage 7B copy/output changes. |
| API helper serialization | No direct test for `api.rerank()` payload shape. | Request serialization and endpoint path. | Add a tiny fetch-mock test if the repo already has API helper tests; otherwise avoid introducing a test harness just for this. |
| Nav route label | No dedicated `NavBar` regression test found. | Regression from "Search Tuning" back to "Optimizer". | Add a lightweight `NavBar` test if Stage 7B keeps a nav entry. |
| Colony Planner boundary | Stage 5/6 tests cover planner passivity and no automatic simulation/optimiser side effects in validation/observed evidence. | No direct test that Search Tuning does not call Colony Planner APIs. | If Stage 7B integrates more closely with Finder/System Detail, add a mock test proving only `/ratings/rerank` is called. |

No optional Stage 7A test was added. Existing tests already cover the most obvious current-label and endpoint smoke cases, and the next valuable tests depend on the Stage 7B UI reframing.

## Recommended Stage 7B Scope

Must do:

- Reframe the feature as **Advanced Search Tuning**.
- Make clear it reranks a copy/subset of current Finder results only.
- Show original Finder rank, tuned rank, and rank movement.
- Clarify "economy preference" as scoring emphasis, not filtering.
- Keep `/api/ratings/rerank` scoring behaviour unchanged.
- Keep Colony Planner, optimiser candidate generation, validation, and observed evidence untouched.
- Add frontend tests for the new copy, source dependence, result rendering, and payload sent to `/ratings/rerank`.

Should do:

- Move Search Tuning under Finder or visually attach it to Finder results.
- Rename frontend feature folder/route from `optimizer` to `search-tuning` with compatibility handling.
- Improve result copy around stored rationale versus tuned-score explanation.
- Add small backend tests for weight normalization and deterministic sorted output.
- Update stale historical rerank documentation in `COLONISATION_ENGINE_REDESIGN.md`.

Could do:

- Add preset weight profiles such as balanced, economy-focused, slot-focused, safety-focused, terraforming-focused.
- Add an "Open in Colony Planner" or "Inspect in System Detail" handoff from tuned rows.
- Add a compact contribution breakdown if backend returns enough fields or frontend can safely label existing components without reimplementing formulas.

Explicitly not now:

- No scoring formula changes.
- No backend search ranking changes.
- No database query redesign.
- No LLM-driven search/rerank.
- No automatic learning from observations.
- No persistence of user tuning.
- No Colony Planner generation/ranking changes.
- No validation-informed ranking mutation.

## Deferred / Future Ideas

- Goal-driven search strategy presets for colony archetypes.
- Search result explanations that say why a system may be promising for a selected goal.
- Better Finder-to-Colony-Planner handoff from result cards and tuned rows.
- Optional archetype-aware search prioritization using existing archetype tables, only after product framing is clear.
- Long-term confidence adjustments from validation evidence after explicit mechanics review, not automatic search ranking mutation.

## Final Recommendation

Keep the feature, but treat it as an advanced Finder tool rather than a top-level workflow. The current implementation is a read-only temporary rerank of supplied Finder result IDs using stored ratings data, so **Advanced Search Tuning** is the best Stage 7B user-facing name. Stage 7B should focus on placement, wording, before/after rank movement, and tests while preserving existing backend search/rerank formulas and keeping Colony Planner boundaries intact.
