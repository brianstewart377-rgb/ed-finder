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

Stage 5.9C reframes the frontend planning surface as **Colony Planner**, with visible **Build Plan**, **Suggested Builds**, and **Preview Result** sections. Simulation Preview is now treated as the explicit preview action/result inside that workspace. Suggested-build generation shows the creation parameters and warns when target archetype, max candidate count, or estimated-data controls have changed since generation.
Backend and API names in this area still use `optimiser`/`candidate` wording for compatibility.

Stage 5.9D keeps that UX intact while reducing `SimulationPreview.tsx` from an all-in-one state/layout component into a composition component. Plan ownership now lives in `hooks/useSimulationPreviewPlan.ts`, explicit preview execution lives in `hooks/useSimulationPreviewRun.ts`, and Colony Planner header, Build Plan, section labels, and Preview Result rendering live in focused presentational components. No backend optimiser generation, ranking, scoring, CP/economy/service mechanics, Search Tuning behaviour, route structure, or Stage 6 validation work changed.

Stage 5.9E hardens the full Colony Planner workflow before Stage 6. Generated candidates remain visible when target archetype, maximum candidate count, or estimated-data settings become stale, but the UI shows generated/current values and requires explicit older-candidate confirmation before loading stale candidates. Preview Result now marks an existing result stale when the exact preview fingerprint changes after an explicit run; that fingerprint includes system ID, target archetype, and resequenced placements. No automatic preview rerun is introduced.

Future Search Tuning work should add clearer presets, before/after rank movement, and better explanations, but that rework is separate from the Stage 5 colony optimiser and is not implemented in this pass.

### Stage 8A-8C Colony Planner Guided Workflow

Stage 8A-8C harden the existing embedded Simulation Preview surface into a guided **Colony Planner** workflow without changing backend mechanics. Users can now enter the planner from system detail, Finder result cards, or Advanced Search Tuning; those handoffs scroll/focus the embedded planner only and do not run Preview, generate Suggested Builds, or copy builds automatically.

User-facing planner terms are **Suggested Builds**, **Build Plan**, and **Preview Result**. Backend/API/type names still use optimiser/candidate vocabulary where compatibility requires it. Build Plan feedback shows placement count and Preview not-run/running/stale/current-match state. Preview Result starts with cautious verdict/next-step guidance. Observed Evidence and Validation remain passive later steps for after in-game checking.

Stage 8C also aligns the older Recommended Builds cards with the Colony Planner path: recommended plans open into the editable Build Plan, and service unlock detail points to the Preview Result. Dedicated planner routes/workspaces, saved builds, material/hauling estimates, deeper primary-port/CP strategy logic, EDMC/journal ingestion, and automatic learning remain deferred.

### Stage 16C Central Workspace Decomposition

Stage 16C turns the dedicated Colony Planner centre from a vertically stacked report into a mode-oriented planning surface. The persistent workspace architecture is now:

- left topology rail for navigation/context
- central planner mode for the active task
- right summary rail for project/status/context

The central `SimulationPreview` composition defaults to **Build Plan** mode and exposes local workspace modes for **Suggested Builds**, **Preview**, **Evidence**, and **Validation**. Mode switching is local UI state only. It does not run Simulation Preview, generate Suggested Builds, mutate the Build Plan, validate predictions, import layout data, or save projects.

Stage 16C is not a mechanics rewrite. It keeps CP formulas, scoring, economy/service logic, optimiser generation/ranking, Simulation Preview calculations, Observed Evidence semantics, Validation behaviour, imports, EDMC ingestion, hauling/material workflows, and primary-port truth handling unchanged. Colony-role editing, role badges, durable/backend project persistence, export/import, account sync, and Architect Slot Survey storage remain deferred.

### Stage 16D Role-Hint Foundations

Stage 16D adds read-only colony role hints to the body-grouped Build Plan Layout view. These hints are inferred from existing placement/template/body context and are player-facing planning guidance only.

The first hints cover Main Station Body, Colony Core, Industrial Core, Extraction Body, Tourism/Agriculture, and Support Body candidates. Sparse, unknown, and unassigned bodies render conservative pending/limited hints. Main-station candidate hints appear only when the current plan places a primary, port, or major-tier facility on that body.

Role hints distinguish inferred context from future observed or editable roles. No role editing controls, role persistence, backend role model, automatic role assignment, automatic Preview, automatic Suggested Build generation, primary-port editing, or Architect Slot Survey storage is introduced. CP formulas, scoring, economy/service logic, optimiser generation/ranking, Simulation Preview calculations, Observed Evidence semantics, Validation behaviour, imports, EDMC ingestion, and hauling/material workflows remain unchanged.

### Stage 16E Role-Hint Workspace Integration

Stage 16E moves the read-only role-hint language into the persistent workspace shell so strategic context is visible before opening body detail panels.

- The left topology rail now shows compact inferred role badges and conservative confidence labels on body rows.
- The right summary rail shows a selected-body strategic role card with inferred roles, confidence, short reasoning, conflicts/warnings, and primary-port/Architect context.
- Build Plan, Suggested Builds, Preview, Evidence, and Validation modes each render a small mode-aware role context strip.
- Confidence remains frontend-only and qualitative: `tentative`, `likely`, or `strong`. It is derived from placement concentration, port signals, support/economy mix, topology spread, and metadata quality, with sparse metadata lowering confidence.
- Conflicts are advisory overlap notes, not errors. Examples include industrial/tourism pressure overlap and main-station/support-body signal conflicts.

Stage 16E is still inferred, advisory, and non-authoritative. It does not add editable roles, role persistence, backend role models, optimiser role mechanics, scoring changes, automatic planning, automatic Preview, automatic Suggested Build generation, primary-port editing, Architect Slot Survey storage, or changes to CP/economy/service/validation/observed-evidence semantics. Stage 16F remains responsible for explicit user-declared roles.

### Stage 16F Explicit Declared Roles

Stage 16F adds planner-level user-declared colony roles while preserving the Stage 16E inferred-role boundary. Users can now select a body and declare strategic intent such as Colony Anchor, Main Station Body, Primary Port Body, Industrial Core, Refinery Core, Extraction Support, Tourism / Agriculture Body, Security / Military Body, Support Body, or Expansion Reserve.

Declared roles are stored only in local Colony Projects. Existing projects without a role field load safely with an empty role list. Duplicating or saving a project carries declared roles with the local project snapshot, and unsaved-change detection includes role changes.

The UI keeps role sources separate:

- inferred roles are ED-Finder advisory suggestions from current plan shape
- declared roles are user intent saved with the local project
- observed roles remain evidence-backed facts and are not implemented as editable truth in Stage 16F

Role overlap is allowed and rendered as tradeoff/conflict notes, for example Tourism + Heavy Industrial or Main Station + Expansion Reserve. These warnings do not block planning, auto-correct assignments, remove roles, run Preview, generate Suggested Builds, or change mechanics.

Primary-port handling remains conservative: users may declare intended Primary Port Body, but the UI states that Architect observation is not recorded and the declaration is not primary-port truth. Stage 16F does not add Architect Slot Survey storage, backend/cloud persistence, role-driven optimiser scoring, role-driven Simulation Preview mechanics, automatic role assignment, automatic Preview, or automatic Suggested Build generation.

### Stage 16G Declared-vs-Observed Role Review

Stage 16G adds a frontend-only strategic review layer that compares user-declared strategy against observed colony-state signals derived from existing Observed Evidence facts. It helps answer whether the colony appears to be evolving toward the intended identity without changing predictions or mechanics.

The role review language is intentionally source-separated:

- **Declared Strategy**: local project intent from Stage 16F
- **Observed Colony State**: lightweight role signals derived from manual observed evidence
- **Inferred Planning Signals**: advisory hints from current plan topology and facility/body context

Evidence and Validation modes now show compact role review cards with strategic consistency indicators: Strategy aligned, Partially aligned, Strategy diverging, or Insufficient observed evidence. Review summaries can surface messages such as declared Industrial Core but observed Tourism Focus, observed role not declared, or no observed evidence recorded yet.

Observed role signals are read-only and derived from existing facts such as economy presence, service presence, facility state, tags, and notes. They do not introduce backend role persistence, Architect Slot Survey storage, observed-role editing, automatic declared-role updates, optimiser integration, scoring changes, Simulation Preview changes, or validation semantics changes. Primary-port review remains conservative: observed primary-port context can be mentioned when evidence supports it, but ED-Finder still does not invent authoritative primary-port truth.

### Stage 17B Suggested Builds Rescue

Stage 17B fixes the immediate Suggested Builds failure path while keeping the larger Colony Architect advisor deferred. The `/optimiser/candidates` 500 was caused by the optimiser preview-context query reading `systems.system_id64`; the systems table and system-detail API use `systems.id64`. The optimiser now queries `WHERE id64 = $1`.

The optimiser route logs request payloads, context loading, generation completion, ranking, preview attachment, trivial-candidate filtering, and root-cause exceptions. Unexpected failures return a safe 503 message for the UI while preserving technical detail for logs and the explicit technical-details expander.

Generation is still deterministic and bounded, but Stage 17B raises the usefulness floor:

- non-colony ports are preferred for strategic candidates
- colony-ship/bootstrap-only candidates are not returned as strategic recommendations
- candidates need at least one support placement and a clear purpose tag
- near-duplicate and trivial candidates are filtered before display
- empty useful output tells the player to start manually or provide more system data

New deterministic candidate directions include Main station candidate, Balanced expansion, Industrial/refinery starter, Tourism/agriculture hub starter, Military/security stabiliser, and Support-body plan. A small system-strategy analysis helper records economy pressure, opportunities, weak points, and sparse-data status as the foundation for Stage 17C/17D Guided Colony Strategy Advisor work.

Stage 17B does not change Simulation Preview scoring, CP formulas, economy propagation, service mechanics, Search Tuning, imports, EDMC ingestion, primary-port truth handling, project persistence, automatic Suggested Build generation, automatic Preview, role-aware optimiser mechanics, or LLM planning.

### Stage 17C Colony Planner Usability Rescue

Stage 17C changes the dedicated Colony Planner interaction model from report-first to body-first without changing mechanics.

