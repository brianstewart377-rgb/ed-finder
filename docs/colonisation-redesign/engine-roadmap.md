# ED-Finder Colonisation Engine Roadmap

This roadmap describes the engine honestly: what exists, what is inferred, and
what should wait until better observation data exists.

## Stage 0 - Legacy System Finder

- Raw local and galaxy search.
- `ratings.py` era scoring.
- Generic economy/body/distance scoring.
- Useful for finding candidates, but not a colony-design engine.

## Stage 1 - Archetype Engine

- Economy archetypes.
- Buildability analysis.
- Early purity and contamination concepts.
- Preliminary rationale and recommendation copy.
- Still mostly answered "is this system good?"

## Stage 2 - Deterministic Colony Planning

Current branch state.

- Facility catalogue from community-observed DaftMav structure data.
- Simulation Preview.
- Recommended Builds.
- Mega Guide body rules.
- Mixed-economy inheritance.
- Topology graph with local-body grouping.
- Strong, weak, pass-through, and converted-port modelling.
- CP build-order timeline.
- Economy stack scoring.
- Service unlock modelling.
- Regional positioning.

Stage 2 answers: "what does this selected plan produce under the current
deterministic rule model?"

## Stage 3 - Explainability And Trust Layer

Current hardening target.

- Mechanics package for central constants.
- Mechanics version and source tracking.
- Confidence signals.
- Observed vs predicted language.
- Structured mechanics trace.
- Transparent recommendation ranking.
- Debuggable score breakdowns.

Stage 3 answers: "what rule produced this answer, what data supported it, and
how confident is ED-Finder?"

## Stage 4 - Topology/Economy Engine V2

Stage 4 begins with Stage 4A, an additive per-port economy propagation layer that keeps the Stage 2/3 deterministic preview and trust layer intact.

- Stage 4A per-Main-Port economy states.
- Stage 4A influence ledger covering body inheritance, direct facility influence, strong links, weak links, pass-through effects, and converted ports.
- Stage 4B per-Main-Port service states.
- Stage 4B service unlock ledger covering port defaults, system unlocks, strong-link unlocks, inferred locked requirements, and unknown rules.
- CP sequence repair assistant that reads the existing CP timeline and emits small repair suggestions without changing CP totals or running a full optimiser.
- Stage 4D observed-vs-predicted foundation with observed fact models, comparison helpers, response summary/diffs, and informational confidence-impact signals.
- Stage 4E simulation engine consolidation that keeps Simulation Preview behaviour stable while separating internal prediction state, observation comparison, and public response assembly.
- System-level economy and service compatibility while preserving existing response fields.
- Simulation Preview Port Economy Breakdown, Influence Ledger, Port Service Graph, and Service Unlock Ledger displays.
- Recommended Build card summary for main-port economy and contamination source.
- Mechanics trace events for port-state creation, top-two protection, major influence sources, weak-link contamination, pass-through influence, port-service-state creation, and service unlock decisions.

Remaining Stage 4 work:

- Advanced service unlock qualifier validation.
- Service-aware recommendation scoring after the graph is stable.
- Full build-order optimiser that can search alternatives beyond local CP sequence repairs.
- Journal upload, EDMC import, manual observation entry, and reviewed mechanics confidence upgrades on top of the Stage 4D foundation.
- Advanced contamination modelling.
- Converted-port confidence refinement.
- Local-body cluster strategy.
- Pass-through validation against observed builds.
- Richer visual graph rendering once more observations exist.

## Stage 4E - Simulation Engine Consolidation

Stage 4E is a behaviour-preserving architecture hardening pass. It does not add gameplay mechanics, alter scoring weights, change CP formulas, or redesign the frontend. Its purpose is to make the deterministic simulation engine easier to maintain before Stage 5 starts calling it repeatedly from candidate-generation code.

The preview pipeline is now documented as a sequence of internal stages: user placements are resolved into catalogue-backed placement instances, core prediction state is built from CP, topology, economy, and service calculations, explainability layers are attached, observations are compared against an internal prediction snapshot, and a dedicated response assembly module converts the internal state into the public API response. This keeps the public response contract stable while preventing the response dictionary from becoming internal engine state.

| Stage 4E Concern | Hardening Outcome |
|---|---|
| Internal prediction state vs public response | Internal dataclasses represent resolved placements, economy/service state, complete prediction state, and observation comparison state before public serialization. |
| Response assembly | Public Simulation Preview fields are centralised in a response assembly module so compatibility is easier to audit. |
| Placement instance identity | Resolved placements carry deterministic instance IDs in the form `build_order:index:facility_template_id:local_body_id_or_none`, allowing duplicate same-template placements to be distinguished internally without changing public `facility_id` fields. |
| Contract testing | A broad simulation contract test validates the Stage 4 response field set, Pydantic compatibility, mechanics trace sections, predicted-only observation summary, and absence of internal-only slot fields. |
| Stage 5 dependency | The optimiser can later call the preview pipeline without needing to understand a monolithic API-response-building function. |

