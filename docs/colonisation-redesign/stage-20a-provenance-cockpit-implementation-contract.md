# Stage 20A - Provenance Cockpit Implementation Contract

## Purpose

Stage 20A turns the merged Stage 20 planning baseline into a concrete
implementation contract that later PRs can execute without reopening Stage 19
production decisions.

This checkpoint remains docs/static-only. It does not add feature delivery, DB
commands, Stage 19 operator commands, canonical apply, rebaseline,
scheduler/service enablement, source acquisition, or production-like DB
execution.

## Primary Contract Set

Stage 20A primary contract set: `System provenance cockpit summary contract`.

This contract defines the first read-only aggregate surface that Stage 20B can
implement. Its job is to let the planner UI explain:

- current source-run evidence identity and freshness;
- warehouse/reconciliation freshness and review state;
- planner evidence posture and user-visible trust boundaries;
- deferred-production guardrails that remain false;
- stale, missing, and unknown evidence states without coercing them to success.

## Contract Scope

The first contract slice is intentionally bounded to one system-level aggregate
response plus fixture-backed UI rendering. It does not introduce write actions,
background tasks, or live operator execution.

The contract response schema version is:

`stage20a_provenance_cockpit/v1`

## Backend Ownership

### Existing supporting readers

These files already own the read-only inputs that Stage 20B should compose
rather than re-invent:

| Ownership | Current file | Role in Stage 20A contract |
| --- | --- | --- |
| Source-run/operator visibility endpoints | `apps/api/src/routers/operator.py` | Existing read-only admin routes for source-run, artifact, bridge, staging-impact, and safety-gate summaries. |
| Source-run redaction/view models | `apps/api/src/operator_visibility.py` | Sanitized source-run, artifact, bridge, staging-impact, and safety-gate summaries. |
| Enrichment and warehouse status sanitization | `apps/api/src/enrichment_operator_status.py` | Safe snapshot reduction for enrichment status and warehouse reconciliation artifacts. |
| System identity/body/station read models | `apps/api/src/routers/systems.py` | Existing system-scoped planner identity, body, and station context. |
| Planner/simulation summary read models | `apps/api/src/routers/simulation.py` | Existing planner-facing summary context that Stage 20 later needs to align with provenance surfaces. |
| Frontend wire type source of truth | `apps/api/src/models.py` | Current Pydantic/OpenAPI ownership point for response-model-backed wire types. |

### Planned Stage 20B aggregation owner

Stage 20B should introduce one read-only aggregation endpoint owned by a
dedicated route module:

- planned route file: `apps/api/src/routers/provenance_cockpit.py`
- planned response-model home: `apps/api/src/models.py` or a narrowly scoped
  `apps/api/src/provenance_contract_models.py`

Stage 20A does not create those files yet. It fixes the ownership decision so
the next PR does not scatter provenance aggregation across unrelated routers.

## Frontend Ownership

### Existing owning surfaces

The first provenance cockpit UI should be anchored in the existing simulation
workspace rather than a parallel planner shell:

| Ownership | Current file | Role in Stage 20A contract |
| --- | --- | --- |
| Workspace shell handoff | `frontend/src/features/system-detail/SimulationPreviewPanel.tsx` | Current entry point that mounts the planner workspace. |
| Workspace state and mode switching | `frontend/src/features/system-detail/simulation-preview/SimulationPreview.tsx` | Current owner of build-plan, evidence, suggested-builds, preview, and validation mode wiring. |
| Evidence workspace surface | `frontend/src/features/system-detail/simulation-preview/EvidenceWorkspaceView.tsx` | Natural location for the first provenance-backed evidence/status panel. |
| Validation surface adjacency | `frontend/src/features/system-detail/simulation-preview/ValidationWorkspaceView.tsx` | Keeps provenance review separate from validation decisions while sharing trust language. |
| API fetch wrapper | `frontend/src/lib/api.ts` | Current owner for adding the Stage 20B read-only fetch wrapper. |
| Frontend wire types | `frontend/src/types/api.ts` | Current owner for generated/manual wire types and friendly aliases. |

### Planned Stage 20B UI owner