- The topology rail is now a compact clickable body tree. Rows show body marker, name, one planned-count chip, and tiny primary/warning/sparse markers instead of role badge clusters and long metadata.
- The central workspace now reacts directly to body selection with a body planning surface: selected body title, compact body facts, planned structures on that body, and explicit Add structure here / Review structures actions.
- Build Plan opens in body view by default. List view remains the advanced order/editor surface and all placement mutations still flow through existing explicit Build Plan controls.
- The summary rail is reduced to Project, Plan Health, Current Focus, compact Body Hint, and Evidence/Validation mode buttons.
- User-facing stage/roadmap/internal language remains out of the planner surface.

Suggested Builds remain the Stage 17B deterministic rescue path. Stage 17C keeps friendly error handling, hidden technical details, useful-build filtering, and explicit generate/load behavior. It does not add automatic generation, automatic Preview, role-aware optimiser scoring, LLM planning, topology drag/drop, slot editing, primary-port editing, or persistence changes.

The EDDN ticker now treats production SSE interruptions as reconnecting state instead of rendering the raw transport error. A successful SSE open/message clears the transient error and cleanup clears pending event flush timers.

### Stage 17D Colony Planner Functional UX Reset

Stage 17D is a frontend interaction and routing/display correction pass. It assumes the backend feed and optimiser routes are mostly healthy and focuses on making the planner reflect that reality.

Delivered scope:

- nav/menu overlay behaviour was corrected so planner routes do not start with a blocking menu layer; menu state now closes on navigation, outside click, and Escape
- health status now probes `/api/health` explicitly and shows compact user copy in normal UI instead of raw technical payloads
- EDDN feed UI now uses explicit `connecting/live/reconnecting/offline` states with safe fallback polling from recent events when SSE is unstable
- topology rail was compacted to body-first planning navigation with short body labels and projection highlighting
- central workspace now responds directly to body selection with reliable body-scoped planning actions (`Add structure here`, `Review structures`) via explicit state/props commands instead of DOM query coupling
- Suggested Builds selection now projects body usage context into topology and candidate details while keeping explicit load and explicit preview boundaries
- right summary rail was reduced to compact operational cards: Project, Plan Health, Current Focus, Preview/Suggested

Stage 17D keeps all non-UI mechanics boundaries intact:

- no CP/economy/service/scoring changes
- no Search Tuning changes
- no import/EDMC/persistence model changes
- no automatic Suggested Build generation/loading
- no automatic Preview execution

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

Stage 6B adds the frontend Observed Evidence panel that lets a user manually record, list, update, and delete observed evidence for the current system. The user-facing label is **Observed Evidence**; the backend wire vocabulary remains observed facts. The panel lives inside Colony Planner, after Preview Result, and is exposed as a fourth section label alongside Build Plan, Suggested Builds, and Preview Result.

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

Stage 6D renders the Stage 6C `POST /api/observations/compare` response inside the Colony Planner. It is a **frontend integration stage**: the engine and the endpoint are unchanged. Validation is rendered as an in-page section inside Colony Planner, **after Observed Evidence**. No popout, modal, or top-level app tab is introduced. The current user-facing Colony Planner section order is: Build Plan -> Suggested Builds -> Preview Result -> Observed Evidence -> Validation.

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
| Load action | Candidate details expose `Copy to Build Plan` only when Simulation Preview passes an explicit load callback; otherwise the panel keeps the Stage 5C read-only copy. |
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
- Logistics planning only where ED-Finder has a distinct value-add beyond existing specialist tools.
- Commodity hauling requirements remain deferred; do not duplicate RavenColonial-style hauling/material planning without a later scoped product reason.
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
- The UI explains that it uses current Finder results, builds a temporary tuned order from a copy, leaves the original Finder results unchanged, and does not save preferences or change Colony Planner.
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
- Rows identify top contributors and weaker signals that contributed less under the current weights using conservative language.
- Confidence is shown as an adjustment note when present; contribution values are documented as pre-confidence.
- Rows provide explicit "Open system detail" and "Evaluate in Colony Planner" actions.
- The handoff opens system detail only. It does not auto-run Simulation Preview, generate builds, mutate Colony Planner, persist tuning weights, alter Finder ordering, or use validation/review evidence.

## Stage 7E - Advanced Search Tuning Final Hardening

Stage 7E locks the Advanced Search Tuning arc before Stage 8A Colony Planner UX work. It is a verification and hardening pass, not a new feature stage.

Current Stage 7E status:

- Advanced Search Tuning naming is consistent in current user-facing UI; legacy `#optimizer` remains only as a route compatibility alias.
- `#search-tuning` and legacy `#optimizer` both render Advanced Search Tuning; navigation writes the preferred `#search-tuning` hash.
- Contribution explanations describe support rather than penalties: rows show top contributors and weaker signals that contributed less under the current weights.
- All-zero contribution rows use neutral copy and do not claim that any signal helped most.
- Backend tests cover the additive `/api/ratings/rerank` extension, including pre-confidence contributions, post-confidence final `reranked_score`, and final-score descending ordering.
- Handoff actions open system detail only and remain explicit that they do not run Simulation Preview or generate builds.
- API and Search Tuning docs describe the current contract: temporary tuned score, no new search, no saved preferences, no normal Finder ordering change, no Colony Planner mutation, and no validation/review evidence input.
- Stage 8A Colony Planner UX risks and backlog are captured in `docs/colonisation-redesign/stage-8a-colony-planner-ux-backlog.md`.

## Stage 8A - Colony Planner UX Backlog

Stage 8A is implemented as a Colony Planner UX pass. It addresses discoverability, suggested-builds-first flow, clearer Preview feedback, and next-step guidance without changing Search Tuning scoring or backend mechanics. See `docs/colonisation-redesign/stage-8a-colony-planner-ux-backlog.md` for deferred UX backlog items.

Stage 8A prep is complete in `docs/colonisation-redesign/stage-8a-colony-planner-ux-prep.md`. The prep pass reviewed the DaftMav colonisation workbook, the Elite Dangerous Colonization Mega Guide, current Colony Planner frontend/backend/docs/tests, and the known user-raised friction around discoverability and unclear Preview output.

Stage 8A implementation status:

- Source-informed Colony Planner UX audit remains in the prep report as historical planning context.
- System detail keeps the embedded planner but now exposes a prominent `Open Colony Planner` CTA near the top of the modal. The CTA scrolls/focuses and briefly highlights the embedded Colony Planner section.
- Advanced Search Tuning `Evaluate in Colony Planner` now opens system detail with planner focus intent. It still does not run Preview, generate Suggested Builds, mutate the Build Plan, persist preferences, or feed tuning weights into Colony Planner.
- User-facing planner copy now presents optimiser candidates as **Suggested Builds**. Backend/API/type names remain optimiser/candidate-oriented to avoid risky contract churn.
- First-run guidance leads with an actionable `Show Suggested Builds` start card that scrolls/focuses the Suggested Builds panel where the explicit `Generate Suggested Builds` button lives. It does not auto-generate candidates, auto-run Preview, or auto-load a build.
- Normal Finder result cards now expose `Evaluate in Colony Planner` when expanded. The action opens system detail with Colony Planner focus only; it does not auto-run Preview, generate Suggested Builds, or alter the existing `Details` action.
- Build Plan feedback now shows placement count and Preview state (`Preview not run yet`, stale, running, or `Preview matches current Build Plan`), plus concise next-step guidance after edits.
- Build Plan helper copy now covers target archetype impact, primary-port commitment, yellow/green CP, build-order timing, and orbital/planetary placement tradeoffs.
- Preview Result now starts with an interpreted verdict/next-step block built from existing response fields only.
- Observed Evidence and Validation remain accessible but are framed as later checking steps after in-game evidence is available.
- No Colony Planner behaviour, Simulation Preview scoring, optimiser candidate generation/ranking, validation/review behaviour, backend mechanics, API endpoints, Search Tuning scoring, persistence, auto-run, auto-generate, or auto-load behaviour changed in Stage 8A.

## Stage 8B - Colony Planner Real-Use QA Hardening

Stage 8B is a ruthless real-user QA pass over the Stage 8A workflow. It does not add new mechanics or a dedicated planner workspace. The focus is making the existing entry points, focus behavior, copy, and tests match what a user sees when moving from Finder or Search Tuning into Colony Planner.

Stage 8B implementation status:

- Finder result `Evaluate in Colony Planner`, Search Tuning `Evaluate in Colony Planner`, and system-detail `Open Colony Planner` remain focus-only handoffs. They do not run Preview, generate Suggested Builds, copy a build, or mutate Search Tuning state.
- Colony Planner and Suggested Builds focus highlights now clear pending timers on repeated clicks and unmount, avoiding stale timer callbacks during modal close or system changes.
- Result-card tests now assert that Details, Evaluate, Watch, Map, Pin, and Compare actions stop propagation, do not collapse the card, and do not double-call detail open.
- Suggested Builds first-run tests assert repeated `Show Suggested Builds` clicks focus the panel without auto-generation or auto-loading.
- Preview guidance keeps conservative wording: low scores/warnings are **Needs work**, low confidence is an estimate, and validation compares predictions with what the user saw rather than claiming truth.
- Larger work remains deferred: a dedicated Colony Planner route/workspace, hauling/material estimates, saved builds, EDMC/journal ingestion, automatic learning, and deeper planner route migration.

No backend files, API contracts, scoring, CP/economy/service/buildability mechanics, optimiser generation/ranking, Search Tuning scoring, or Stage 6 validation/review behavior changed in Stage 8B.

## Stage 9A - Full App UX / Navigation Forensic Review

Stage 9A steps back from the Colony Planner and Search Tuning feature work to review whether ED-Finder now reads as one coherent app. It is a forensic UX/navigation review, not a feature stage.

Current Stage 9A status:

- The full frontend route map is documented in `docs/colonisation-redesign/stage-9a-full-app-ux-navigation-forensic-review.md`.
- Main journeys are mapped across Finder, result cards, System Detail, Colony Planner, Suggested Builds, Preview Result, Observed Evidence, Validation/Review Guidance, Advanced Search Tuning, Pinned, Watchlist, Compare, Map, FC Planner, EDDN ticker, and Admin.
- Top-level navigation terminology received tiny safe fixes: `FC` is now `FC Planner`, and `Colony` is now `Colony Tracker` to distinguish the local tracker from the embedded Colony Planner.
- Advanced Search Tuning user-facing copy now says it builds a temporary tuned order and does not run Preview, keeping backend `/api/ratings/rerank` terminology internal.
- Hash-route tests cover all top-level tabs, modal child routes, legacy `#optimizer` compatibility including `#optimizer/system/{id64}`, external `#system/{id64}` links, unknown-route fallback, and modal close.
- Stage 9B is recommended as an information-architecture decision point: decide Admin visibility, consider grouping advanced/secondary tools, evaluate whether Advanced Search Tuning belongs under Finder, and decide whether Colony Planner needs a dedicated workspace.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, persistence, auto-run, auto-generate, or route-framework migration changed in Stage 9A.

