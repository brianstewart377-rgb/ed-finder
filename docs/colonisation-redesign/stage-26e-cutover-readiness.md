# Stage 26E Cutover Readiness

## Status

Stage 26E is in progress. The isolated production-candidate foundation now has
measured desktop-browser, viewport, accessibility, visual-regression, and
steady-state frame evidence. The live `#map` route is unchanged because four
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

These are local Windows/Playwright readings. They do not imply a broad hardware
performance guarantee.

## Open Engineering Gates

### GPU timing

Stage 26E now attempts a real WebGL2 `EXT_disjoint_timer_query_webgl2` query.
The extension was unavailable in the measured Chromium environment, so GPU
time remains explicitly unknown. JavaScript callback or request-animation-frame
duration is not substituted.

### Memory budget

Chromium reported roughly 212 MB and 410 MB of used JavaScript heap after the
500,000-system development journey at 1280x720 and 1440x900 respectively. The
fixture is intentionally much larger than today's Finder-backed production
response, but Stage 26E has not yet set or passed a production memory budget.

### Production feature parity

The typed foundation supports Finder systems, selected-system context, compare
and exact cluster highlights, overlap choice, camera return state, and explicit
Planner hand-off. The current live Map still owns heatmap cells, aggregate
cluster hulls, timeline summary/bucket state, Results/Galaxy/Reference presets,
and its production error/empty-state composition. Those features must either be
wired to the typed boundary or explicitly retired by product review before
cutover.

## Region Data And Legal Gate

Repository history shows `apps/importer/src/data/region_map.json` first arriving
in commit `f4e9ff6b2b2f201441eaf70301dc98ee15efe992`. The importer credits the
MIT-licensed `klightspeed/EliteDangerousRegionMap` algorithm, but the repository
contains no retained source receipt establishing redistribution rights for the
42 names and RLE geometry themselves.

Frontier's official media guidance permits specified non-commercial fan and
community uses with attribution, requires express permission for commercial or
promotional uses, and directs uncertain uses to its community team. That policy
does not unambiguously classify this derived geometry or establish whether the
deployed ED-Finder service is within the non-commercial allowance. See
[Frontier's official guidance](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media).

Before production exposure of the RLE-derived boundaries, the project owner or
qualified reviewer must confirm the service posture, geometry coverage, and
required attribution. The upstream MIT notice must also be retained if its code
is reused. Until then, the production route cannot cut over.

## Next Authorized Work

Stage 26E may continue with production feature-parity adapters and a bounded
production memory plan. It may also rerun GPU timing on an environment exposing
the required extension or with a captured system trace. Route cutover and
superseded-map deletion remain unauthorized until every blocking gate is
recorded as closed.
