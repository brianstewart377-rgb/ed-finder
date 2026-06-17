# Stage 18H.2 — Read-Only Backend Warehouse Evidence Endpoint

## Purpose

Stage 18H.2 turns the `warehouse_planner_evidence/v1` contract from Stage 18H.1
into a planner-safe backend endpoint scaffold.

This slice adds a dedicated read-only endpoint for per-system warehouse planner
evidence without changing planner truth semantics, enabling admin access, or
authorizing any write lane.

## Route

`GET /api/colony-planner/system/{id64}/warehouse-planner-evidence`

The route is intentionally hidden from OpenAPI for now, matching the earlier
Stage 20B provenance cockpit surface while the contract remains a controlled
follow-on path.

## Backend Shape

The endpoint returns `warehouse_planner_evidence/v1` and is implemented by:

- `apps/api/src/warehouse_planner_evidence.py`
- `apps/api/src/warehouse_planner_evidence_models.py`
- `apps/api/src/routers/warehouse_planner_evidence.py`

The builder is conservative by design:

1. it reads the existing read-only warehouse status artifact, if configured,
   using the same sanitization boundary as the admin/operator warehouse status
   view
2. it extracts only safe artifact freshness and source-run metadata
3. it publishes fixture-backed per-system examples for a limited safe surface
4. it returns `availability = "unavailable"` for every system that does not
   have a safe per-system mapping

## What It Does Not Do

This slice does **not**:

- expose admin-only warehouse details
- publish raw warehouse rows
- infer per-system evidence from aggregate-only counters
- mutate planner state
- authorize database writes, canonical apply, rebaseline, or scheduler work
- change the current planner UI fetch path

## Fallback Semantics

When the warehouse artifact is unavailable, the endpoint still returns a valid
`warehouse_planner_evidence/v1` object with:

- `availability = "unavailable"`
- `report_only = true`
- empty `items`
- source/freshness metadata kept conservative
- warnings that explain why the planner must remain on fallback

This lets Stage 18H.3 safely query the endpoint and fall back to the current
provenance bridge whenever no trusted per-system evidence is published.

## Follow-on

The next slices after this endpoint scaffold are:

1. Stage 18H.3 — planner integration that fetches this endpoint first and falls
   back to the current provenance bridge when evidence is unavailable
2. Stage 18H.4 — UX clarification for freshness, review status, and source
   posture once the planner is reading the dedicated contract