## Stage 9B - Dedicated Colony Planner Workspace Feasibility

Stage 9B answers the Stage 9A information-architecture question for Colony Planner. It is a feasibility and design stage only: no workspace route, component move, routing behaviour change, backend mechanic, scoring change, generation change, or validation behaviour change is implemented.

Current Stage 9B status:

- The dedicated workspace design is documented in `docs/colonisation-redesign/stage-9b-dedicated-colony-planner-workspace-feasibility.md`.
- The recommended route for Stage 9C is `#colony-planner/system/{id64}`.
- The recommended router shape keeps the future planner workspace system id separate from the existing System Detail modal `selectedSystemId`, avoiding modal/workspace state conflicts.
- The recommended implementation strategy is to add a light `ColonyPlannerWorkspace` wrapper that reuses `useSystemDetail(id64)` and the existing `SimulationPreviewPanel` / `SimulationPreview` planner components.
- Finder and Advanced Search Tuning `Evaluate in Colony Planner` should route directly to the workspace in Stage 9C, while normal `Details` / `Open system detail` actions continue to open System Detail.
- The embedded planner should remain in System Detail during the first workspace implementation for compatibility, with a later stage deciding whether to replace it with a summary/CTA.
- Stage 9C should add route parsing, workspace rendering, handoff, and no-auto-run/no-auto-generate tests before changing the primary entry points.

Deferred beyond Stage 9B: the actual workspace implementation, embedded-planner removal, source-aware back labels, a static top-level planner tab, saved builds, material/hauling estimates, EDMC/journal ingestion, account persistence, automatic learning, and broader app navigation redesign.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, persistence, auto-run, auto-generate, route behaviour, or route-framework migration changed in Stage 9B.

## Stage 9C - Dedicated Colony Planner Workspace

Stage 9C implements the Stage 9B recommendation as a focused frontend routing/workspace pass. Colony Planner now has a dedicated full-page app-shell workspace at `#colony-planner/system/{id64}` while the embedded planner remains inside System Detail for compatibility.

Current Stage 9C status:

- `useHashRoute` now separates modal `selectedSystemId` from dedicated workspace `plannerSystemId`.
- `#colony-planner/system/{id64}` renders the dedicated Colony Planner workspace and does not accidentally open `SystemDetailModal`.
- `#colony-planner` and invalid planner IDs render a safe no-system workspace state instead of crashing.
- `ColonyPlannerWorkspace` reuses `useSystemDetail(id64)` and `SimulationPreviewPanel`; planner logic is not duplicated.
- Finder result cards and Advanced Search Tuning `Evaluate in Colony Planner` route directly to the workspace.
- Details / Open system detail actions still open System Detail modal routes.
- System Detail `Open Colony Planner` now opens the dedicated workspace when the app provides the workspace handler; the component keeps its embedded-focus fallback for isolated compatibility.
- No static top-level `Colony Planner` nav tab was added because the workspace is system-specific.
- Tests cover route parsing, workspace states, handoffs, modal/workspace separation, Search Tuning fallback behaviour, ResultCard fallback behaviour, and System Detail CTA fallback behaviour.

Deferred beyond Stage 9C: removing or replacing the embedded planner, top-level planner chooser/recent plans, source-aware back labels, saved builds, material/hauling estimates, workspace side rails, EDMC/journal ingestion, account persistence, automatic learning, and broader navigation redesign.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, persistence, auto-run, auto-generate, or auto-load behaviour changed in Stage 9C.

## Stage 9D - Colony Planner Workspace Final Hardening

Stage 9D is the real-use QA hardening pass for the dedicated Colony Planner workspace. It does not add new product surfaces or backend behaviour.

Current Stage 9D status:

- Route tests now cover `navigate('colony-planner')` with and without an active planner system, plus `closeSystem()` safety while on the workspace route.
- Workspace passivity tests render the real `SimulationPreviewPanel` inside `ColonyPlannerWorkspace` and assert that loading the workspace may fetch passive support data but does not call `simulateBuild`, `fetchOptimiserCandidates`, observed-evidence mutations, validation compare, or review endpoints.
- Existing no-system/loading/error/loaded workspace tests continue to cover Back to Finder, Retry, Open full system detail, and planner reuse.
- Existing handoff tests continue to protect Finder, Advanced Search Tuning, and System Detail entry behaviour.
- Docs now clarify that hauling/material planning is deferred and should not duplicate RavenColonial-style specialist tooling unless a later stage defines a distinct ED-Finder value-add.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 9D.

## Stage 10A - Build Plan Structure Picker / Body Layout UX Feasibility

Stage 10A is a feasibility/design stage for making manual Build Plan editing more visual and easier to understand. It reviews the dedicated Colony Planner workspace, the current Build Plan editor, available facility/body/Preview data, and the ED-Finder UI / UX Discussion Tracker based on RavenColonial screenshots.

Current Stage 10A status:

- The feasibility report is documented in `docs/colonisation-redesign/stage-10a-build-plan-structure-picker-body-layout-feasibility.md`.
- The report recommends moving ED-Finder closer to RavenColonial's planning clarity: body-based build layout, compact badges, inline warnings, a future structure picker/table, and a later planner summary.
- The product boundary remains explicit: ED-Finder is the planning/intelligence layer, while RavenColonial remains the stronger hauling/material execution layer.
- Stage 10A does not implement UI behaviour. It does not change Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability, optimiser generation/ranking, Search Tuning, Observed Evidence, Validation/Review, persistence, auto-run, auto-generate, or auto-load behaviour.
- Hauling/material planning, commodity requirements, carrier stock, progress tracking, and trip estimates remain deferred and should not be cloned from RavenColonial.

Recommended Stage 10B:

- Add a low-risk frontend-only body-grouped Build Plan visual view using existing placements, facility templates, and body data.
- Keep the current flat `BuildPlanEditor` as the detailed editing surface.
- Add a local List/Layout toggle with no persistence.
- Show unassigned placements and compact badges for primary port, allowed location, tier, economy, CP, confidence, and missing-data warnings.
- Defer the full structure picker/table and variant-aware selection to Stage 10C.

## Stage 10B - Body-Grouped Build Plan Visual Layout

Stage 10B implements the low-risk visual planning improvement recommended by Stage 10A. It adds a body-grouped Build Plan readout while preserving the existing flat/list editor for detailed editing compatibility.

Current Stage 10B status:

- `BuildPlanSection` now exposes a local List view / Layout view toggle.
- List view remains the default and continues to render the existing `BuildPlanEditor`.
- Layout view renders the current Build Plan grouped by assigned body, with an explicit `Unassigned / needs body` group for placements without a known body.
- Placement cards show build order, facility name, primary-port badge, allowed location, tier, pad size, economy, category/role, CP gives/needs, confidence, missing-template warnings, and body assignment using existing data only.
- The toggle does not persist state, run Preview, generate Suggested Builds, copy/load builds, mutate Observed Evidence, or call Validation/Review endpoints.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 10B.

Deferred beyond Stage 10B:

- Full structure picker/table.
- Variant-aware structure selection.
- Pre-preview body/facility validity explanations.
- Right-side planner summary.
- Material/hauling/trip tracking, which remains outside ED-Finder's planning scope unless a later handoff/export stage is explicitly defined.

## Stage 10C - Graphical Body Layout Planner Foundation

Stage 10C builds on the Stage 10B body readout and makes it feel more like a graphical colony planning layout while staying low risk. It keeps the existing List view as the default editor and renames the visual readout to Layout view.

Current Stage 10C status:

- `BuildPlanBodyView` now renders a compact system-layout summary for system name, target archetype, placement counts, assigned/unassigned counts, bodies used, primary-port status, warning count, visible CP generated/needed, and Preview status.
- Body groups now act as compact layout cards with body tags, primary-port-body badge, warning counts, and body-level CP generated/needed.
- Placement rows now include conservative status/confidence/warning chips for missing templates, unknown bodies, unassigned bodies, estimated data, sparse body metadata, surface-on-water-world risk, surface-on-non-landable-body risk, unclear orbital suitability, stale Preview, and CP pressure.
- Layout view is a readout, not the destructive editing surface. Move/remove/edit actions remain in List view.
- Tests cover summary counts, primary-port states, warning chips, sparse body metadata safety, unassigned visibility, and no Preview/Suggested Builds side effects when toggling.

Spansh import feasibility:

- Spansh currently exposes documented API endpoints for system, dump, body, and station lookup by IDs, and a search endpoint can find systems by name.
- ED-Finder already has backend Spansh dump import infrastructure and a `/api/system/{id64}` detail endpoint with imported bodies/stations.
- A manual "Import / refresh system layout from Spansh" action is possible but should be backend-side, cached in Postgres, explicitly user-triggered, and protected from silently overwriting Build Plans.
- Direct frontend import, silent background refresh, and automatic planner mutation are not safe for Stage 10C.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 10C.

Deferred beyond Stage 10C:

- Structure picker/table and variant comparison.
- Selected body/site detail panel.
- Actual orbital/body map rendering.
- Spansh refresh endpoint, cache workflow, and import review UI.
- Saved builds and external ingestion.
- Material, commodity, carrier, hauling, and trip planning.

## Stage 10D - Layout View Selected Body / Placement Detail Panel

Stage 10D makes Layout view locally interactive while keeping it read-only and safe. Users can select a body group or placement card and inspect what the selection means without changing the Build Plan.

Current Stage 10D status:

- `BuildPlanBodyView` owns local selection state for summary, selected body, and selected placement.
- Body groups and placement cards expose visible selected styling and `aria-pressed` state, and support keyboard activation.
- `BuildPlanLayoutDetailPanel` renders the default summary state, selected-body detail state, and selected-placement detail state.
- The detail panel shows only existing frontend data: plan counts, primary-port status, Preview status, warning count, body tags, placement count, body/placement warnings, facility/template fields, CP generated/needed, confidence, body assignment state, and conservative next-action guidance.
- Detail copy points users back to List view for edits. Layout view still has no add, replace, picker, move, remove, body assignment, or facility selection workflow.
- Tests cover selection, detail panel states, missing template fallback, unassigned/unknown body fallback, stale Preview guidance, selected state, keyboard selection, and no Preview/Suggested Builds side effects.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 10D.

Deferred beyond Stage 10D:

- Structure picker/table and variant comparison.
- Facility selection, add, or replace workflows from Layout view.
- Actual orbital/body map rendering.
- Spansh refresh endpoint, cache workflow, and import review UI.
- Saved builds, account/profile persistence, EDMC/journal ingestion, and automatic learning.
- Material, commodity, carrier, hauling, and trip planning.

## Stage 10E.1 - Spansh Layout Import Foundation

Stage 10E.1 adds the safe foundation for manually importing or refreshing system layout data from a Spansh-style source. It is a contract and UX foundation only; live provider ingestion/upsert policy remains deferred.

Current Stage 10E.1 status:

- Added `POST /api/colony-planner/system/{id64}/import-layout` with a typed request/response contract for `source`, `status`, `fetched_at`, import summary counts, warnings, and errors.
- Added a `LayoutImportProvider` interface and `SpanshLayoutImportProvider` stub path. The Stage 10E.1 stub is intentionally bounded and non-destructive; it does not fetch remote Spansh data or overwrite planner state.
- Added minimal structured logs for import attempt, outcome, and provider failure.
- Added a manual `Import / refresh system layout` button in the Colony Planner Build Plan area.
- Added local read-only import status UI for loading, success, partial, failed, source, fetched timestamp, bodies/stations imported, found counts, warnings, and errors.
- If current imported/body data does not match assigned placement body IDs, the UI shows a `Needs review` warning and does not reassign placements.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 10E.1.

Deferred to Stage 10E.2 or later:

- Real Spansh provider fetches, timeout tuning, and remote response parsing.
- Database upsert policy and cache invalidation/reload workflow for imported bodies/stations.
- Review UI for changed imported rows before using refreshed layout data.
- Automatic Build Plan reassignment, which remains out of scope unless a later stage defines an explicit user-confirmed workflow.
- Material, commodity, carrier, hauling, and trip planning.

## Stage 11A - Colony Planner Visual Redesign Foundation

Stage 11A begins the visual redesign pass for the dedicated Colony Planner workspace. It is a frontend layout and copy polish stage that makes the planning path easier to scan while keeping all existing simulation and optimiser mechanics unchanged.

Current Stage 11A status:

- Strengthened workspace and planner identity with clearer planning-flow framing in the dedicated Colony Planner workspace and planner header.
- Polished section hierarchy so Suggested Builds, Build Plan, and Preview Result read as the primary workflow, while Observed Evidence and Validation are visually framed as later steps.
- Updated Build Plan presentation copy and view framing so List view stays the canonical editor and Layout view stays a read-only planning readout.
- Improved visual card hierarchy and badge/readout styling in the existing Layout view and selection-detail surfaces without changing grouping logic or planner data contracts.
- Applied copy cleanup for conservative planning language across planner sections.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material feature, auto-run, auto-generate, or auto-load behaviour changed in Stage 11A.

Deferred beyond Stage 11A:

- Rich structure picker / variant comparison workflow (if/when a stage branch with picker foundation is merged).
- Deeper body-map visualisation beyond the current card/tree layout.
- Saved-build lifecycle and project persistence.
- EDMC/journal ingestion and automatic data-learning loops.
- Commodity/material/carrier/hauling execution tracking, which remains outside ED-Finder's planning scope.

## Stage 11B - Layout Cards, Detail Panel, and Workflow Hierarchy Polish

Stage 11B deepens the visual readability of the Layout view and surrounding planner workflow without changing any planning mechanics.

Current Stage 11B status:

- Refined Layout view body cards with stronger grouping headers, clearer placement chip grouping, and stronger selected-state emphasis for bodies and placements.
- Added compact body summary/badge rhythm and grouped summary/detail sections in `BuildPlanLayoutDetailPanel`.
- Updated Layout detail panel copy to emphasize read-only planning intent and keep edit direction toward List view.
- Added clearer section hierarchy in `ColonyPlannerSectionNav` with primary-step separators and subdued later-step grouping for Observed Evidence and Validation.
- Preserved keyboard-friendly card interactions and avoided destructive actions from Layout view.

No backend mechanics, backend scoring, optimiser generation/ranking, candidate comparison logic, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, auto-run, auto-generate, auto-load behavior, or hauling/material workflow changed in Stage 11B.

Deferred beyond Stage 11B:

- Richer planner map rendering (e.g., deeper orbit/body visual topology).
- Further structure picker polish and variant affordance work when a Stage 11C plan is ready.
- Saved-build persistence and account/profile persistence.
- EDMC/journal ingestion and automatic planning model updates.
- Commodity/material/carrier/hauling execution tracking.

## Stage 11C - Colony Planner Visual Redesign QA / Final Polish

Stage 11C performs a final visual/readability QA pass across the dedicated Colony Planner workspace before Stage 12 starts deeper picker/table work.

Current Stage 11C status:

- Tightened workflow hierarchy clarity in `ColonyPlannerSectionNav` so the planner path is easier to read at a glance (`Suggested Builds → Build Plan → Preview Result`) and later steps remain visually muted.
- Cleaned the ASCII/Unicode artefact in workflow separators and improved responsive wrapping in the flow strip for long viewports.
- Kept read-only Layout view semantics explicit and preserved placement/body selection keyboard behavior and visible selected state.
- Improved detail-panel focus affordance and polishing so selected summary/body/placement context remains easy to locate on read-only layout.
- Reaffirmed and tests reinforced the same non-side-effect boundary: no automatic Preview run, no auto-generated candidate load, and no automatic suggestion refresh from Layout interactions.

No backend mechanics, backend scoring, Simulation Preview mechanics, optimiser generation/ranking, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, auto-run, auto-generate, auto-load behavior, or hauling/material workflow changed in Stage 11C.

Deferred beyond Stage 11C:

- Full structure picker/table interaction and richer placement replacement flows.
- Deeper body map/plan topology rendering.
- Facility variant workflows and layout/body-specific comparison UX beyond the current readout.
- Saved builds, account persistence, and external ingestion loops.
- Commodity/material/carrier/hauling execution tracking.

## Stage 11D - Reviewer-Driven Visual Hierarchy Refinement

Stage 11D addresses a final narrow polish pass on reviewer feedback for the dedicated Colony Planner visual surface.

Current Stage 11D status:

- Fixed small visual/navigation copy regressions in the workflow nav strip and normalized workflow separators so planner path text and spacing are stable across encodings and smaller viewports.
- Updated workflow nav wording so `Suggested Builds`, `Build Plan`, and `Preview Result` stay visually primary while `Observed Evidence` and `Validation` remain clearly marked as later steps.
- Preserved the accessibility-safe interaction model from Stage 11C so body selection and placement selection remain separate controls with visible selection and keyboard support.
- Kept all existing section-copy and interaction contracts unchanged (`List view` remains the canonical editable surface, `Layout view` remains read-only).
- Reaffirmed no passive/side-effect regressions: no automatic Preview run, no suggested-build auto generation/load, no mutation of planner state from layout interactions.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, hauling/material workflow, auto-run, auto-generate, or auto-load behaviour changed in Stage 11D.

Deferred beyond Stage 11D:

- Full structure picker/table enhancement and facility variant workflows.
- Deeper planner topology and body-map rendering.
- Material/commodity/carrier/hauling execution tracking.
- Saved-build lifecycle and external ingestion loops.

## Stage 11E - Colony Planner Interaction Polish and Copy Hardening

Stage 11E is a micro-polish and accessibility pass that hardens the Planner workflow signalling, keeps the existing read/write boundaries obvious, and tightens interaction clarity for `Build Plan` and `Layout view`.

Current Stage 11E status:

- Reinforced Planner workflow copy and ordering on both the workspace header and planner nav.
- Confirmed Planner identity as a dedicated visual planning workspace with explicit `Suggested Builds -> Build Plan -> Preview Result` path and clearly secondary `Observed Evidence` and `Validation`.
- Kept `List view` as the canonical editing path and `Layout view` as a planning readout.
- Added explicit Layout read-only / edit guidance in Planner copy, including `Use List view to edit`.
- Preserved accessibility-focused interaction structure in Layout cards: dedicated body selection control plus separate placement selection and keyboard access.
- Added/updated focused regression tests for nav wording, layout guidance copy, selection behavior, and no accidental side-effect triggering from view interactions.
- Ran copy-safety checks to avoid user-facing non-goal wording.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, auto-run, auto-generate, auto-load behaviour, or hauling/material workflow changed in Stage 11E.

Deferred beyond Stage 11E:

- Full structure picker/table expansion and variant-aware placement comparison.
- Additional body-map style spatial rendering beyond the current card layout.
- Saved build persistence and external ingestion loops.
- Commodity/material/commodity/trip planning features, which remain outside ED-Finder's planning layer.

## Stage 11F - Micro-Polish and QA Guardrails

Stage 11F is a narrow UX polish and wording alignment pass over the existing Colony Planner visual workflow before deeper planning interaction work resumes.

Current Stage 11F status:

- Clarified the Build Plan workflow chips in `BuildPlanSection` so the primary flow remains `Suggested Builds -> Build Plan -> Preview Result` and later sections are clearly separated as `Observed Evidence` and `Validation`.
- Updated workflow labeling in the plan section to avoid abbreviated "Evidence / Validation later" phrasing, while retaining existing non-side-effect behavior.
- Kept `List view` as the canonical editable surface and `Layout view` as planning readout-only.
- Preserved keyboard/accessibility behavior for body and placement selection controls introduced in Stage 11D/11E.
- Reaffirmed no automatic preview execution, no Suggested Build auto-generation, and no automatic build mutation during navigation, view toggling, or layout interactions.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, auto-run, auto-generate, auto-load behavior, or hauling/material workflow changed in Stage 11F.

Deferred beyond Stage 11F:

- Full structure picker/table enhancements.
- Variant-aware placement comparison workflows.
- Deeper planner map topology and import-review UX beyond the current layout cards.
- Saved build lifecycle and external ingestion loops.
- Commodity/material/commodity/trip planning features.

## Stage 11G - Workflow Label Consistency and Header Micro-Polish

Stage 11G is a small, mechanics-safe cleanup pass to keep workflow labeling consistent across planner surfaces after the Stage 11F wording pass.

Current Stage 11G status:

- Normalized `ColonyPlannerHeader` workflow chip labels to match the rest of the planner surface (`Suggested Builds`, `Build Plan`, `Preview Result`, `Observed Evidence`, `Validation`) without suffix duplication.
- Kept a11y intention (`Observed Evidence` and `Validation` remain secondary by styling/semantic context) while avoiding visual redundancy in chip labels.
- Added a focused regression test for header workflow labels and Run Preview button enabled-state behavior.
- Updated docs to record this micro-polish as a separate consistency pass.
- Clarified a legacy rating-rationale caveat: if stored `ratings.rationale` still includes old phrases like "Strong Refinery; via ...", UI now labels them as stale-format and advises a refresh. This is a presentation hardening only; scoring is not changed. Systems with legacy rationale should be refreshed through existing importer-backed rating rebuild paths (not via UI auto-recompute).

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behaviour, Validation/Review behaviour, saved-build persistence, auto-run, auto-generate, auto-load behaviour, or hauling/material workflow changed in Stage 11G.

Deferred beyond Stage 11G:

- Full structure picker/table enhancements and facility variant workflows.
- Deeper planner map topology and import-review UX beyond current layout cards.
- Saved build lifecycle and external ingestion loops.
- Commodity/material/commodity/trip planning features.

## Stage 11H - Layout Import Staleness Guardrail

Stage 11H is a narrow mechanics-safe polishing pass that addresses remaining QA consistency: when users switch systems, stale layout-import banners/messages in the Build Plan section should be cleared so the next system starts from a clean planner layout-import state.

Current Stage 11H status:

- Added system-scoped reset for layout import status in `BuildPlanSection`.
- Cleared stale `layoutImportResult`, `layoutImportError`, and `layoutImportRunning` when `systemId64` changes.
- Added focused regression coverage for stale layout-import status and success-state rendering after import.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, auto-run, auto-generate, auto-load behavior, or hauling/material workflow changed in Stage 11H.

Chronology clarification:

- Stage 11F preceded 11G; Stage 11H follows 11G on this branch.

Deferred beyond Stage 11H:

- Full structure picker/table enhancements and variant-aware placement comparison.
- Additional layout-import UX refinements (history, retry queueing, conflict messaging).
- Saved build persistence and external ingestion loops.
- Commodity/material/commodity/trip planning features.

## Stage 12A - Structure Picker / Table Foundation

Stage 12A adds the first safe structure-picker surface in the Colony Planner List view so users can compare facility templates before selecting one for a placement.

Current Stage 12A status:

- Added a dedicated `StructurePickerTable` component integrated into `BuildPlanEditor` via an explicit `Browse structures` control per placement.
- Preserved List view as the canonical edit path. The existing template `<select>` remains available and authoritative.
- Added conservative search/filter controls (`All`, `Orbital`, `Surface`, `Both`) and facility comparison columns: structure, location, tier, pad, economy, role, CP gives/needs, confidence, validity, and explicit select action.
- Added body-context-aware planning hints: selected body context, no-body state, unknown-body state, and conservative warnings for likely risky combinations.
- Reused existing planning warning semantics for high-signal checks:
  - surface facility on water world
  - surface facility on non-landable body
  - sparse body metadata
  - orbital suitability unclear
  - estimated template data
- Kept selection explicit and local. Choosing `Select structure` only updates the current placement template via existing `onUpdate`; no preview/generation/load side effects are introduced.
- Added focused tests for picker rendering, search/filter behavior, warning/validity labels, explicit selection callback behavior, and composed no-side-effect behavior from `SimulationPreview`.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, auto-run, auto-generate, auto-load behavior, or hauling/material workflow changed in Stage 12A.

Deferred to Stage 12B:

- Variant/family grouping and richer picker presentation modes.
- Placement replacement workflows beyond explicit per-row template selection.
- Layout-view-side picker actions (Layout remains read-only).
- Any backend catalogue enrichment or new mechanics fields.
- Saved-build and logistics workflows.

## Stage 12B - Structure Replacement Comparison / Architect Context

Stage 12B makes structure replacement more deliberate by inserting a read-only comparison step before a picker selection changes a placement.

Current Stage 12B status:

- Added a focused replacement review panel in the Colony Planner List view. Selecting a structure from the picker now opens a current-vs-proposed comparison instead of applying immediately.
- Comparison fields include structure name, tier, allowed location, pad size, economy, role/category, CP generated, CP needed, confidence, validity labels, warning chips, and body context.
- Added explicit `Apply replacement` and `Cancel replacement` actions. Apply uses the existing placement `onUpdate` path and updates only the selected placement template; cancel closes the review without mutation.
- Kept replacement review local and manual. It does not run Preview, generate or load Suggested Builds, run validation, persist builds, or mutate primary-port state.
- Added conservative read-only Architect primary-port context: users should check Architect Mode before final station placement, inconvenient flagged slots can be treated as outpost candidates, and primary-port location is planning context rather than a Build Point source.
- Removed the primary-port checkbox from the List view editor surface. Existing primary-port flags are shown as read-only state; ED-Finder does not offer arbitrary `make primary` or `remove primary` controls.
- Updated focused tests for replacement review, cancellation, apply behavior, no preview/optimiser side effects, and read-only primary-port wording.

No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, import behavior, auto-run, auto-generate, auto-load behavior, map topology rendering, or hauling/material workflow changed in Stage 12B.

Deferred to Stage 12C:

- Architect Slot Survey data entry/import surfaces for confirmed in-game primary-port slot evidence.
- Better body/orbit recommendation context once confirmed Architect-slot data exists.
- Layout-view-side explanatory affordances remain read-only unless a later stage explicitly scopes safe actions.
- Backend catalogue enrichment and persistence workflows remain separate.

## Stage 12C - Picker Grouping / Replacement Delta Polish

Stage 12C keeps the Structure Picker and replacement workflow frontend-only while making the catalogue easier to browse and replacement consequences easier to read.

Current Stage 12C status:

- Added conservative frontend grouping for structure templates. Group labels are derived only from existing catalogue fields such as port/support status, allowed location, economy, category/role, and tier-visible row data; no backend taxonomy or mechanics field is introduced.
- `StructurePickerTable` now renders grouped sections such as orbital ports, surface settlements, economy-specific support, military/security, support facilities, and unknown/other while preserving search, location filters, warning chips, validity labels, and explicit `Select structure` actions.
- The picker highlights both the current structure and the proposed replacement when a replacement review is open. Highlighting is visual planning state only and does not mutate the Build Plan.
- Replacement review now shows a field-delta table for current vs proposed values. Changed fields are emphasized; unchanged fields remain readable but subdued.
- Warning movement is split into warnings added, warnings removed, and warnings unchanged so users can see whether a replacement reduces, preserves, or introduces planning risk.
- Architect primary-port guidance remains read-only and conservative. The List view reminds users to confirm the primary-port location in-game through System Map and Architect Mode before final major station placement, frames primary-port location as placement guidance rather than a Build Point source, and suggests using an inconvenient flagged slot for an outpost while placing the main station elsewhere.

Safety boundaries in Stage 12C:

- No backend mechanics, backend scoring, normal search scoring, Simulation Preview scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, candidate comparison logic, Search Tuning behaviour, Observed Evidence behavior, Validation behavior, saved-build persistence, import behavior, EDMC ingestion, auto-run, auto-generate, auto-load behavior, map topology rendering, or hauling/material workflow changed.
- Stage 12C does not add primary-port setting/unsetting controls, make-primary/remove-primary actions, arbitrary Architect slot assignment, confirmed-slot storage, backend import/storage, full Architect Slot Survey, auto-preview, auto-save, polling, or silent mutation.
- Layout view remains read-only planning output. List view remains the canonical editable surface.

Test coverage added in Stage 12C:

- Group-label derivation and stable grouped ordering.
- Grouped picker rendering, grouped search/filter behavior, current/proposed row highlighting, and explicit selection behavior.
- Replacement comparison changed/unchanged field rendering, warning added/removed/unchanged deltas, apply/cancel behavior, no preview/optimiser side effects, and continued absence of primary-port editing controls.

Deferred to Stage 12D:

- Architect Slot Survey data entry/import surfaces for confirmed in-game primary-port slot evidence.
- Better body/orbit recommendation context once confirmed Architect-slot data exists.
- Any backend catalogue enrichment, saved-build persistence, logistics/material planning, or layout-view action surface.

## Stage 12D - Planner Intelligence Guidance Foundation

Stage 12D adds a frontend-only guidance layer on top of existing planner data and warning strings. It explains what a warning means, how severe it is, and what the user should confirm in game without changing optimiser output, scoring, preview semantics, or Build Plan mutation rules.

Current Stage 12D status:

- Added deterministic guidance severity levels: `info`, `advisory`, `caution`, `high-risk`, and `incompatible`.
- Added compact guidance rows in List view and read-only Layout view. These rows explain existing facts such as estimated template data, sparse body metadata, unknown body assignments, and potentially invalid surface placements.
- Surface structures planned on water worlds or non-landable bodies are explained as incompatible placement risks. Estimated template data stays advisory and does not block explicit user actions.
- Water-world orbital context can surface a conservative tourism/agriculture planning hint when the existing body/template data supports it.
- Architect primary-port guidance remains read-only. Users are reminded to check System Map -> Architect Mode before final major station placement, and inconvenient flagged primary-port slots are framed as possible outpost placements rather than reasons to reject a system.

Safety boundaries in Stage 12D:

- No backend mechanics, backend scoring, CP formulas, economy mechanics, service unlock mechanics, buildability mechanics, optimiser generation/ranking, Simulation Preview scoring, Search Tuning, Observed Evidence semantics, Validation semantics, persistence, imports, EDMC ingestion, hauling/material workflows, or map topology rendering changed.
- Guidance is explanatory only. It does not block Apply/Cancel actions, does not auto-run Preview, does not auto-generate/load/save, and does not mutate the Build Plan silently.
- Primary-port location remains planning guidance only and is not treated as a Build Point source or user-editable truth.

