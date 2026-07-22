# Stage 26E Cutover-Readiness Evidence

This directory records the measured Stage 26E engineering progress without
claiming production cutover readiness.

- `cutover-gates.json` is the machine-readable gate ledger.
- `performance-1280x720.json` and `performance-1440x900.json` are Chromium
  steady-state readings from the deterministic 500,000-system development
  fixture after the Stage 26D hand-off journey.
- `hardware-gpu-timing.json` records 30 actual-render WebGL2 timer-query
  samples at each required viewport on a hardware-backed Chromium session.
  After antialiased continuous exact-grid boundaries replaced the sparse
  sampled dividers, both runs returned 30 valid samples with no disjoint
  results; p95 GPU time was 18.982 ms at 1280x720 and 27.243 ms at 1440x900.
- `production-memory-budget.json` records the bounded normalized overlay
  buffers, their deterministic worst-case byte count, the closed raw-response
  bound, and the closed live-route heap budget.
- `live-route-memory.json` records the exact default-off `#map` candidate at
  both required viewports with 500 live Finder systems, 50,000 heatmap cells,
  2,000 aggregate hulls, and 100 timeline points. Chromium CDP heap maxima were
  26,392,356 and 28,724,676 bytes against a 256 MiB budget; Axe reported zero
  detectable WCAG 2/2.1 A/AA violations on both composed-route viewports.
- `heatmap-response-envelope.json` records the server-side 50,000-cell ceiling,
  stable density-first ordering, truncation contract, and compact JSON budget.
- `region-source-review.json` records the exact local/upstream RLE comparison
  and the EDAssets catalog review. It separates MIT source provenance from the
  owner's recorded non-commercial Frontier-media-usage coverage decision.
- `THIRD_PARTY_NOTICES.md` at the repository root now retains the upstream MIT
  copyright and permission notice for the reused region algorithm and data.
- The visual golden is retained beside its Playwright test under
  `frontend/map-foundation/e2e/visual.spec.ts-snapshots/`.

The earlier automated Chromium environment did not expose the timer extension.
The hardware-backed rerun closes that evidence gap using real
`WebGLRenderer.render(scene, camera)` timer queries rather than JavaScript frame
callbacks. Region-data provenance, attribution, and the owner-review gate are
now closed. The candidate remains behind an exact default-off production flag;
bounded region delivery and the full cutover regression are the remaining
route work.
