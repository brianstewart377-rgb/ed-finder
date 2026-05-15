# API Contracts

ED-Finder keeps the backend, frontend, and EDDN worker as separate apps. They should stay separate. The shared contract between them is the HTTP API.

## Source Of Truth

The backend owns API response shapes through Pydantic models in `apps/api/src/models.py`.

For the simulation and optimiser endpoints, the important response models are:

- `SlotPredictionResponse`
- `BuildabilityResponse`
- `SimulationSummaryResponse`
- `BuildabilityBottleneck`
- `BuildabilityOpportunity`
- `RecommendedBuildStep`
- `OptimiserCandidatesRequest`
- `OptimiserCandidate`
- `OptimiserCandidatesResponse`

Frontend code should not manually guess these response shapes. When backend fields change, regenerate the frontend OpenAPI types and update the central API client if needed.

## Frontend Types

The current web app lives in `frontend-v2`. Generate types from the running FastAPI OpenAPI document:

```powershell
cd frontend-v2
$env:VITE_OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"
yarn types:gen
```

If dependencies are missing:

```powershell
cd frontend-v2
npm install -D openapi-typescript
```

If the API is not already running locally, start the backend first. In Docker-based deployments:

```bash
cd /opt/ed-finder
docker compose up -d postgres redis api
```

Then run the type generation command from `frontend-v2`.

## Frontend API Calls

Frontend calls for simulation data should go through `frontend-v2/src/lib/api.ts`.

Use the central helper functions:

- `getSlotPredictions(id64)`
- `getBuildability(id64, archetype?)`
- `getSimulationSummary(id64, archetype?)`

Stage 5A adds `POST /api/optimiser/candidates`, which accepts `OptimiserCandidatesRequest` with `system_id64`, preferred `target_archetype`, compatibility `target_archetype_key`, `max_candidates` bounded to 1-10 by the public API model, `preferred_body_ids`, `allow_estimated_data`, `run_preview`, and optional Stage 5B `include_ranking`. The endpoint returns `OptimiserCandidatesResponse`, containing a bounded candidate envelope with `system_id64`, `target_archetype`, `candidate_count`, `candidates`, `warnings`, `assumptions`, and nullable top-level `ranking`. Frontend integration should add a central API helper rather than calling this route directly from components.

Avoid scattered raw `fetch()` calls for these endpoints. The central client is the only place that should know endpoint paths.

## Canonical Field Names

The frontend should consume the backend field names exactly:

- `estimated_surface_slots`
- `estimated_orbital_slots`
- `estimated_ground_slots`
- `slot_confidence`
- `slot_confidence_label`
- `slot_source`
- `build_complexity`
- `bottlenecks`
- `opportunities`
- `recommended_build_order`

Do not introduce frontend-only names such as `surface_slots`, `orbital_slots`, or `confidence` for these API responses unless they are deliberately mapped in one central API adapter.

For optimiser candidates, clients should consume the backend field names exactly:

- `candidate_id`
- `label`
- `target_archetype`
- `strategy`
- `placements`
- `rationale`
- `warnings`
- `assumptions`
- `tags`
- `preview_summary`

The optimiser `preview_summary` is deliberately lightweight and optimiser-specific. It is not a full Simulation Preview response and should not be treated as the source of detailed mechanics explanation. Candidate dedupe uses ordered placement fingerprints because build order affects CP timing and repair suggestions.

For Stage 5B ranking, clients request `include_ranking=true`. Ranking is returned as a top-level `ranking` object with `target_archetype`, `ranked_candidates`, `warnings`, and `assumptions`. Each ranked entry references `candidate_id` and includes `rank`, `rank_score`, `rank_tier`, and `rank_breakdown`; it must not duplicate full candidate objects or add rank fields to candidates. The ranking breakdown includes `alignment_component` for the top-two/economy alignment contribution. When `include_ranking=false`, candidate ordering and shape remain the Stage 5A response behaviour.

## Change Workflow

1. Change or add the backend Pydantic model.
2. Make the route return that exact model through `response_model=...`.
3. Regenerate frontend OpenAPI types.
4. Update `frontend-v2/src/lib/api.ts` if a new endpoint or helper is needed.
5. Update frontend components to use generated types and central client helpers.
6. Add or update contract tests so old field names cannot silently return.