Test coverage added in Stage 12D:

- `plannerGuidanceUtils.test.ts` for severity mapping, placement guidance, read-only Architect guidance, and body-level guidance.
- `BuildPlanEditor.test.tsx` coverage for advisory guidance rendering while preserving explicit cancel/apply behavior.
- `BuildPlanBodyView.test.tsx` coverage for Layout guidance rendering and continued absence of primary-port editing controls.

Deferred to Stage 13:

- Architect observation concepts, unknown-vs-observed status, and future storage/import decisions.
- Topology-aware readout beyond conservative body/placement guidance.
- Full Architect Slot Survey and primary-port observation workflows.

## Stage 13A - Architect Observation Foundation

Stage 13A introduces frontend-only Architect observation concepts so the planner can distinguish unknown planning context from user-observed in-game Architect context without adding storage, imports, or primary-port editing.

Current Stage 13A status:

- Added read-only Architect observation status helpers for `not_observed` vs `observed` survey state, observed orbital/ground slot counts when supplied, and unknown vs observed primary-port flag context.
- Added a compact Architect observation panel in the List editor and read-only Layout detail surfaces. By default it reports `Architect survey: not observed`, `Primary-port flag: unknown`, and unknown slot counts.
- Preserved the conservative guidance that System Map -> Architect Mode should be checked before final major station placement, primary-port location is placement guidance rather than a Build Point source, and inconvenient flagged primary-port slots can be handled with an outpost while the main station goes elsewhere.

Safety boundaries in Stage 13A:

- No backend persistence, import, EDMC ingestion, Architect Slot Survey storage, scoring, CP formulas, economy mechanics, buildability mechanics, service unlock mechanics, optimiser behavior, Simulation Preview scoring, Observed Evidence semantics, or Validation semantics changed.
- The Architect observation panel is display-only. It has no make-primary/remove-primary controls, no set/unset primary-port controls, no slot editing, and no automatic mutation.
- Unknown Architect context is never presented as confirmed. Observed state is only rendered when explicitly supplied to the frontend helper/component.

Test coverage added in Stage 13A:

- `architectObservationUtils.test.ts` covers default unknown state, observed mock state, slot-count normalization, and guidance copy.
- `ArchitectObservationPanel.test.tsx` covers unknown and observed rendering plus absence of primary-port editing controls.
- Existing planner/List/Layout tests continue to confirm read-only Architect wording and no primary-port controls.

Deferred to Stage 13B/13C:

- Persistent Architect survey records, import/storage design, manual observation entry workflows, and EDMC/journal ingestion.
- Full Architect Slot Survey UI and exact slot topology capture.
- Topology-aware Layout readout that groups bodies, orbital-capable context, ground-capable context, and observed/unknown Architect status.

## Stage 13B - Layout Topology Readout

Stage 13B improves the read-only Layout view into a more topology-aware planning readout while staying conservative about unknown Architect data.

Current Stage 13B status:

- Added frontend-only topology readout helpers that count current planned orbital, ground, and unknown-location placements per body group using existing placement templates only.
- Added compact read-only topology sections to Layout body cards and selected-body detail so users can distinguish known bodies, unknown body references, unassigned placements, ground-capable context, and unknown Architect slot counts.
- Preserved the Stage 13A Architect boundary: slot counts and primary-port flags remain unknown unless explicit observed context is supplied to frontend helpers; no exact slot locations are invented.

Safety boundaries in Stage 13B:

- Layout view remains read-only. No placement editing, primary-port editing, make/remove primary actions, slot editing, persistence, imports, polling, auto-preview, auto-generation, or silent mutation are introduced.
- No backend mechanics, scoring, CP formulas, economy mechanics, service unlock logic, buildability rules, optimiser generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence semantics, Validation semantics, EDMC ingestion, hauling/material workflows, or map topology rendering changed.
- Ground/orbital readouts are planning context only. They do not assert confirmed Architect capacity and do not change buildability or planner scoring.

Test coverage added in Stage 13B:

- `layoutTopologyUtils.test.ts` covers topology grouping, orbital/ground/unknown counts, known/unknown/unassigned body states, conservative ground-capability labels, observed mock Architect labels, and template-location formatting.
- `BuildPlanBodyView.test.tsx` covers topology readout rendering in Layout cards/detail while preserving read-only selection behavior.

Deferred to Stage 13C:

- Strategic topology labels such as main-station candidate and support-body guidance.
- Persistent Architect survey records, manual observation entry, imports, and EDMC/journal ingestion.
- Full Architect Slot Survey UI, exact slot topology capture, and any map-like spatial rendering.

## Stage 13C - Strategic Topology Guidance

Stage 13C adds conservative strategic labels to the read-only Layout topology surface. It uses only existing Build Plan placements, facility-template fields, body metadata, and optional frontend Architect observation context.

Current Stage 13C status:

- Added frontend-only strategic topology guidance helpers for body groups.
- Layout body cards and selected-body detail can now label main-station candidates, support-focused bodies, sparse metadata, likely tourism/agriculture review pressure, unknown Architect primary-port flag context, and the outpost-on-inconvenient-flag option.
- The guidance is advisory copy only. It does not create or modify scoring signals, optimiser ranking, travel-time calculations, Build Plan placement state, Preview state, Observed Evidence, or Validation state.
- Primary-port guidance remains conservative: unknown Architect primary-port flag context is labelled unknown, users are told to check Architect Mode before final station placement, and inconvenient flagged slots are framed as possible outpost placements rather than reasons to reject a system.

Safety boundaries in Stage 13C:

- No backend mechanics, scoring, CP formulas, economy mechanics, buildability rules, service unlock logic, optimiser generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence semantics, Validation semantics, persistence, imports, EDMC ingestion, hauling/material workflows, or map topology rendering changed.
- No primary-port editing controls, make/remove primary actions, arbitrary slot assignment, Architect Slot Survey storage, auto-preview, auto-generation, auto-load/save, polling, or silent mutation are introduced.
- Strategic labels are deterministic UI guidance from existing facts only. They do not invent body relationships, exact travel times, confirmed slot capacity, or primary-port truth.

Test coverage added in Stage 13C:

- `strategicTopologyGuidanceUtils.test.ts` covers main-station candidate labels, support-body labels, tourism/agriculture pressure labels, observed-vs-unknown Architect primary-port flag handling, and sparse/unknown body copy.
- `BuildPlanBodyView.test.tsx` covers strategic topology rendering in Layout cards and selected-body detail while preserving read-only layout behavior.

Deferred beyond Stage 13C:

- Persistent Architect survey records, manual observation entry, imports, and EDMC/journal ingestion.
- Full Architect Slot Survey UI, exact slot topology capture, and any map-like spatial rendering.
- Travel-time or adjacency calculations unless future data supports them.

## Stage 14A - Observed Evidence Planning Expansion

Stage 14A strengthens Observed Evidence as the place where real in-game observations are organized against the plan. It remains a passive evidence surface and uses the existing observed-facts API only.

Current Stage 14A status:

- Added frontend-only evidence category helpers for primary-port / Architect notes, structures actually built, body or slot observations, economy observations, service / population / security observations, and general notes.
- Added an Observed vs planned framing readout to the Observed Evidence panel so Planned, Observed, and Unknown / not checked states remain visibly distinct.
- Category counts are derived from the visible evidence list and stay clearly labelled as evidence organization, not validation verdicts.

Safety boundaries in Stage 14A:

- No backend persistence contract, imports, EDMC ingestion, scoring, CP formulas, economy mechanics, buildability rules, service unlock logic, optimiser behavior, Simulation Preview scoring, Validation semantics, or planner mutation changed.
- Viewing Observed Evidence does not auto-run Preview, generation, Validation compare/review, polling, or silent mutation.
- Primary-port / Architect evidence is categorized only when existing manual evidence text/tags/fields mention it. Stage 14A does not add Architect survey storage, slot editing, or primary-port editing controls.

Test coverage added in Stage 14A:

- `observedEvidencePlanningUtils.test.ts` covers category derivation and zero-count category summaries.
- `ObservedEvidencePanel.test.tsx` covers planned/observed/unknown framing, category rendering, and passivity against preview, generation, validation compare/review, and observed-fact mutations while viewing.

Deferred beyond Stage 14A:

- Richer manual evidence types for Architect survey records, slot observations, service/population/security-specific fields, and future persistence/import work.

## Stage 14B - Validation Review Clarity

Stage 14B improves how Validation explains mismatches between the current Preview Result and Observed Evidence. It remains a frontend clarity stage layered over the existing Stage 6C compare response and Stage 6E review response.

Current Stage 14B status:

- Added a frontend-only validation review category layer for comparison rows: Matches plan, Differs from plan, Missing observation, Unknown / not checked, and Needs manual review.
- Comparison cards now show the category alongside the existing backend status/severity/confidence labels. Backend statuses are preserved; the new category is explanatory copy only.
- Differing rows use explicit mismatch wording: `Observed value differs from preview.` Missing and unknown rows distinguish unrecorded evidence from unchecked/uncertain comparison state.
- Validation now includes conservative review reminders: Preview assumes the current plan and should be confirmed in-game; Architect primary-port context is not a dedicated validation field and should be checked in System Map -> Architect Mode before final major station placement.

Safety boundaries in Stage 14B:

- No backend compare/review engine, API contract, persistence, observed-facts semantics, Validation semantics, Simulation Preview scoring, optimiser behavior, CP/economy/buildability/service mechanics, Search Tuning, imports, EDMC ingestion, or planner mutation changed.
- Validation still does not auto-run Preview, generation, evidence mutation, compare/review outside the existing Validation queries, polling, auto-save, or auto-load.
- Primary-port wording remains read-only guidance. Stage 14B does not add Architect survey storage, primary-port editing, slot editing, or any make/remove primary control.

Test coverage added in Stage 14B:

- `validationReviewCategoryUtils.test.ts` covers category mapping, fallback behavior for future statuses, and explicit mismatch copy.
- `ValidationPanel.test.tsx` covers review reminders, comparison category rendering for matches/differs/missing/manual-review/unknown states, Architect primary-port unknown copy, and existing passivity against preview/generation/observed-fact mutation.

