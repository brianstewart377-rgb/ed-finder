# Stage 26E Cutover-Readiness Evidence

This directory records the measured Stage 26E engineering progress without
claiming production cutover readiness.

- `cutover-gates.json` is the machine-readable gate ledger.
- `performance-1280x720.json` and `performance-1440x900.json` are Chromium
  steady-state readings from the deterministic 500,000-system development
  fixture after the Stage 26D hand-off journey.
- `production-memory-budget.json` records the bounded normalized overlay
  buffers, their deterministic worst-case byte count, and the raw-response and
  live-route measurements that remain open.
- The visual golden is retained beside its Playwright test under
  `frontend/map-foundation/e2e/visual.spec.ts-snapshots/`.

The GPU timer extension was unavailable, so GPU time remains unknown rather
than being inferred from JavaScript frame callbacks. The isolated candidate now
carries the live feature shapes, but production cutover remains blocked by raw
heatmap/live-route memory evidence (including highly variable isolated heap
snapshots), GPU evidence, and region-data provenance and attribution review.