## Stage 6A Observed Facts API

Stage 6A adds a backend-only observed-facts shelf. An **observation** is manually supplied evidence about something a player saw; it is not a prediction, it is not an optimiser input, and it does not mutate Simulation Preview scoring or mechanics. Predicted-vs-observed comparison is intentionally reserved for later Stage 6 work.

Stage 6A is a **passive evidence shelf**: observations are recorded separately from predictions and **do not mutate** optimiser ranking, candidate generation, Simulation Preview scoring, CP / economy / service / buildability mechanics, or any existing simulation response field. Static safety tests assert that the optimiser, simulation, mechanics, and their routers never import the observation store.

| Endpoint | Purpose | Response Model |
|---|---|---|
| `POST /api/observations/facts` | Create one observed fact. | `ObservedFactResponse` |
| `GET /api/observations/facts?system_id64=123` | List observed facts for a system, with optional filters. | `ObservedFactListResponse` |
| `GET /api/observations/facts/{observation_id}` | Retrieve one observed fact by ID. | `ObservedFactResponse` |
| `PATCH /api/observations/facts/{observation_id}` | Update allowed observed-fact fields. | `ObservedFactResponse` |
| `DELETE /api/observations/facts/{observation_id}` | Hard-delete one observed fact for Stage 6A. | `ObservedFactDeleteResponse` |

The list endpoint supports `fact_type`, `subject_type`, `status`, `target_archetype`, `build_fingerprint`, `simulation_fingerprint`, `limit`, and `offset` query filters.

### Accepted and reserved sources

The Stage 6A public API accepts only:

- `manual`
- `test_fixture`

`imported` and `inferred` are present in the `ObservationSource` enum vocabulary but are **reserved for later stages** (EDMC/journal ingestion in 6B, automated inference in 6C). Stage 6A request validation rejects them with HTTP 422. Future stages will define provenance and trust rules before lifting that restriction.

### Summary semantics

`ObservedFactListResponse.summary` describes the **full filtered result set**, not just the paginated page returned in `facts`. So if `limit=1` is sent against three matching observations, `facts` has one entry, `total` is `3`, and `summary.total_count` / `summary.by_fact_type` / `summary.by_status` / `summary.by_confidence` all count all three. The store provides a dedicated `summarise_observed_facts_for_filter` query for this; it shares the same filter clause as the list query so total and summary always describe the same rows.

### Nullable subject_id

`subject_id` may be `null` for system-level or build-level notes that do not target a specific service, economy, facility, or other subject (for example a free-form `note` fact_type). The Stage 4D `subject_id NOT NULL` constraint is relaxed in `sql/018_observed_facts_stage6a.sql`, and the Stage 6A store preserves `None` end-to-end without coercing it to an empty string.

### Legacy compatibility columns

`observed_facts` existed before Stage 6A with Stage 4D comparison columns. The Stage 6A store keeps both the new and legacy columns populated on every write so existing Stage 4D readers continue to see consistent rows:

| Legacy column | New Stage 6A column |
|---|---|
| `area` | `fact_type` |
| `source_type` | `source` |
| `observed_value` | `observed_value_json` |
| `facility_id` | `facility_template_id` |
| `body_id` | `local_body_id` |

A later migration will normalise or drop these duplicate columns; until then the duplication is deliberate and documented in `apps/api/src/observations/store.py` and `sql/018_observed_facts_stage6a.sql`.

Example create request:

```json
{
  "system_id64": 123,
  "source": "manual",
  "fact_type": "service_presence",
  "subject_type": "service",
  "subject_id": "market",
  "status": "observed_present",
  "service_id": "market",
  "observed_value": { "present": true },
  "expected_value": { "present": false },
  "confidence": "high",
  "notes": "Observed after construction tick.",
  "target_archetype": "trade_logistics",
  "tags": ["service", "tick"],
  "metadata": { "source_screen": "station services" }
}
```

Example response:

