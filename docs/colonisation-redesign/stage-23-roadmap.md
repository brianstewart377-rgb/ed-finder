# Stage 23 Roadmap

## Purpose

Stage 23 is the next post-Stage-22 control sequence. Its goal is to move the
planner evidence path from fixture-backed or aggregate-only summaries toward a
first bounded live per-system evidence provider while preserving all Stage 22
read-only and safety boundaries.

Stage 23 is not a Stage 19 reactivation programme. It does not authorize
planner mutation, canonical apply, rebaseline, scheduler/service enablement, DB
writes, operator commands, or production-like DB execution.

## Current Status

- Stage 23A is complete: the dedicated planner-evidence endpoint now has a
  first bounded live per-system provider built from existing canonical
  system/station data and existing observed-facts summaries.
- Stage 23B is complete: the same endpoint now exposes bounded Stage 19BB
  staging evidence for a selected system when that evidence is safely queryable
  and otherwise returns explicit unavailable / not-evaluated bounded-staging
  status.
- Stage 23C is complete: the same endpoint now exposes an explicit evidence
  envelope so callers can distinguish canonical, observed-facts,
  bounded-staging, derived-report, unavailable, and not-evaluated semantics
  without inferring them from warnings alone.
- Stage 23D is complete: the planner UI now consumes the governed evidence
  envelope directly and renders distinct user-facing wording for available,
  unavailable, not-evaluated, unknown, and bounded-staging review states.
- The dedicated `warehouse_planner_evidence/v1` endpoint remains the preferred
  planner evidence path.
- Provenance fallback remains preserved.
- Unsupported or insufficiently evidenced systems still remain
  `unavailable`/`unknown`.
- The next recommended checkpoint is `Stage 23E - Closeout or next-control
  handoff`.
- The separate Stage 19BB bounded-staging execution dependency is now
  satisfied. The merged closeout is recorded in
  `docs/colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`.
- Stage 23 itself remains read-only: the satisfied dependency does not
  authorize Stage 23 DB writes, canonical apply, rebaseline, or scheduler work.

## Source Order

Stage 23 keeps the evidence source order explicit:

1. Canonical system/station data already used by the app.
2. Observed facts already stored in the app.
3. Warehouse/reconciliation data only when a safe per-system join exists.
4. Sanitized source-run metadata only as supporting review context.

Missing evidence stays unknown. Historical authority snapshots do not become
selected-system evidence.

## Checkpoint Plan

### Stage 23A

`Stage 23A - First bounded live per-system evidence provider`

Deliver the first live provider behind the existing dedicated endpoint using
only existing read-only data already present in the app.

### Stage 23B

`Stage 23B - Safe per-system warehouse join expansion`

Stage 23B is complete and recorded in
`docs/colonisation-redesign/stage-23b-readonly-per-system-warehouse-join.md`.

The delivered slice keeps the existing dedicated endpoint and expands it with a
guarded read-only lookup for Stage 19BB bounded staging evidence:

- selected-system responses can expose bounded staging provenance;
- bounded staging remains explicitly `report-only`;
- bounded staging remains explicitly `bounded staging only`;
- bounded staging is unavailable when no approved closeout run links the
  selected system;
- bounded staging remains not evaluated when the staging boundary is not safely
  queryable in the current runtime.

This still remains operationally dependent on the separate bounded Stage 19
production-staging activation contract rather than inferred warehouse truth.
That separate dependency is now pinned to the merged Stage 19BB authorization
and closeout chain, which records the reviewed EDSM source, the reviewed
isolated staging target fingerprint, and the completed `100 -> 1,000 -> 10,000`
bounded ladder as sanitized staging-only evidence. Stage 23B uses that
dependency as review context only; Stage 23 still does not authorize operator
execution or any write-capable lane.

### Stage 23C

`Stage 23C - Evidence envelope governance and source semantics`

Stage 23C is complete and recorded in
`docs/colonisation-redesign/stage-23c-evidence-envelope-governance.md`.

The delivered slice keeps the endpoint path stable and adds explicit envelope
governance:

- envelope-level `status`;
- explicit `source_classes`;
- explicit `semantics`;
- explicit report-only and selected-system-only posture;
- explicit non-canonical and non-full-coverage semantics for bounded staging.

This keeps canonical evidence, observed-facts evidence, bounded staging
evidence, unavailable evidence, and not-evaluated evidence distinct inside the
same read-only planner evidence surface.

### Stage 23D

`Stage 23D - Read-only planner evidence UX follow-through`

Stage 23D is complete and recorded in
`docs/colonisation-redesign/stage-23d-planner-evidence-ux-follow-through.md`.

The delivered slice keeps the existing endpoint path and applies the Stage 23C
envelope directly in the planner UI:

- the dedicated endpoint response is preferred whenever it exists;
- envelope `status` now drives the user-facing state wording;
- source classes and source semantics are rendered directly;
- bounded staging stays explicitly report-only, non-canonical, and not full
  coverage;
- provenance fallback remains a fallback for dedicated-endpoint read failure,
  not a replacement for explicit `unavailable` responses.

### Stage 23E

`Stage 23E - Closeout or next-control handoff`

Close Stage 23 or hand off to the next explicit control document while keeping
Stage 19 separately gated unless re-authorized by a new control document.

## Preserved Boundaries

- Read-only only.
- No new ingestion lane.
- No crawling external live APIs.
- No planner mutation or scoring changes.
- No CP logic changes.
- No DB writes.
- No Stage 19 operator execution.
- No canonical apply or rebaseline.
- No scheduler/service activation.

This order keeps live evidence usefulness ahead of any broader execution or
production-lane discussion.