Stage 20B should add one dedicated panel component under:

- `frontend/src/features/system-detail/simulation-preview/provenance/ProvenanceCockpitPanel.tsx`

That panel should be rendered from `EvidenceWorkspaceView.tsx` first. It must
not become a new planner root or a second simulation shell.

## Response Shape

The first response must stay compact, reviewable, and safe to fixture. The
Stage 20B implementation should expose the following top-level contract:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Fixed schema identifier `stage20a_provenance_cockpit/v1`. |
| `system` | object | System identity needed to label the cockpit surface. |
| `provenance_summary` | object | High-level freshness/trust posture for source-run, warehouse, planner, and guardrail state. |
| `evidence_panels` | object | Compact read-only panel payloads for source-run, warehouse, and planner evidence summaries. |
| `guardrails` | object | Explicit booleans for deferred production lanes that remain disabled/incomplete. |
| `warnings` | array | User-visible stale/missing/unknown evidence warnings. |
| `ui_hints` | object | Non-authoritative presentation hints such as severity labels or empty-state copy keys. |

### Required guardrail booleans

The `guardrails` object must explicitly carry:

- `stage19_paused`
- `stage19_production_activation_complete`
- `next_stage19_write_lane_authorized`
- `canonical_apply_complete`
- `rebaseline_complete`
- `scheduler_enabled`
- `db_writes_authorized`
- `stage19_operator_commands_authorized`

All of those remain `false` except `stage19_paused`, which remains `true`.

### Required evidence states

Every panel payload must support three safe states:

- `available`
- `stale`
- `unknown`

Missing or stale evidence must never be coerced to fresh/complete. Unknown
values remain unknown.

## Fixture Plan

Stage 20A commits three fixture payloads under `tests/fixtures/stage20a/`:

1. `provenance_cockpit_happy_path.json`
2. `provenance_cockpit_stale_evidence.json`
3. `provenance_cockpit_unknown_evidence.json`

These fixtures are non-secret and path-safe. They use redacted artifact names,
compact counters, and explicit guardrail booleans so the next UI/API PR can
implement against stable examples before touching live reads.

## Runtime Validation Plan

Stage 20A does not add a runtime validation library, but it does lock the
handoff points:

- backend response model: Pydantic response model in `apps/api/src/models.py`
  or a narrowly scoped provenance contract models module;
- generated frontend wire type: `frontend/src/types/api.gen.ts`;
- frontend ergonomic wrapper type: `frontend/src/types/api.ts`;
- fetch wrapper entry: `frontend/src/lib/api.ts`;
- component boundary for the first user-visible slice:
  `frontend/src/features/system-detail/simulation-preview/EvidenceWorkspaceView.tsx`.

If runtime guards are added in Stage 20B, they must validate only the
provenance cockpit response and must not broaden into generic app-wide schema
churn.

## Acceptance Criteria

Stage 20A is complete when:

- one primary contract set is named;
- backend and frontend ownership are tied to concrete repo files;
- the aggregate response shape is defined with fixed top-level fields;
- fixture payloads exist for happy-path, stale, and unknown evidence states;
- guardrail booleans keep Stage 19 production activation, canonical apply,
  rebaseline, scheduler/service enablement, DB writes, and Stage 19 operator
  commands unauthorized;
- the contract leaves a bounded Stage 20B slice that can be reviewed without
  inventing additional planning work first.

## Explicit Non-Goals

Stage 20A does not authorize:

- new API endpoints in this PR;
- frontend feature delivery in this PR;
- DB reads or writes from new request handlers;
- operator command execution;
- source acquisition or staging-loader execution;
- migrations, canonical promotion, rebaseline, or scheduler activation;
- automatic Simulation Preview execution;
- automatic Suggested Build generation/loading;
- broad map/planner rewrites.

## Next Checkpoint Handoff

The next checkpoint after this contract is:

`Stage 20B - Read-only evidence and status surfaces`

Stage 20B should implement only the first bounded slice described here:

- one read-only provenance cockpit aggregation route;
- one Evidence Workspace panel;
- fixture-backed UI tests and static contract checks;
- no write path and no Stage 19 production activation.