Deferred beyond Stage 14B:

- Dedicated Architect survey validation fields once Stage 13 storage/input work exists.
- Richer mismatch grouping, bulk review workflows, and any auto-resolution remain deferred.

## Stage 15 - Topology-First Planner Workspace

Stage 15 reframes the next Colony Planner work as a product/workspace redesign rather than another vertical-panel polish pass. The dedicated route already exists as `#colony-planner/system/{id64}`, but it still wraps the current stacked Simulation Preview flow. The Stage 15 plan moves the target architecture toward a topology-first strategic colony planning workspace with a body tree, local body/slot editing, persistent summary, saved project lifecycle, and drawer-based Preview/Evidence/Validation modes.

Stage 15A is documentation only and is captured in `docs/colonisation-redesign/stage-15-planner-workspace-redesign-plan.md`. It audits the current route/component/data flow, identifies scroll bloat and internal wording, defines the target UX architecture, specifies a minimal saved Colony Project model, and breaks implementation into safe stages 15B through 15I.

Key Stage 15 direction:

- Keep ED-Finder's dark ED-orange / brushed steel identity. Use RavenColonial only as workflow inspiration: visible body hierarchy, local placement, persistent stats, compact warnings, and plan save/load.
- Simplify System Detail into an overview, project/planner status summary, and open-planner action.
- Make the Planner Workspace topology-first: left body tree, center selected-body/slot editor, right persistent summary, bottom/drawer modes for Preview, Observed Evidence, Validation, and project journal.
- Improve Suggested Builds quality so trivial port-only or "Colony Ship only" outputs are hidden, demoted, or clearly labelled as fallback seeds rather than first-class recommendations.
- Introduce saved Colony Projects, frontend-only first if necessary, before backend persistence is committed.
- Keep Architect primary-port handling conservative: in-game Architect Mode can reveal the flagged slot, but ED-Finder must not let users arbitrarily declare primary-port truth. The flag is placement guidance, not a Build Point source, and inconvenient flagged slots can be handled as outpost candidates while the main station goes elsewhere.

Stage 15 safety boundaries:

- Stage 15A does not implement UI or backend changes.
- Later Stage 15 implementation should not change CP formulas, economy mechanics, service unlock logic, simulation scoring, observed-evidence semantics, or validation semantics unless a separate mechanics stage explicitly scopes that work.
- Avoid RavenColonial visual cloning, proprietary assets, and exact look/feel replication.

### Stage 15B - Planner Workspace Shell V2

Stage 15B implements the first workspace-shell step on the existing `#colony-planner/system/{id64}` route. The route now feels like a planning application shell rather than a single-column report wrapper: compact system header, left topology orientation rail, central contained planner work area, and right persistent summary/context rail.

Current Stage 15B status:

- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx` keeps using `useSystemDetail(id64)` and reuses `SimulationPreviewPanel` in the central workspace content.
- The left topology rail is a read-only placeholder for Stage 15D. It surfaces body counts, notable loaded bodies, and an unassigned-placement placeholder without changing plan state.
- The right summary rail surfaces project/planner status placeholders, Architect-not-observed status, loaded body/station counts, mode chips, and deferred-stage reminders.
- Existing planner behavior remains contained and available. Stage 15B does not alter Simulation Preview internals, Suggested Builds generation, Observed Evidence, Validation, imports, persistence, CP/economy/service mechanics, backend scoring, or route shape.

Deferred to Stage 15D and later:

- Stage 15E should move build editing toward selected body/slot context.
- Stage 15F should add Suggested Builds quality gates and a load-into-workspace flow.
- Stage 15G should add saved Colony Project persistence and saved-project status on System Detail.

### Stage 15C - System Detail Simplification

Stage 15C simplifies the main System Detail modal so it is an overview/discovery surface rather than a second Colony Planner workspace. The full planning workflow now belongs to the existing `#colony-planner/system/{id64}` route.

Current Stage 15C status:

- `frontend-v2/src/features/system-detail/SystemDetailModal.tsx` now renders a compact Colony Planner entry card with planner availability, system name/ID64, concise player-facing copy, and an `Open Colony Planner` CTA.
- System Detail keeps rating profile, system info, bodies/stations/exploration summaries, external links, and existing modal actions.
- System Detail no longer renders the full planner stack inline: buildability, regional position, Recommended Builds, embedded Simulation Preview, slot prediction, Observed Evidence, and Validation are no longer part of the modal path.
- Recommended Builds are workspace-first. System Detail does not fetch/generate/display recommended-build candidates just to populate the entry card.
- The System Detail to Planner handoff uses the existing `#colony-planner/system/{id64}` route; the Stage 15B back-to-system-detail action preserves the return flow.
- Error display is compact and friendly, avoiding raw backend strings in the overview modal.

Safety boundaries in Stage 15C:

- No backend mechanics, backend scoring, optimiser generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence, Validation, imports, persistence, CP/economy/service mechanics, or auto-run behavior changed.
- No saved projects and no topology tree implementation were added.
- The existing planner route shape remains unchanged.

Test coverage added/updated in Stage 15C:

- `SystemDetailModal.test.tsx` covers the compact planner entry card, existing overview visibility, absence of inline planner panels, disabled friendly state, compact error state, and normal modal close behavior.
- `App.test.tsx` covers the System Detail `Open Colony Planner` handoff to `#colony-planner/system/{id64}`.
- Stage 15B planner workspace tests continue to cover the dedicated planner route shell.

Deferred after Stage 15C:

- Stage 15D replaces the read-only topology placeholder rail with a real topology/body-tree MVP.
- Keep saved project status, persistence, Suggested Builds quality gates, and drawer-mode Evidence/Validation for later Stage 15 work.

### Stage 15D - Topology Tree MVP

Stage 15D replaces the Stage 15B placeholder left rail with a real read-only topology/body-tree navigation MVP inside the dedicated Colony Planner workspace. The route remains `#colony-planner/system/{id64}`.

Current Stage 15D status:

- `frontend-v2/src/features/colony-planner/ColonyTopologyRail.tsx` renders the system root, body rows, child/moon indentation when parent metadata exists, planned placement counts, orbital/surface/flex chips, sparse metadata chips, primary-port planned chips, unknown/unmatched placement groups, and unassigned placements.
- `SimulationPreviewPanel` and `SimulationPreview` expose a narrow read-only `TopologyPlanSnapshot` callback so the workspace can display current placement context without moving Build Plan editing out of the central planner.
- `ColonyPlannerWorkspace.tsx` owns local read-only selection state. Selecting a body, placement, unknown group, or unassigned group highlights the rail and updates the right summary/context panel.
- The right summary panel now shows selected context, placement count, warning count, Architect status, and explicit `Read-only topology selection` copy.
- Empty body layout state is friendly and compact: no body layout imported yet, use planner tools to import/refresh when available.

Safety boundaries in Stage 15D:

- No backend mechanics, scoring, CP formulas, economy logic, optimiser generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence, Validation, imports, persistence, or auto-run behavior changed.
- No topology-local structure editing, saved projects, Architect Slot Survey storage, primary-port editing, map rendering, or hauling/material workflow was added.
- Selection is read-only UI state only. It does not mutate the Build Plan, run Preview, generate candidates, import layout, mutate observations, or run validation.

Test coverage added/updated in Stage 15D:

- `ColonyTopologyRail.test.tsx` covers body rows, parent/child indentation support, per-body placement counts/chips, unknown/unmatched and unassigned groups, read-only selection context, and empty body layout copy.
- `ColonyPlannerWorkspace.test.tsx` covers shell rendering with the 15D topology rail, one-way plan snapshots, central `SimulationPreviewPanel` availability, and read-only selected-context updates.
- `ColonyPlannerWorkspace.integration.test.tsx` confirms the real workspace still loads passive planner data without preview/generation/import/evidence/validation side effects, including after topology selection.

Deferred to Stage 15E:

- Move editing toward selected body/slot context while preserving explicit Apply/Preview behavior.
- Keep saved projects, Suggested Builds quality gates, and drawer-mode Evidence/Validation for later scoped stages.

### Stage 15E - Topology-Aware Planner Coordination

Stage 15E keeps topology selection read-only while allowing it to coordinate with the central Build Plan editor.

Current Stage 15E status:

- The workspace passes the selected topology body or placement into the existing central planner through a narrow prop chain.
- Selecting a body in the topology rail updates a compact `Currently viewing` context in Build Plan and highlights matching placement rows in List view.
- Selecting a placement in the topology rail highlights and focuses the corresponding placement editor row in List view.
- The central planner exposes an explicit `Add to selected body` action when a known topology body is selected. It reuses the existing placement-add path and assigns only the selected body id.
- Structure picker context can evaluate an unassigned placement against the selected topology body without mutating the placement.

Safety boundaries in Stage 15E:

- Rail clicks do not mutate the Build Plan, run Preview, generate Suggested Builds, import layout, save state, mutate Observed Evidence, or run Validation.
- Editing remains in the central planner. No drag/drop, slot editing, topology-local editor, primary-port truth editing, persistence, backend mechanics, scoring, CP formulas, economy logic, optimiser behavior, or validation/evidence semantics changed.

Test coverage added/updated in Stage 15E:

- Workspace tests cover selection propagation from topology rail to the planner adapter.
- Build Plan tests cover selected-body context, explicit add-to-selected-body behavior, placement-row highlighting/focus targeting, and no mutation from selection alone.

Deferred after Stage 15E:

- Stage 15F should improve Suggested Builds quality and workspace loading.
- Stage 15G should add saved Colony Project persistence.
- Stage 15H should move Evidence and Validation into drawers/modes.

### Stage 15F - Suggested Builds Quality Gate + Workspace Loading

Stage 15F makes Suggested Builds a workspace-first review surface without changing optimiser generation, ranking, scoring, or backend mechanics.

Current Stage 15F status:

- Suggested Build display now applies a frontend quality gate over the existing optimiser response. Trivial one-placement plans, Colony Ship-only plans, Colony Ship plus generic-station plans, duplicate near-identical placement sets, and candidates with no clear purpose are hidden from the visible list.
- If generation returns only trivial/duplicate candidates, the workspace shows: `No useful suggested builds are available yet. Add more system data or start a manual Build Plan.`
- Candidate cards/details now surface player-facing category, purpose, reason, tradeoff, and next action copy.
- Raw optimiser tags such as `body_diversity` are translated into readable labels like `Uses multiple bodies`.
- The explicit load action is now framed as `Load into Planner Workspace`; it still uses the existing candidate-to-Build-Plan path and still requires confirmation when replacing an existing plan or loading stale candidates.