```json
{
  "observation_id": "obs_...",
  "system_id64": 123,
  "created_at": "2026-05-14T13:00:00+00:00",
  "updated_at": null,
  "source": "manual",
  "fact_type": "service_presence",
  "subject_type": "service",
  "subject_id": "market",
  "status": "observed_present",
  "observed_value": { "present": true },
  "expected_value": { "present": false },
  "confidence": "high",
  "notes": "Observed after construction tick.",
  "build_fingerprint": null,
  "simulation_fingerprint": null,
  "target_archetype": "trade_logistics",
  "facility_template_id": null,
  "local_body_id": null,
  "service_id": "market",
  "economy": null,
  "tags": ["service", "tick"],
  "metadata": { "source_screen": "station services" }
}
```

The write models validate enum values, require positive `system_id64`, normalise/dedupe/cap tags, require object-shaped metadata, and require structured identifiers for the most common typed facts: `service_presence` needs `service_id`, `economy_presence` needs `economy`, and `facility_state` needs `facility_template_id`. These checks keep observations structured without claiming that one observed fact proves or disproves a mechanics rule.

Observations do **not** change optimiser ranking, candidate generation, Simulation Preview scoring, CP/economy/service/buildability mechanics, or existing simulation response fields. They are stored evidence for future manual-entry UI and predicted-vs-observed comparison stages.

## Stage 6B Frontend Observed Evidence Integration

Stage 6B adds the frontend integration on top of the Stage 6A API. It introduces frontend types, central API helpers, and an Observed Evidence panel inside Colony Planner. It does **not** change any backend contract.

Frontend types are declared in `frontend-v2/src/types/api.ts` and mirror the Stage 6A wire shapes:

- `ObservationSource`
- `ObservedFactType`
- `ObservedSubjectType`
- `ObservedStatus`
- `ObservedConfidence`
- `ObservedJsonValue`
- `ObservedFact`
- `ObservedFactCreateRequest`
- `ObservedFactUpdateRequest`
- `ObservationFactSummary`
- `ObservedFactListResponse`
- `ObservedFactDeleteResponse`
- `ListObservedFactsParams`

Central API client helpers in `frontend-v2/src/lib/api.ts` follow the existing `jsonFetch` style and target the Stage 6A endpoints:

- `listObservedFacts(params)` → `GET /api/observations/facts?system_id64=...&fact_type=...&status=...`
- `createObservedFact(request)` → `POST /api/observations/facts`
- `updateObservedFact(observationId, request)` → `PATCH /api/observations/facts/{observation_id}`
- `deleteObservedFact(observationId)` → `DELETE /api/observations/facts/{observation_id}`

The Stage 6B UI only ever sends `source: 'manual'` in create requests. `imported` and `inferred` remain reserved Stage 6A enum values and are intentionally not exposed as create-form source options; the manual UI does not provide any control that could pick them.

Stage 6B is a **passive** integration: the Observed Evidence panel does not feed observed facts back into `simulateBuild`, `fetchOptimiserCandidates`, optimiser ranking, candidate generation, or Simulation Preview scoring. The simulation and optimiser request payloads remain unchanged. Predicted-vs-observed comparison is reserved for Stage 6C, and validation rendering for Stage 6D.

## Stage 6C Predicted-vs-Observed Comparison

Stage 6C adds a **comparison-only** endpoint that compares a Simulation Preview prediction against persisted Stage 6A observed facts and returns a structured per-row comparison plus a top-level summary. Stage 6C is the engine; Stage 6D will render its output in the validation UI.

Core principle: **prediction is what ED-Finder thinks should happen, observation is what a user actually saw, comparison is a structured diff between the two.** Stage 6C compares; it does not change predictions, scoring, ranking, candidate generation, or Simulation Preview output.

### Endpoint

| Method + Path | Purpose | Response |
|---|---|---|
| `POST /api/observations/compare` | Run deterministic comparison engine over a prediction and observed-facts list. | `PredictionObservationCompareResponse` |

The endpoint supports two modes:

- **Mode A** — caller supplies `prediction`, `system_id64`, and `target_archetype`; the backend loads observed facts for `system_id64` (and optionally `target_archetype`) from the persisted Stage 6A store, up to `fact_load_limit`.
- **Mode B** — caller supplies `observed_facts` in addition to the other fields. The backend uses the supplied list verbatim and does NOT query the database for facts.

