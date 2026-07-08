# Stage 19C.2 — Warehouse compact summary status support

## Result

Stage 19C.2 teaches the warehouse status sanitizer to understand compact reconciliation summary artifacts with schema:

`enrichment_reconciliation_artifact_summary/v1`

These compact summaries are produced from large read-only reconciliation artifacts and are intentionally reduced/sanitized for operator review.

## Scope

The sanitizer now maps compact summary counters and distributions into the existing Admin Warehouse Status UI contract where available:

- canonical writes planned;
- staged station/body/ring candidate counts;
- risk/confidence/reconciliation distributions;
- source coverage counters;
- evidence health counters;
- safety flags.

Missing compact fields remain unavailable instead of being guessed.

## Safety boundary

This stage only changes API sanitizer logic and docs.

It does not perform:

- DB access;
- DB writes;
- migrations;
- station-type writes;
- canonical writes;
- canonical apply;
- artifact generation.