## Stage 5 - Optimiser V1

Generate candidate plans rather than only previewing selected plans. This Stage 5 colony optimiser is separate from **Search Tuning**, the legacy Finder-result reranking tool that only adjusts weights and reorders the current Finder search results via the ratings rerank endpoint.

Stage 5.9C reframes the frontend planning surface as **Colony Planner**, with visible **Build Plan**, **Optimiser Candidates**, and **Preview Result** sections. Simulation Preview is now treated as the explicit preview action/result inside that workspace. Optimiser candidates show the generation parameters they were created with and warn when target archetype, max candidate count, or estimated-data controls have changed since generation.

Stage 5.9D keeps that UX intact while reducing `SimulationPreview.tsx` from an all-in-one state/layout component into a composition component. Plan ownership now lives in `hooks/useSimulationPreviewPlan.ts`, explicit preview execution lives in `hooks/useSimulationPreviewRun.ts`, and Colony Planner header, Build Plan, section labels, and Preview Result rendering live in focused presentational components. No backend optimiser generation, ranking, scoring, CP/economy/service mechanics, Search Tuning behaviour, route structure, or Stage 6 validation work changed.

Stage 5.9E hardens the full Colony Planner workflow before Stage 6. Generated candidates remain visible when target archetype, maximum candidate count, or estimated-data settings become stale, but the UI shows generated/current values and requires explicit older-candidate confirmation before loading stale candidates. Preview Result now marks an existing result stale when the exact preview fingerprint changes after an explicit run; that fingerprint includes system ID, target archetype, and resequenced placements. No automatic preview rerun is introduced.

Future Search Tuning work should add clearer presets, before/after rank movement, and better explanations, but that rework is separate from the Stage 5 colony optimiser and is not implemented in this pass.

## Stage 6 - Observed vs Predicted Validation

Stage 6A begins the validation layer as a backend-only observed facts foundation. It adds a passive `observed_facts` persistence contract, manual/test-fixture source support, CRUD API endpoints, and descriptive summaries. Observations record evidence; they do not mutate predictions, optimiser generation, ranking, Simulation Preview scoring, or CP/economy/service/buildability mechanics.

| Stage 6A Concern | Current Outcome |
|---|---|
| Backend data shelf | `apps/api/src/observations/` defines explicit observed fact enums, persisted fact records, request/response models, store helpers, and descriptive summary counts. |
| API surface | `POST/GET/PATCH/DELETE /api/observations/facts` supports create, list/filter by system, get, update, and hard-delete for Stage 6A. |
| Persistence | `sql/018_observed_facts_stage6a.sql` extends the existing `observed_facts` table with stable observation IDs, typed fact/status/source fields, JSON value columns, fingerprints, tags, metadata, and useful indexes. It also relaxes `subject_id` to nullable so system/build-level notes can be persisted. |
| Sources | The Stage 6A public API accepts `manual` and `test_fixture` only. `imported` and `inferred` are reserved enum values for later ingestion/comparison stages and are rejected by Stage 6A validation. |
| List summary | `ObservedFactListResponse.summary` describes the full filtered result set (matching `total`), not just the paginated page. The store provides `summarise_observed_facts_for_filter` for this; it shares the list query's filter clause so the two always agree. |
| Nullable subject_id | `subject_id` may be null for system-level or build-level notes; the store preserves `None` end-to-end without coercing to an empty string. |
| Legacy compatibility | Stage 4D columns (`area`, `source_type`, `observed_value`, `facility_id`, `body_id`) remain populated by Stage 6A writes alongside the new columns, so existing Stage 4D comparison/trace code keeps working until a later normalisation migration. The mapping is documented in `apps/api/src/observations/store.py` and `sql/018_observed_facts_stage6a.sql`. |
| Boundaries | No frontend UI, EDMC/journal ingestion, account persistence, auto-learning, mechanics mutation, or predicted-vs-observed comparison is implemented in Stage 6A. A static safety test asserts the optimiser, simulation, mechanics, and their routers do not import the observation store. |

Stage 6B should add manual observation entry UI on top of this API. Stage 6C should add the predicted-vs-observed comparison engine that interprets stored observations against simulation output. Until those stages exist, observed facts are a trustworthy evidence shelf only.

### Stage 6B - Manual Observed Evidence UI

Stage 6B adds the frontend Observed Evidence panel that lets a user manually record, list, update, and delete observed evidence for the current system. The user-facing label is **Observed Evidence**; the backend wire vocabulary remains observed facts. The panel lives inside Colony Planner, after Preview Result, and is exposed as a fourth section label alongside Build Plan, Optimiser Candidates, and Preview Result.

