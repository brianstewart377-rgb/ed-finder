# Stage 18H.1 — Per-System Warehouse Evidence Contract Review

## Purpose

Stage 18H delivered a live read-only warehouse bridge into the planner by
reusing the sanitized provenance cockpit summary. Stage 18H.1 defines the next
safe step: a dedicated **per-system, report-only** warehouse evidence contract
that can later be served to the planner without crossing the admin or write
boundaries.

This slice is intentionally contract-first. It does **not** add a live endpoint,
does **not** join warehouse evidence into planner truth, and does **not**
authorize any Stage 19 production lane.

## Contract ID

`warehouse_planner_evidence/v1`

## Scope

The contract is for one system at a time, keyed by `system_id64`, and carries
only conservative warehouse evidence summaries that the planner may display as
report-only context.

The planner must continue treating missing contract data as
`availability = "unavailable"` and `source = "unknown"`, never as a false
negative.

## Allowed Fields

The contract may include only sanitized, planner-safe summary fields:

- `schema_version`
- `system_id64`
- `generated_at`
- `freshness`
- `source_run`
- `evidence_summary`
- `warnings`

Suggested normalized shape:

```json
{
  "schema_version": "warehouse_planner_evidence/v1",
  "system_id64": 123,
  "generated_at": "2026-06-17T12:00:00Z",
  "freshness": {
    "status": "fresh",
    "evaluated_at": "2026-06-17T12:00:00Z"
  },
  "source_run": {
    "source_name": "warehouse_reconciliation",
    "run_key": "warehouse/run-20260617T120000Z"
  },
  "evidence_summary": {
    "availability": "report_only",
    "report_only": true,
    "manual_review_required": false,
    "items": [
      {
        "label": "report_only",
        "source": "warehouse_report_only",
        "summary": "1 warehouse reconciliation item is available for this system."
      }
    ]
  },
  "warnings": []
}
```

## Prohibited Fields

This contract must **not** include:

- canonical write instructions
- SQL payloads, migration steps, or apply plans
- DSNs, credentials, tokens, or secrets
- raw file paths or host paths
- admin-only operator metadata
- raw unresolved station rows or bulky warehouse internals
- any field that tells the planner to mutate placements, roles, scoring,
  validation, Preview, optimiser output, or canonical app data

## Semantics

The contract is constrained by the same trust rules as Stage 18H:

- it is always report-only
- it is never planner truth
- it must remain source-labelled
- it may increase review visibility but never reduce the planner's canonical
  safety boundaries

If a later endpoint cannot safely produce evidence for a given `system_id64`,
the planner stays on the current unavailable/provenance-summary fallback path.

## Scaffolding Outcome

Stage 18H.1 in this slice adds:

- this contract document
- backend model scaffolding for `warehouse_planner_evidence/v1`
- frontend type scaffolding for the same contract
- authority/test/README updates that record this as the next planned follow-on

It does **not** add:

- a live endpoint
- a live API endpoint
- a new planner fetch
- admin-token reuse
- write-lane access
- any direct planner behavior change

## Follow-on

The next implementation slices after this contract review should be:

1. Stage 18H.2 — read-only backend contract resolver/endpoint scaffolding
2. Stage 18H.3 — planner integration with fallback to the current provenance
   bridge
3. Stage 18H.4 — UX clarification for freshness, review status, and source
   posture
