# Stage 26E Cutover Readiness

## Status

Stage 26E is in progress. The isolated production-candidate foundation now has
measured desktop-browser, viewport, accessibility, visual-regression, and
steady-state frame evidence. Its isolated boundary now carries the remaining
production feature shapes. The live `#map` route is unchanged because three
cutover gates remain open. This document is a progress checkpoint, not a
completion or shipping claim.

The machine-readable source of truth is
[`cutover-gates.json`](../../artifacts/map-foundation/stage-26e/cutover-gates.json).

## Closed Engineering Evidence

- Chromium, Firefox, and WebKit pass the typed foundation journey at 1280x720
  and 1440x900: six browser/viewport cells.
- The existing overlap, context-restoration, camera, all-feature hand-off, and
  read-only Planner journey remains green in Chromium at both viewports.
- Axe reports zero detectable WCAG 2/2.1 A/AA violations on the isolated
  foundation; the companion selection and hand-off controls remain keyboard
  operable and named.
- A repeatable 1440x900 Chromium golden image passes with a maximum one-percent
  pixel-difference budget and has been manually inspected.
- Sixty-frame steady-state samples after the 500,000-system hand-off journey
  measured approximately 16.7 ms and 16.8 ms p95 at the two required
  viewports, below the provisional 50 ms gate.
- The heatmap API now returns at most 50,000 density-first cells, fetches one
  sentinel row to report truncation, and emits explicit `max_cells` and
  `truncated` metadata. A maximum-width compact JSON fixture measured 4,550,111
  bytes against an 8 MiB raw-response budget.

These are local Windows/Playwright readings. They do not imply a broad hardware
performance guarantee.

## Open Engineering Gates

### GPU timing

Stage 26E now attempts a real WebGL2 `EXT_disjoint_timer_query_webgl2` query.
The extension was unavailable in the measured Chromium environment, so GPU
time remains explicitly unknown. JavaScript callback or request-animation-frame
duration is not substituted.

### Memory budget

The candidate now limits the current 500-system Finder envelope, 50,000
normalized heatmap cells, 2,000 aggregate hulls, and 1,200 timeline points. At
those maxima, the heatmap and score-coloured hull typed buffers total 4,272,000
bytes and pass an 8 MiB normalized-overlay budget. Repeated isolated
500,000-system journeys
reported roughly 167-662 MB at 1280x720 and 188-386 MB at 1440x900, demonstrating
that these development-fixture heap snapshots are not stable enough to serve as
a production budget.

This closes the raw heatmap transport bound. It is still partial memory closure:
the candidate has not been composed into the live production route, so an
end-to-end route heap budget has not been measured. The repeated isolated heap
variability makes that live measurement mandatory rather than inferable.

### Production feature parity

The isolated typed boundary now supports Finder systems, selected-system
context, compare and exact cluster highlights, overlap choice, camera return
state, explicit Planner hand-off, live heatmap response shapes, aggregate
cluster hulls, timeline summary/bucket state, Results/Galaxy/Reference presets,
and typed ready/empty/error composition. Invalid overlay coordinates are
omitted rather than invented, and the large-result preset calculation is
iterative rather than spreading an unbounded result array onto the call stack.

This closes the isolated feature-parity adapter gate. It does not wire the live
route; that deliberate composition and its regression run remain a final route
step after the blocking gates close.

## Region Data And Legal Gate

Repository history shows `apps/importer/src/data/region_map.json` first arriving
in commit `f4e9ff6b2b2f201441eaf70301dc98ee15efe992`. The importer credits the
MIT-licensed `klightspeed/EliteDangerousRegionMap` algorithm, but the repository
contains no retained source receipt establishing redistribution rights for the
42 names and RLE geometry themselves. On 2026-07-22, the project owner confirmed
that ED-Finder is non-commercial, resolving the service-posture question.

Frontier's official media guidance permits specified non-commercial fan and
community uses with attribution, requires express permission for commercial or
promotional uses, and directs uncertain uses to its community team. That policy
does not unambiguously establish that this derived geometry is covered or state
the attribution required for this particular use. See
[Frontier's official guidance](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media).

Before production exposure of the RLE-derived boundaries, the project owner or
qualified reviewer must confirm geometry coverage and required attribution.
The upstream MIT notice must also be retained if its code is reused. Until
then, the production route cannot cut over.

## Next Authorized Work

Stage 26E may continue by composing the candidate behind a disabled production
flag and measuring a live-route JavaScript heap budget. It may also rerun GPU
timing on an environment exposing the required extension or with a captured
system trace, and close the remaining region-geometry and attribution
questions. Route cutover and
superseded-map deletion remain unauthorized until every blocking gate is
recorded as closed.