| Stage 6B Concern | Current Outcome |
|---|---|
| Frontend types | `frontend-v2/src/types/api.ts` adds `ObservationSource`, `ObservedFactType`, `ObservedSubjectType`, `ObservedStatus`, `ObservedConfidence`, `ObservedFact`, `ObservedFactCreateRequest`, `ObservedFactUpdateRequest`, `ObservationFactSummary`, `ObservedFactListResponse`, `ObservedFactDeleteResponse`, and `ListObservedFactsParams` matching the Stage 6A wire contract. |
| API client | `frontend-v2/src/lib/api.ts` adds `listObservedFacts`, `createObservedFact`, `updateObservedFact`, and `deleteObservedFact` helpers calling the Stage 6A endpoints. |
| Panel | `frontend-v2/src/features/system-detail/simulation-preview/observations/ObservedEvidencePanel.tsx` lists facts for the current `system_id64`, renders create/edit/delete UI, surfaces backend summary counts, and shows loading/error/empty states with a retry control. |
| Create flow | `ObservedEvidenceForm.tsx` lets users record manual evidence with required Evidence type, Status, Confidence, and Notes fields. Conditional inputs for `service_id`, `economy`, `facility_template_id`, and observed value appear per fact type. Advanced fields (local body, target archetype, expected value, tags) are collapsible. The form hardcodes `source: 'manual'` — imported and inferred remain reserved for later stages. |
| Update flow | Each card has an inline Edit form for status, confidence, notes, tags, and observed/expected values. Cancel preserves the original card; save calls `PATCH /api/observations/facts/{id}` and invalidates the list query. |
| Delete flow | Delete requires explicit confirmation via a separate confirm panel with the exact non-mutation copy ("This removes the manually recorded evidence only. It does not change predictions, builds, or in-game state."). Cancel preserves the record. |
| Filters | Fact-type and status filters call the backend list endpoint as query params. Confidence filter is applied client-side to the returned facts. A Clear filters control is exposed when at least one filter is active. |
| Passivity copy | The panel renders the Stage 6B passive-evidence notice near the top: *"Observed Evidence is passive. It does not change Simulation Preview scoring, optimiser ranking, or generated candidates."* No final-verdict or automatic mechanics-change wording is used. |
| Integration | `SimulationPreview.tsx` renders `ObservedEvidencePanel` after `PreviewResultSection`, passes `system.id64` and `plan.targetArchetype`, and otherwise keeps the existing simulation/optimiser request payloads unchanged. `ColonyPlannerSectionNav.tsx` adds a neutral Observed Evidence section label. |
| Tests | `ObservedEvidencePanel.test.tsx` covers passive copy, list/empty/loading/error states with retry, manual create for service/economy/facility/note evidence, 422 backend error display, client-side validation, edit save and cancel, delete confirm and cancel, fact-type/status filter calls, hidden imported/inferred sources, and absence of simulate/optimiser side effects during observation flows. `SimulationPreview.optimiser.test.tsx` adds Observed Evidence panel render checks and confirms the optimiser/simulation request paths remain unchanged. |
| Boundaries | Stage 6B records evidence only. It does not classify predictions as correct/incorrect, run any comparison engine, change simulation/optimiser request payloads, alter scoring, ingest EDMC or journals, persist accounts/builds, or feed evidence back into mechanics. Stage 6C will add predicted-vs-observed comparison; Stage 6D will render validation results. |

Stage 6C remains responsible for the predicted-vs-observed comparison engine. Stage 6D will render the validation/comparison results. Imported and inferred sources remain reserved for later ingestion stages; Stage 6B never exposes them in any create-form option.

### Stage 6C - Predicted vs Observed Comparison Engine

Stage 6C adds the deterministic predicted-vs-observed comparison engine that compares a Simulation Preview prediction against persisted Stage 6A observed facts and emits a structured per-row comparison plus a top-level summary. Stage 6C is the engine; Stage 6D will render its output in the validation UI.

Core principle: **prediction is what ED-Finder thinks should happen, observation is what a user actually saw, comparison is a structured diff between the two.** Stage 6C compares but does not change predictions, scoring, ranking, candidate generation, or Simulation Preview output. One observation is evidence to compare, not a mechanics verdict.

