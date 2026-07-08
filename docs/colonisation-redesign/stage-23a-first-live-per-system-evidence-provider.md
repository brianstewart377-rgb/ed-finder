# Stage 23A - First Live Per-System Evidence Provider

## Purpose

Stage 23A delivers the first bounded live read-only provider behind the
dedicated planner-evidence endpoint. It replaces the normal-runtime reliance on
fixtures or aggregate-only fallback with real per-system evidence assembled from
existing data already used by the app.

## Chosen Provider

The first provider is intentionally narrow:

- canonical selected-system identity plus existing canonical station/body data;
- existing observed-facts summary keyed by `system_id64`;
- no per-system warehouse evidence unless a safe selected-system join already
  exists;
- no historical authority JSON reused as selected-system evidence.

## Why This Slice

This is the smallest implementation that satisfies the Stage 23 start
conditions:

- it uses real existing in-app data;
- it preserves the current dedicated endpoint and frontend path;
- it keeps provenance fallback intact;
- it does not invent a new ingestion pipeline or live external dependency;
- it keeps unsupported systems safely unknown.

## Delivered Behaviour

- The dedicated `warehouse_planner_evidence/v1` endpoint remains preferred.
- In normal runtime, known systems with bounded canonical and/or observed
  evidence can return source-labelled report-only evidence without enabling any
  write lane.
- Systems with no safe selected-system evidence remain
  `availability = unavailable` and `freshness = unknown`.
- Freshness stays conservative: missing timestamps do not imply `fresh`.
- Warehouse source-run metadata only remains supporting review context and does
  not become selected-system evidence.

## Source Semantics

- `canonical`: existing app truth such as system/station/body presence.
- `observed`: persisted observed-facts summary keyed by the selected system.
- `warehouse_report_only`: reserved for safe selected-system warehouse joins.
- `unknown`: unresolved or not safely linked.

The endpoint is therefore treated as a broader report-only planner evidence
envelope, even though the historical route name still contains
`warehouse_planner_evidence`.

## Boundaries Preserved

- Read-only only.
- No new ingestion lane.
- No DB writes.
- No external live API crawling.
- No planner mutation.
- No scoring, CP, or auto-action changes.
- No Stage 19 reactivation.

## Acceptance

Stage 23A is complete when:

- at least one real selected system can return non-fixture evidence in normal
  runtime;
- source labels clearly distinguish canonical, observed, warehouse report-only,
  and unknown evidence;
- unsupported systems still remain unavailable/unknown;
- provenance fallback still works;
- all Stage 19 and write-capable boundaries remain false.