Safety boundaries in Stage 15F:

- No optimiser backend scoring/ranking/generation, Simulation Preview scoring, CP/economy/buildability/service mechanics, Search Tuning, imports, persistence, Observed Evidence, Validation, or primary-port truth handling changed.
- Suggested Builds still require explicit generation and explicit load. They do not auto-copy into the Build Plan, auto-run Preview, auto-save, auto-import, auto-generate on page load, mutate evidence, or run validation.

Test coverage added/updated in Stage 15F:

- Optimiser UI tests cover trivial build filtering, duplicate filtering, useful-build empty state, purpose/reason/tradeoff/action rendering, tag translation, explicit workspace loading, and existing no-auto-side-effect behavior.

Deferred after Stage 15F:

- Stage 15G should add saved Colony Project persistence.
- Stage 15H should move Evidence and Validation into drawers/modes.

### Stage 15G - Saved Colony Project Persistence MVP

Stage 15G adds a local-only saved Colony Project MVP so users can return to a plan later without committing to backend schema too early.

Current Stage 15G status:

- Added a Zustand/localStorage project store under `ed_colony_projects_v1`.
- The minimum project model includes project id, system id64/name, project name, build plan placements, selected body assignments derived from placements, notes, status, created/updated timestamps, and archive timestamp.
- The workspace summary rail now includes local project controls: save, rename, load, duplicate, and delete/archive with confirmation.
- The summary rail shows `Unsaved changes` / `Saved` and a `Last saved` timestamp.
- Reloading the planner workspace for a system restores the latest active local project into the editable Build Plan through the existing `initialRequest` path.

Safety boundaries in Stage 15G:

- Persistence is local-only. No backend schema, account sync, collaboration, cloud sync, imports, EDMC ingestion, hauling/material execution, scoring, CP/economy/buildability/service mechanics, optimiser behavior, Search Tuning, Observed Evidence, Validation, or primary-port truth handling changed.
- Saving/loading projects does not auto-run Preview, auto-generate Suggested Builds, auto-import layout, mutate evidence, or run validation.

Test coverage added/updated in Stage 15G:

- Store tests cover save/load shape, rename, duplicate, archive, active project filtering, selected body assignments, and unsaved snapshot matching.
- Workspace tests cover save, rename, duplicate, archive confirmation, unsaved/saved indicator, and reload restoring a saved plan through the planner adapter.

Deferred after Stage 15G:

- Backend persistence and migration remain future work after the project model stabilises.
- Stage 15H should move Evidence and Validation into drawers/modes.

### Stage 15H - Evidence / Validation Drawers

Stage 15H moves Observed Evidence and Validation out of the always-visible planner stack and into explicit workspace drawers.

Current Stage 15H status:

- `SimulationPreview` now renders compact Evidence / Validation drawer controls after Preview Result.
- Observed Evidence and Validation panels mount only when their drawer is opened.
- Compact status badges show Evidence as manual and Validation as needing preview, preview ready, or preview stale.
- Each drawer includes a short mismatch / needs-observation summary in a collapsed details block before the existing panel.
- The existing Observed Evidence and Validation components are reused unchanged inside drawers.

Safety boundaries in Stage 15H:

- Opening/closing drawers does not run Preview, generate Suggested Builds, import layout, save projects, mutate the Build Plan, or change backend mechanics.
- Validation still does not auto-run without an explicit preview result; the compare query only mounts when the Validation drawer is opened.
- Observed Evidence CRUD semantics and Validation compare/review semantics remain unchanged.

Test coverage added/updated in Stage 15H:

- Simulation Preview tests cover drawer buttons, evidence drawer open/close, validation drawer open/close, existing Evidence/Validation panel accessibility, no-preview validation empty state, and no compare call until the Validation drawer is explicitly opened.

Deferred after Stage 15H:

- Stage 15I should finish QA, accessibility, copy cleanup, and responsive hardening.

### Stage 15I - Workspace QA / Accessibility / Regression Hardening

Stage 15I closes the topology-first planner workspace pass with focused QA and copy hardening.

Current Stage 15I status:

- The dedicated planner route header now describes the surface as the Stage 15 workspace instead of the earlier topology-only milestone.
- User-facing planner copy no longer exposes raw body IDs by default when body metadata is missing.
- Structure picker, body layout summaries, optimiser placement summaries, and optimiser comparison deltas use compact body-reference fallback copy.
- Existing component tests cover the updated fallback labels.

Safety boundaries in Stage 15I:

- Stage 15I does not change backend mechanics, scoring, CP/economy/buildability/service logic, optimiser generation/ranking, Simulation Preview scoring, Observed Evidence semantics, Validation behavior, imports, persistence semantics, EDMC ingestion, hauling/material execution, or primary-port truth handling.
- No auto-preview, auto-generation, auto-validation, auto-import, or autosave behavior is introduced.

Test coverage added/updated in Stage 15I:

- Structure picker fallback copy.
- Body layout fallback copy.
- Optimiser placement fallback copy.
- Existing workspace route tests remain in place for project controls and planner navigation.

Deferred after Stage 15I:

- Backend saved-project persistence and migration.
- Stage 16 colony role and colony planet modelling.
- Additional visual regression and responsive screenshot coverage after the role model surfaces are designed.

## Stage 16 - Colony Role / Colony Planet Model

Stage 16 starts the next planner layer: role intent. Stage 15 made the workspace topology-first and project-capable; Stage 16 defines how ED-Finder should talk about what each body is for without changing game mechanics or pretending user intent is observed truth.

### Stage 16A - Colony Role Model Planning Report

Stage 16A is documentation only and is captured in `docs/colonisation-redesign/stage-16-colony-role-model-plan.md`.

Current Stage 16A status:

- Defines why the planner needs colony roles now that it can show bodies, placements, and saved projects.
- Separates planned roles, observed roles, user-declared roles, and inferred roles.
- Defines role boundaries for Colony Anchor, Colony Planet / Core Body, Main Station Body, Primary Port Body, Industrial Core, Extraction Body, Tourism/Agriculture Body, Military/Security Body, Support Body, and Expansion Reserve.
- Captures role conflicts, overlap, confidence labels, badges, persistence needs, saved-project migration, future optimiser integration, and Evidence/Validation integration.

Safety boundaries in Stage 16A:

- No code implementation.
- No backend mechanics, scoring, CP/economy/buildability/service logic, optimiser generation/ranking, Simulation Preview scoring, Observed Evidence semantics, Validation behavior, imports, persistence semantics, EDMC ingestion, hauling/material execution, or primary-port truth handling changed.
- Primary-port role remains evidence-backed guidance only; users must not be able to set it arbitrarily as truth.

Deferred after Stage 16A:

- Role data model and local project migration design.
- Role badges in the topology workspace.
- Explicit user-declared role controls.
- Role conflict/overlap guidance.
- Evidence/Validation role review integration.
- Suggested Build role explanations and explicit load-time role acceptance.

### Stage 16B - Workspace Cleanup Before Role Implementation

Stage 16B is a cleanup and hardening stage before full colony-role implementation. It does not add role editing, backend persistence, or mechanics changes.

Current Stage 16B status:

- `ColonyPlannerWorkspace.tsx` is reduced to the route/loading/error container.
- Workspace layout and planner mounting moved to `WorkspaceGrid.tsx`.
- Header rendering moved to `WorkspaceHeader.tsx`.
- Saved project lifecycle state moved to `useWorkspaceProjectState.ts`.
- The right rail is split into compact Project, Plan Health, Selection, Architect, Workspace Modes, and current save-state cards.
- Saved project copy now clearly states that projects are stored locally in this browser, are not cloud-synced, and may be removed by clearing browser storage.
- Architect copy is derived from the current local plan snapshot and says `Architect flag not recorded` when no supported observation exists.
- Evidence and Validation drawer controls are available from the persistent summary rail while the drawer content remains in the central planner.
- A compact `What next?` strip and first-run start panel give the central workspace clearer next actions without rewriting `SimulationPreview`.
- Target archetype labels are humanized for user-facing planner copy.
- Suggested Builds copy now explains that frontend usefulness filtering may hide trivial backend candidates.
- Frontend trivial Suggested Build detection now considers labels, tags, rationale, assumptions, and placement/template ids more defensively while keeping clear-role starters visible.

Safety boundaries in Stage 16B:

- No full colony role editing.
- No backend/cloud persistence.
- No Architect Slot Survey storage.
- No primary-port editing or arbitrary primary-port truth.
- No backend mechanics, scoring, CP/economy/buildability/service logic, optimiser generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence semantics, Validation behavior, imports, EDMC ingestion, hauling/material workflows, or automatic Preview/Suggested Build generation changed.

Test coverage added/updated in Stage 16B:

- Workspace still renders through the route container.
- Summary rail cards render separately.
- User-facing workspace UI avoids internal stage/roadmap language.
- Local-only persistence warning appears.
- Plan health counts and humanized archetype labels are covered.
- Selected body shows the central planning focus banner.
- Summary rail Evidence/Validation mode controls update drawer state without running planner side effects.
- Suggested Build filtering covers colony-ship-only, colony ship plus generic outpost/station, duplicate plans, and useful single-placement role starters.

Deferred after Stage 16B:

- Full colony role data model and migration.
- Role badges and explicit user-declared role controls.
- Durable/backend saved project persistence.
- Project export/import and migration from localStorage.

## Stage 17 - Durable Colony Project Persistence

Stage 17 is pencilled in for durable saved Colony Project persistence after the role model stabilises.

Scope to cover:

- backend/cloud project persistence
- explicit project export/import JSON
- migration from `localStorage` saved projects
- account/device sync if the product later supports accounts
- preview snapshot persistence
- observed evidence snapshot persistence
- validation snapshot persistence
- migration safeguards for role assignments and primary-port evidence

Safety boundaries for Stage 17:

- No silent autosave without clear UX.
- No primary-port truth editing.
- No loss of local-only projects during migration.
- No mechanics/scoring changes bundled with persistence work.