| Stage 6C Concern | Current Outcome |
|---|---|
| Engine module | `apps/api/src/observations/comparison_engine.py` exposes a single pure entry point `compare_prediction_to_observations(*, system_id64, target_archetype, prediction, observed_facts, now=None)` returning a `PredictionObservationComparisonResult`. Pure and deterministic: no DB access, no network access, no mutation of inputs; the only time-dependent field (`generated_at`) is injectable. |
| Engine models | `apps/api/src/observations/comparison_models.py` defines the Stage 6C dataclasses and enums (`ComparisonStatus`, `ComparisonSeverity`, `ComparisonConfidence`, `ComparisonOverallStatus`, `ComparisonConfidenceImpact`, `ComparisonArea`, `ObservationEvidenceMatch`, `PredictionObservationComparison`, `PredictionObservationComparisonSummary`, `PredictionObservationComparisonResult`) plus JSON-safe serialisation helpers. These are intentionally separate from the legacy Stage 4D comparison models so the Stage 4D pipeline keeps running unchanged. |
| API endpoint | `POST /api/observations/compare` runs the engine. Mode A (no `observed_facts` in request): backend loads persisted facts for `system_id64` (and optional `target_archetype`) from the Stage 6A store up to `fact_load_limit`. Mode B (`observed_facts` provided): backend uses the supplied list verbatim and does not query the database for facts. |
| API models | `apps/api/src/observations/api_models.py` adds `PredictionObservationCompareRequest`, `PredictionObservationCompareResponse`, `PredictionObservationComparisonResponse`, `PredictionObservationComparisonSummaryResponse`, `ObservationEvidenceMatchResponse`, and `ObservedFactInput` for the compare endpoint. Validators reject `system_id64 <= 0` and non-object predictions (lists/strings/numbers). |
| Matching rules | Service comparisons read `services` plus the active/locked/unknown buckets inside `port_service_states`; economy comparisons combine `economy_composition` (weight > 0) and `economy_order`; CP comparisons accept a numeric scalar (compared against `yellow_cp_final`) or a dict (overlapping keys only). Facility state, build outcome, and notes are observation-driven, conservative, and do not auto-classify. `prediction_match` / `prediction_mismatch` only elevate to confirmed/contradicted when the referenced subject exists in the current prediction; otherwise they stay observed_only/unverified. |
| Status rules | `confirmed` / `contradicted` / `predicted_only` / `observed_only` / `unknown` / `unverified`. Observations with status `unknown` or `unverified` never confirm or contradict — they surface as `unverified`. Notes are always `observed_only` / `info`. |
| Severity clamp | Contradiction severity is clamped by observation confidence: low-confidence observations cannot produce high-severity contradictions, medium-confidence observations clamp `high` base severities down to `medium`. |
| Summary rules | `summary.status`: `no_observations` / `confirmed` / `mixed` / `needs_review` / `insufficient_evidence`. `summary.confidence_impact`: `none` / `strengthened` / `weakened` / `mixed` / `insufficient_evidence`. Both are UI hints only; Stage 6C does not plumb them back into scoring or ranking. |
| Tests | `tests/test_stage6c_comparison.py` covers engine matching/status/severity/summary rules, input non-mutation, JSON round-trip, deterministic `generated_at` injection, Mode A vs Mode B endpoint behaviour, validation errors for negative/zero `system_id64` and non-object predictions, and a runtime passivity check that simulation/optimiser modules are not imported during a compare call. The legacy `tests/test_observation_comparison.py` (Stage 4D) is left untouched. |
| Boundaries | Stage 6C is comparison-only. It does not change predictions, alter optimiser candidate generation, alter optimiser ranking, change Simulation Preview scoring, mutate CP/economy/service/buildability mechanics, ingest EDMC or journals, or rewrite predictions. A static passivity test asserts simulation/optimiser/ranking source files do not import `observations.comparison_engine` or `observations.store`. Stage 6D renders Stage 6C's output in the Simulation Preview UI. |

### Stage 6D - Validation Display in Colony Planner

Stage 6D renders the Stage 6C `POST /api/observations/compare` response inside the Colony Planner. It is a **frontend integration stage**: the engine and the endpoint are unchanged. Validation is rendered as an in-page section inside Colony Planner, **after Observed Evidence**. No popout, modal, or top-level app tab is introduced. The Colony Planner section order is now: Build Plan → Optimiser Candidates → Preview Result → Observed Evidence → Validation.

Core principle: **prediction is what ED-Finder thinks should happen, observation is what a user actually saw, validation displays the comparison between them.** Stage 6D shows; it does not change predictions, optimiser candidates, optimiser ranking, scoring, mechanics, persisted observations, or in-game state. Contradictions are labelled **Needs review** because one observation is evidence to compare, not a mechanics verdict. Missing observations do not mean a prediction is incorrect; they are reported as `predicted_only` with conservative copy.