Validation: `system_id64` must be `> 0`, `prediction` must be a JSON object (lists / strings / numbers are rejected with HTTP 422), `observed_facts` (when supplied) must be a list of fact-shaped objects.

### Response vocabulary

Per-row `status` (`PredictionObservationComparisonResponse.status`):

- `confirmed` — observation aligns with prediction.
- `contradicted` — observation conflicts with prediction (subject to severity clamping by observation `confidence`).
- `predicted_only` — prediction includes the subject but no observation has been recorded for it.
- `observed_only` — observation records the subject but the prediction does not.
- `unknown` / `unverified` — observation is not strong enough to confirm or contradict.

`severity` (`info` / `low` / `medium` / `high`) is clamped by the observation's confidence: a `low`-confidence observation can never produce a `high`-severity contradiction; a `medium`-confidence observation clamps `high` base severities down to `medium`.

`PredictionObservationComparisonSummaryResponse.status` (the top-level summary status):

- `no_observations` — system has no observed evidence yet.
- `confirmed` — all comparable observations match the prediction.
- `needs_review` — only contradictions, no confirmations.
- `mixed` — at least one confirmation and at least one contradiction.
- `insufficient_evidence` — observations exist but none are strong enough to confirm or contradict.

`confidence_impact` (`none` / `strengthened` / `weakened` / `mixed` / `insufficient_evidence`) is a UI hint only. Stage 6C does NOT plumb confidence impact back into Simulation Preview scoring or optimiser ranking.

### Example request (Mode A)

```json
{
  "system_id64": 123,
  "target_archetype": "trade_logistics",
  "prediction": {
    "services": { "refining": { "status": "active" } },
    "economy_composition": { "extraction": 0.7 },
    "economy_order": ["extraction"],
    "cp": { "yellow_cp_final": 12, "green_cp_final": 4 },
    "final_score": 88.0,
    "confidence": "high"
  }
}
```

### Example response

```json
{
  "system_id64": 123,
  "target_archetype": "trade_logistics",
  "generated_at": "2026-05-15T12:00:00+00:00",
  "summary": {
    "status": "confirmed",
    "observed_facts_count": 1,
    "compared_predictions_count": 2,
    "confirmed_count": 1,
    "contradicted_count": 0,
    "observed_only_count": 0,
    "predicted_only_count": 1,
    "unknown_count": 0,
    "unverified_count": 0,
    "confidence_impact": "strengthened",
    "summary": "Observations support the prediction: 1 confirmed, 1 predicted-only."
  },
  "comparisons": [
    {
      "comparison_id": "service:refining",
      "area": "service",
      "subject_type": "service",
      "subject_id": "refining",
      "predicted_value": "active",
      "observed_value": { "present": true },
      "status": "confirmed",
      "severity": "info",
      "confidence": "high",
      "reason": "Predicted active and observed present (status=active).",
      "recommended_action": null,
      "evidence": [
        {
          "observation_id": "obs_abc",
          "fact_type": "service_presence",
          "subject_type": "service",
          "subject_id": "refining",
          "status": "observed_present",
          "confidence": "high",
          "observed_value": { "present": true },
          "expected_value": null,
          "notes": null
        }
      ],
      "prediction_source": "services"
    }
  ],
  "warnings": [],
  "assumptions": []
}
```

### Passivity guarantee

`POST /api/observations/compare` is read-only over its inputs. It does not import or invoke any simulation, optimiser, ranking, or candidate-generation code, and it does not mutate persisted observations. The comparison engine is pure and deterministic given its inputs (`generated_at` is the only time-dependent field and is injectable for tests). A static passivity test in the test suite asserts that simulation/optimiser/ranking source files do not import `observations.comparison_engine` or `observations.store`.

Stage 6C tests live in `tests/test_stage6c_comparison.py`. The legacy Stage 4D in-pipeline comparison code in `apps/api/src/observations/comparison.py` and its tests in `tests/test_observation_comparison.py` remain untouched.
