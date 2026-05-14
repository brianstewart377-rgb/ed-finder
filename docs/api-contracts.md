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

Stage 5A adds `POST /api/optimiser/candidates`, which accepts `OptimiserCandidatesRequest` with `system_id64`, preferred `target_archetype`, compatibility `target_archetype_key`, `max_candidates` bounded to 1-10 by the public API model, `preferred_body_ids`, `allow_estimated_data`, and `run_preview`. The endpoint returns `OptimiserCandidatesResponse`, containing a bounded candidate envelope with `system_id64`, `target_archetype`, `candidate_count`, `candidates`, `warnings`, and `assumptions`. Frontend integration should add a central API helper rather than calling this route directly from components.

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

## Change Workflow

1. Change or add the backend Pydantic model.
2. Make the route return that exact model through `response_model=...`.
3. Regenerate frontend OpenAPI types.
4. Update `frontend-v2/src/lib/api.ts` if a new endpoint or helper is needed.
5. Update frontend components to use generated types and central client helpers.
6. Add or update contract tests so old field names cannot silently return.