| Stage 6D Concern | Current Outcome |
|---|---|
| Frontend types | `frontend-v2/src/types/api.ts` adds `ComparisonStatus`, `ComparisonSeverity`, `ComparisonOverallStatus`, `ComparisonConfidenceImpact`, `ObservationEvidenceMatch`, `PredictionObservationComparison`, `PredictionObservationComparisonSummary`, `PredictionObservationCompareRequest`, and `PredictionObservationCompareResponse` matching the Stage 6C wire contract. |
| API helper | `frontend-v2/src/lib/api.ts` adds `comparePredictionToObservations(request)` → `POST /api/observations/compare`. The helper is narrow: it never calls `simulateBuild` or `fetchOptimiserCandidates`. |
| Validation module | `frontend-v2/src/features/system-detail/simulation-preview/validation/` ships `ValidationPanel`, `ValidationSummary`, `ValidationComparisonList`, `ValidationComparisonCard`, `validationLabels`, and `validationUtils` plus tests. Components are small and focused; no Stage 6C rules are re-implemented in React. The panel only renders backend comparison output. |
| Panel behaviour | `ValidationPanel` receives `systemId64`, `targetArchetype`, `previewResult`, and `isPreviewResultStale`. If `previewResult` is null, the panel shows the no-preview empty state and does NOT call the compare API. If `previewResult` exists, the panel calls `/api/observations/compare` in Mode A (no `observed_facts` in the request) with the current preview result as `prediction`. The query key includes `systemId64`, `targetArchetype`, and a stable preview-result fingerprint so a new preview run triggers a fresh comparison and an unchanged preview reuses the cached result. |
| Stale handling | When `isPreviewResultStale` is true, the panel renders the stale warning *"Preview result is stale. The Build Plan has changed since this preview was run. Run Preview again before relying on validation."* Stage 6D never auto-runs Simulation Preview and never mutates the build plan. |
| Refresh | A manual **Refresh validation** button calls `refetch()` on the compare query. The Observed Evidence panel additionally invalidates `observation-compare` queries on create/update/delete so new evidence is reflected on the next refresh. |
| Summary rendering | `ValidationSummary` displays overall status (`no_observations`/`confirmed`/`mixed`/`needs_review`/`insufficient_evidence`), confidence impact (`none`/`strengthened`/`weakened`/`mixed`/`insufficient_evidence`), observed-facts count, compared-predictions count, and per-bucket counts using the conservative labels listed in `validationLabels.ts`. The backend `summary` text is rendered verbatim. |
| Comparison rendering | `ValidationComparisonList` renders one `ValidationComparisonCard` per comparison row with a status filter (severity filter is optional and not in scope). Each card shows status, severity, confidence, area, subject type, subject id, predicted value, observed value, reason, recommended action (when present), evidence count, and per-evidence details (`observation_id`, `fact_type`, `status`, `confidence`, `observed_value`, `expected_value`, `notes`). Empty state and filter-empty state copy stay neutral. |
| Conservative copy | `contradicted` rows render as **Needs review**; `predicted_only` and `observed_only` rows use neutral wording that describes the asymmetry without implying correctness. The advisory top banner makes the boundary explicit. |
| Tests | `frontend-v2/src/features/system-detail/simulation-preview/validation/ValidationPanel.test.tsx` covers advisory copy, no-preview empty state, compare API call shape, summary rendering, per-status labels (confirmed/contradicted/predicted_only/observed_only/unknown/unverified), evidence detail rendering, status filtering, loading state, error/retry, stale warning, refresh, and passivity (no `simulateBuild`, no `fetchOptimiserCandidates`, no observed-fact mutations). `SimulationPreview.optimiser.test.tsx` additionally asserts that Validation renders inside Colony Planner after Observed Evidence and that the compare API is called with the current preview result once a preview has been run. |
| Boundaries | Stage 6D is a display layer only. It does not change predictions, simulation scoring, optimiser candidate generation, optimiser ranking, CP/economy/service/buildability mechanics, persisted observed evidence, or in-game state. Validation rendering never auto-runs Simulation Preview. Stage 6E will introduce the confidence/rule mutation review loop on top of this display; Stage 6D defers that work. A future expansion may move large comparison sets into a drawer or popout, but the default placement remains in-page. |

### Stage 5A - Deterministic Candidate Generation

Stage 5A is implemented as a bounded backend candidate generator rather than a full search optimiser. The hardened implementation lives in `apps/api/src/optimiser/`, with internal dataclasses, central archetype metadata, catalogue-driven facility selection, placement-fingerprint dedupe, and lightweight preview-summary extraction separated from the older recommendations package.

