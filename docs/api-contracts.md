# API Contracts

ED-Finder keeps the backend, frontend, and EDDN worker as separate apps. They should stay separate. The shared contract between them is the HTTP API.

## Source Of Truth

The backend owns API response shapes through Pydantic models in `apps/api/src/models.py`.

For the simulation endpoints, the important response models are:

- `SlotPredictionResponse`
- `BuildabilityResponse`
- `SimulationSummaryResponse`
- `BuildabilityBottleneck`
- `BuildabilityOpportunity`
- `RecommendedBuildStep`

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

## Change Workflow

1. Change or add the backend Pydantic model.
2. Make the route return that exact model through `response_model=...`.
3. Regenerate frontend OpenAPI types.
4. Update `frontend-v2/src/lib/api.ts` if a new endpoint or helper is needed.
5. Update frontend components to use generated types and central client helpers.
6. Add or update contract tests so old field names cannot silently return.

