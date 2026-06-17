# Stage 20B - Read-only Evidence And Status Surfaces

## Purpose

Stage 20B delivers the first user-visible provenance cockpit slice defined by
 the Stage 20A contract. This checkpoint is implementation work, but it remains
 bounded to read-only status surfaces.

It does not authorize DB writes, Stage 19 operator execution, canonical apply,
rebaseline, scheduler/service activation, source acquisition, or production-like
DB access.

## Delivered Slice

Stage 20B delivers one fixture-backed aggregation endpoint and one Evidence
Workspace panel:

- backend aggregation route:
  `apps/api/src/routers/provenance_cockpit.py`
- backend contract/builders:
  `apps/api/src/provenance_cockpit.py`
  `apps/api/src/provenance_cockpit_models.py`
- frontend API helper:
  `frontend-v2/src/lib/api.ts`
- frontend panel:
  `frontend-v2/src/features/system-detail/simulation-preview/provenance/ProvenanceCockpitPanel.tsx`
- workspace integration point:
  `frontend-v2/src/features/system-detail/simulation-preview/EvidenceWorkspaceView.tsx`

## Bounded Read-only Behavior

The new endpoint is fixture-backed and authority-backed. It uses the preserved
Stage 19AV proof and current authority booleans to surface:

- source-run identity and staged-row counts;
- warehouse freshness posture;
- planner evidence posture;
- warnings for stale or unknown states;
- explicit deferred-production guardrails.

The endpoint remains hidden from OpenAPI in this checkpoint to avoid unrelated
type-generation churn while the contract is still being exercised by the first
user-visible surface.

## Route Contract

Route:

`GET /api/colony-planner/system/{id64}/provenance-cockpit`

The response uses schema version:

`stage20a_provenance_cockpit/v1`

Supported fixture-safe states:

- `available`
- `stale`
- `unknown`

Unknown values remain unknown. Stale values remain stale. Neither state
authorizes planner mutation, warehouse writes, or production activation.

## Frontend Surface

The Evidence Workspace now shows a dedicated Provenance cockpit panel before the
Observed Evidence panel. It renders:

- source-run summary;
- planner evidence summary;
- warehouse evidence card reuse in report-only mode;
- explicit guardrail booleans;
- stale and unknown warnings without coercing them to success.

## Validation

Stage 20B adds focused tests for:

- backend fixture-backed provenance summary behavior;
- authority and guardrail preservation;
- frontend read-only API helper;
- frontend panel rendering across available, stale, and unknown states.

## Non-goals Preserved

Stage 20B still does not implement:

- live DB reads beyond existing checkpoint evidence;
- DB writes of any kind;
- Stage 19 operator command execution;
- canonical promotion;
- rebaseline;
- scheduler/service activation;
- source acquisition or staging-loader runs;
- automatic Simulation Preview execution;
- automatic Suggested Build generation or loading.

## Next Checkpoint

The next checkpoint remains:

`Stage 20C - Map planning surface foundation`