| Stage 5A Concern | Current Outcome |
|---|---|
| Candidate endpoint | `POST /api/optimiser/candidates` delegates to `optimiser.candidate_generator.generate_candidates`. |
| Request contract | `system_id64`, `target_archetype`, `max_candidates`, `preferred_body_ids`, `allow_estimated_data`, and `run_preview`; `target_archetype_key` remains accepted as compatibility input. |
| Response contract | `system_id64`, `target_archetype`, `candidate_count`, `candidates`, `warnings`, and `assumptions`. Candidate fields use `candidate_id`, `target_archetype`, `strategy`, `placements`, `rationale`, `warnings`, `assumptions`, `tags`, and lightweight `preview_summary`. |
| Generation strategy | Bounded deterministic strategies are `balanced`, `pure`, `services_aware`, `low_cp`, and `flexible_multirole`. |
| Preview integration | `run_preview` controls whether generated placements are previewed; preview summaries are lightweight only, and preview failures are captured per candidate without aborting generation. |
| Guardrails | Unknown archetypes fall back to `flexible_multirole` with a warning, duplicate ordered placement fingerprints are deduped, and generated placements use catalogue-present facility IDs only. Dedupe is order-sensitive because build order affects CP timing. |
| Tests | `tests/test_optimiser.py` covers required Stage 5A behaviours including max-candidate bounds, deterministic IDs, build-order sequencing, primary-port limits, dedupe, fallback, no-body-data generation, preferred bodies, preview modes, preview failure isolation, conversion helpers, and endpoint response shape. |

### Stage 5B - Candidate Ranking and Explanation

Stage 5B ranks existing Stage 5A candidates when clients request `include_ranking=true`. It is deterministic and heuristic, using only lightweight preview summaries, candidate warnings, assumptions, candidate metadata, CP risk, confidence, and target alignment. Ranking output is a top-level object that references candidates by `candidate_id`; it does not mutate candidates, add rank fields to candidates, duplicate full candidate payloads, call Simulation Preview, or expand the candidate search space.

| Stage 5B Concern | Current Outcome |
|---|---|
| Ranking module | `optimiser.ranker.rank_candidates` owns ranking logic; the router remains a thin orchestration layer. |
| Request contract | `include_ranking=false` preserves Stage 5A candidate shape and ordering; `include_ranking=true` adds top-level `ranking`. |
| Ranking response | Ranked entries include `candidate_id`, `rank`, `rank_score`, `rank_tier`, and structured `rank_breakdown`. |
| Guardrails | Missing preview summaries are handled with an explanatory reason; candidate warnings and negative CP pressure reduce rank without crashing. |
| Tests | `tests/test_optimiser.py` covers deterministic ranking, penalties, serialization, non-mutation, and endpoint compatibility. |

### Stage 5C - Read-only Candidate Comparison UI

Stage 5C adds a frontend comparison panel under `simulation-preview/optimiser/`. It deliberately fetches candidates with `run_preview=true` and `include_ranking=true`, displays ranked cards, rationale, warnings, assumptions, placements, and structured ranking breakdowns, and keeps candidate comparison read-only. It does not apply candidates to the current build editor or mutate Simulation Preview state.

| Stage 5C Concern | Current Outcome |
|---|---|
| UI placement | `OptimiserCandidatePanel` is rendered as a sibling panel inside Simulation Preview rather than folded into the existing result sections. |
| Candidate display | Cards show rank, tier, score, strategy, preview summary signals, warning count, and CP risk. |
| Details display | Selected candidate details show rationale, warnings, assumptions, placements, and ranking breakdown including `alignment_component`. |
| Read-only guardrail | Candidate selection and comparison remain non-destructive; Stage 5D owns the deliberate load-into-preview action. |

### Stage 5D - Load Optimiser Candidate into Preview

Stage 5D lets the user deliberately load a selected optimiser candidate into the editable Simulation Preview plan. Loading copies candidate placements, updates the target archetype, clears stale preview output, and shows an optimiser-candidate origin marker. If the user edits, moves, removes, or adds placements after loading, the marker changes to show that the preview plan started from that optimiser candidate but has since been edited. Loading remains local preview-only: it does not commit anything in-game, save a build, auto-run Simulation Preview, or alter backend generation, ranking, scoring, CP, economy, or service mechanics.

| Stage 5D Concern | Current Outcome |
|---|---|
| Load action | Candidate details expose `Load into preview` only when Simulation Preview passes an explicit load callback; otherwise the panel keeps the Stage 5C read-only copy. |
| Conversion | Candidate placements are copied into preview placements, resequenced, and defensively normalised to one primary port. |
| Overwrite protection | Non-empty preview plans require confirmation before replacement; cancel preserves the current plan. |
| Preview execution | Loading a candidate clears stale result/error state but does not call `simulateBuild`; the existing Run Preview button remains the execution path. |

### Stage 5E - Optimiser Comparison Engine

Stage 5E adds a deterministic frontend comparison engine under `simulation-preview/optimiser/comparison/`. The engine compares any two compatible build-plan sources, including the current editable preview plan and optimiser candidates, without running simulations or changing backend mechanics. It produces serialisable output for facility additions/removals, count deltas, body/order/primary-port changes, target-archetype changes, lightweight preview-summary deltas, ranking deltas, warning and assumption changes, risk direction, tradeoff summaries, and a conservative recommendation verdict.

| Stage 5E Concern | Current Outcome |
|---|---|
| Engine boundary | Comparison logic is isolated in `comparisonEngine.ts`, with serialisable types and pure formatters for Stage 5F. |
| Input sources | Helpers create copied comparison sources from optimiser candidates and current preview placements without mutating inputs. |
| Scope guardrail | Stage 5E does not build a full comparison UI, run Simulation Preview, save builds, or alter backend generation/ranking/scoring mechanics. |

### Stage 5F - Optimiser Comparison UI and Final Stage 5 Hardening

Stage 5F renders the Stage 5E comparison output in a contained, show/hide comparison panel inside the optimiser details pane. The primary path compares the latest current editable Simulation Preview plan against the selected optimiser candidate, showing the conservative verdict, deterministic tradeoff summary, target-archetype change, facility and placement deltas, preview-summary deltas, ranking availability, warning/assumption changes, and risk direction. The comparison is advisory and preview-only: it does not run Simulation Preview, save a build, commit anything in-game, or alter backend mechanics.

| Stage 5F Concern | Current Outcome |
|---|---|
| Rendering boundary | UI consumes `compareBuildSources(...)` output rather than reimplementing comparison logic in React components. |
| Candidate-vs-current | Selected candidates compare against the current editable preview placements and target archetype. |
| Candidate-vs-candidate | Engine support exists from Stage 5E; the selector UI remains explicitly deferred to avoid clutter. |
| Safety | Comparison rendering is read-only, uses the latest editor props, and does not affect the Stage 5D load/confirmation flow. |

Remaining optimiser work:

- Deeper constraints by complexity, confidence, CP pressure, and player preferences.
- Explicit comparison of rejected alternatives.
- Stage 6 observed/predicted validation remains a separate later phase.

## Stage 6 - Community Observation Loop

Move more mechanics from inferred to observed.

- Journal uploads.
- Observed slot confirmation.
- Observed service unlocks.
- Observed build outcomes.
- Correction of inferred mechanics.
- Player-submitted validation.

## Stage 7 - Regional Expansion Strategy

Expand beyond one-system planning.

- Expansion corridors.
- Frontier chain planning.
- Regional competition.
- Strategic bridge systems.
- Cluster-level recommendations.
- Best next colony after this one.

## Stage 8 - Full Colony Planning Platform

Longer-term destination.

- Multi-system expansion plans.
- Player goals and preferences.
- Build sequence optimiser.
- Logistics planning.
- Commodity hauling requirements.
- Construction progress tracking.

## Current Guardrail

Do not add unsupported gameplay mechanics until the deterministic preview remains easy to test, explain, and debug. Stage 4 work should remain conservative: it explains existing topology, economy, service, CP, and observation-comparison rules while labelling inferred behaviour rather than inventing new mechanics.

### Stage 6E - Validation Review Guidance

Stage 6E adds a structured review layer on top of Stage 6C comparison output and Stage 6D rendering. The review layer answers: "Based on the validation results, what should I review next?" It is advisory and passive.

| Stage 6E Concern | Current Outcome |
| --- | --- |
| Engine models | `apps/api/src/observations/review_models.py` defines `ValidationReviewSignal`, `ValidationReviewSummary`, `ValidationReviewResult`, review statuses, review areas, evidence strength, and JSON-safe serialisation helpers. |
| Engine module | `apps/api/src/observations/review_engine.py` exposes `build_validation_review(comparison_result=...)`. It consumes a Stage 6C `PredictionObservationComparisonResult`, uses its `generated_at`, and performs no DB access, API calls, simulation calls, optimiser calls, or mutation. |
| API endpoint | `POST /api/observations/review` mirrors the Stage 6C compare request, loads facts with the same comparison semantics, runs Stage 6C comparison, then runs Stage 6E review guidance. |
| Frontend | `ValidationPanel` calls the review endpoint alongside compare when a preview result exists and renders `ValidationReviewPanel` below the comparison summary and above comparison rows. Review failure is isolated so comparison rows still render. |
| Invalidation | Observed evidence create/update/delete invalidates both `observation-compare` and `observation-review` query namespaces. |
| Rules | Contradicted service rows point to `service_rules`; economy rows to `economy_rules`; CP rows to `cp_rules`; facility observed-only rows to `facility_rules`; low-confidence contradictions produce `monitor`/`evidence_quality`; missing evidence produces `insufficient_evidence`; high-priority review wins the top-line summary over mixed evidence while still emitting a secondary mixed-evidence signal. |
| Boundaries | Stage 6E does not rewrite predictions, mutate rule weights, change confidence values, alter scoring, alter optimiser generation/ranking, change CP/economy/service/buildability mechanics, ingest EDMC/journals, or create an adaptive mechanics system. Low-confidence evidence cannot produce high-priority review. Contradictions are "may need review", not final mechanics verdicts. |

The review implementation is split under `apps/api/src/observations/review/`: `engine.py` orchestrates, `rules.py` selects deterministic signals, `signals.py` constructs signal objects, `summary.py` owns top-line status precedence, `areas.py` maps comparison areas to review areas, `severity.py` owns severity/confidence helpers, and `shared.py` owns common buckets. The legacy `observations.review_engine` module remains a thin compatibility import.

Stage 6F will harden the Stage 6 workflow around robustness, ergonomics, and contract edges. EDMC/journal ingestion remains unimplemented and out of scope for Stage 6E.

## Stage 7A - Search Tuning / Finder Rerank Forensic Review

Stage 7A is the map-before-the-march review for the legacy Search Tuning / Finder-result rerank surface. It documents what the current feature actually does, where it is implemented, what endpoints and data it uses, how it differs from normal Finder search and Colony Planner, and what should happen next.

Current Stage 7A status:

- Search Tuning is a read-only rerank of the current Finder result IDs through `POST /api/ratings/rerank`.
- It does not mutate ratings, persist tuning preferences, change `/api/local/search` ordering, generate colony build plans, call Colony Planner optimiser candidates, or consume Observed Evidence / Validation output.
- The current user-facing copy is mostly accurate, but the top-level placement and internal `optimizer` naming still make the feature look more central than it is.
- The recommended Stage 7B user-facing framing is **Advanced Search Tuning**: an advanced Finder tool that shows a tuned order, original rank, and rank movement for the current result set.
- Stage 7B should implement UX/reframing and focused tests based on `docs/colonisation-redesign/search-tuning-forensic-review.md`; it should not change scoring formulas, backend search ranking, Colony Planner logic, validation logic, or observed-evidence passivity.

## Stage 7B - Advanced Search Tuning UX Reframe

Stage 7B reframes the existing Search Tuning surface as **Advanced Search Tuning**. It remains a temporary re-prioritisation of the current Finder result IDs through `POST /api/ratings/rerank`; it does not run a new search, persist preferences, alter normal `/api/local/search` ordering, alter Colony Planner, or use Observed Evidence / Validation output.

Current Stage 7B status:

- The visible nav/page label is Advanced Search Tuning. `#search-tuning` is the preferred route alias, while legacy `#optimizer` remains compatible.
- The UI explains that it uses current Finder results, reranks a copy, leaves the original Finder results unchanged, and does not save preferences or change Colony Planner.
- Economy selection is labelled as scoring emphasis rather than a filter, with explicit helper copy that systems are not filtered out.
- Slider copy says weights apply only to the current tuning run and are normalised for the temporary tuned score.
- Result rows show original Finder rank, tuned rank, movement up/down/unchanged, temporary tuned score, original stored score, and stored rating rationale.
- Original Finder rank is snapshotted when the tuning run starts; movement labels use that snapshot, not whatever Finder results are live later.
- `/api/ratings/rerank`, `RerankRequest`, and `RerankResponse` remain backend/internal terminology. Stage 7C resolves the deferred frontend `optimizer` naming debt; later follow-ups may add presets or deeper contribution explanations.

## Stage 7C - Advanced Search Tuning Internal Rename

Stage 7C removes the Stage 7B frontend compatibility debt around the old `optimizer` naming. The feature folder is now `frontend-v2/src/features/search-tuning/`, the tab component is `AdvancedSearchTuningTab`, the hook is `useSearchTuning`, and the state/snapshot types use Search Tuning names.

Current Stage 7C status:

- `#search-tuning` is the preferred route.
- Legacy `#optimizer` direct links still work and normalize to the `search-tuning` route internally.
- Test IDs for this feature use `search-tuning-*`.
- Backend `/api/ratings/rerank`, `RerankRequest`, `RerankResponse`, and `RerankWeights` remain unchanged.
- No backend scoring, normal search ordering, Colony Planner, Stage 5 optimiser, or Stage 6 validation/review behaviour changed.

## Stage 7D - Advanced Search Tuning Explanation + Handoff

Stage 7D makes tuned rows more understandable and easier to inspect without changing search or planner behaviour. `/api/ratings/rerank` now returns additive explanation fields on each row: pre-confidence weighted `contributions` and stored/raw `signals`. The existing `reranked_score` formula and sorting remain unchanged.

Current Stage 7D status:

- Tuned result rows show a deterministic "Why this tuned position?" explanation based on stored rating signals and selected weights.
- Rows identify top contributors and weaker/held-back signals using conservative language.
- Confidence is shown as an adjustment note when present; contribution values are documented as pre-confidence.
- Rows provide explicit "Open system detail" and "Evaluate in Colony Planner" actions.
- The handoff opens system detail only. It does not auto-run Simulation Preview, generate builds, mutate Colony Planner, persist tuning weights, alter Finder ordering, or use validation/review evidence.
