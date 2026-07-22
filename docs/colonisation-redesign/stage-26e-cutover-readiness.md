# Stage 26E Cutover Readiness

## Status

Stage 26E is in progress. The isolated production-candidate foundation now has
measured desktop-browser, viewport, accessibility, visual-regression, and
steady-state frame evidence. Its isolated boundary now carries the remaining
production feature shapes. The live `#map` route is unchanged because two
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
  foundation and on the default-off composed live route at both viewports; the
  companion selection and hand-off controls remain keyboard operable and named.
- A repeatable 1440x900 Chromium golden image passes with a maximum one-percent
  pixel-difference budget and has been manually inspected.
- Sixty-frame steady-state samples after the 500,000-system hand-off journey
  measured approximately 16.7 ms and 16.8 ms p95 at the two required
  viewports, below the provisional 50 ms gate.
- The heatmap API now returns at most 50,000 density-first cells, fetches one
  sentinel row to report truncation, and emits explicit `max_cells` and
  `truncated` metadata. A maximum-width compact JSON fixture measured 4,550,111
  bytes against an 8 MiB raw-response budget.
- The candidate is composed on the production `#map` route behind the exact
  `VITE_STAGE26E_PRODUCTION_MAP=enabled` measurement flag. Normal builds leave
  the value unset and continue to select the established map.
- With 500 live Finder systems, 50,000 heatmap cells, 2,000 aggregate hulls,
  and 100 timeline points, Chromium CDP reported composed-route heap maxima of
  26,392,356 bytes at 1280x720 and 28,724,676 bytes at 1440x900. Both pass the
  predeclared 256 MiB live-route budget. Region geometry was not requested or
  exposed.

These are local Windows/Playwright readings. They do not imply a broad hardware
performance guarantee.

The live payloads were fetched from the ED-Finder API through the Vite preview
proxy and fulfilled unchanged into the measured route. Seven
`Performance.getMetrics` `JSHeapUsedSize` readings were taken after a one-second
idle without forcing garbage collection. This is a conservative retained-heap
reading on the measured Windows/Chromium environment, not a broad hardware
guarantee.

## Closed Memory Budget

The candidate now limits the current 500-system Finder envelope, 50,000
normalized heatmap cells, 2,000 aggregate hulls, and 1,200 timeline points. At
those maxima, the heatmap and score-coloured hull typed buffers total 4,272,000
bytes and pass an 8 MiB normalized-overlay budget. Repeated isolated
500,000-system journeys
reported roughly 167-662 MB at 1280x720 and 188-386 MB at 1440x900, demonstrating
that these development-fixture heap snapshots are not stable enough to serve as
a production budget.

The raw transport, normalized overlay buffers, and default-off live-route heap
are now all bounded. The live-route evidence supersedes the variable isolated
fixture snapshots for the memory gate because it measures the actual route
composition and live production-shaped payloads. It does not close GPU timing
or authorize route cutover.

## Closed Production Feature Parity

The isolated typed boundary now supports Finder systems, selected-system
context, compare and exact cluster highlights, overlap choice, camera return
state, explicit Planner hand-off, live heatmap response shapes, aggregate
cluster hulls, timeline summary/bucket state, Results/Galaxy/Reference presets,
and typed ready/empty/error composition. Invalid overlay coordinates are
omitted rather than invented, and the large-result preset calculation is
iterative rather than spreading an unbounded result array onto the call stack.

This closes the feature-parity adapter and disabled live-route composition
gates. The established renderer remains selected in normal production builds;
deliberate flag activation and superseded-map removal remain final route steps
after the remaining blocking gates close.

## Open Engineering Gates

### GPU timing

Stage 26E now attempts a real WebGL2 `EXT_disjoint_timer_query_webgl2` query.
The extension was unavailable in the measured Chromium environment, so GPU
time remains explicitly unknown. JavaScript callback or request-animation-frame
duration is not substituted.

## Region Data And Legal Gate

Repository history shows `apps/importer/src/data/region_map.json` first arriving
in commit `f4e9ff6b2b2f201441eaf70301dc98ee15efe992`. The importer credits the
MIT-licensed `klightspeed/EliteDangerousRegionMap` project. A byte- and
structure-level comparison now confirms that the local 2,048-row RLE geometry
is the upstream `RegionMapData.json` grid with coordinate metadata added; its
42 names also match, apart from changing the unused index-zero sentinel from
`null` to an empty string. This identifies the source precisely but does not
by itself establish Frontier redistribution coverage. The receipt and hashes
are retained in
[`region-source-review.json`](../../artifacts/map-foundation/stage-26e/region-source-review.json).

The inspected EDAssets Galaxy Map catalogs contain credited icons and markers,
not the 42-region RLE boundary grid. EDAssets states that its own site was made
with Frontier's permission; that site-specific statement is not evidence of a
transferable license for ED-Finder. Raven Colonial's web code is GPL-3.0 and
its embedded ED3D map has a separate MIT license; Raven also contains the exact
upstream `RegionMap.svg` blob and displays an unofficial/non-affiliation and
rights-acknowledgement notice. EDSM's public GitHub repositories expose no
detected license, while its service is catalogued as free and attributes Elite
Dangerous to Frontier. These are useful implementation precedents, not rights
clearance ED-Finder can inherit.

On 2026-07-22, the project owner confirmed that ED-Finder is non-commercial,
resolving the service-posture question. The owner also supplied and approved
the Frontier fan disclaimer, which is now rendered site-wide in the application
footer.

Frontier's official media guidance permits specified non-commercial fan and
community uses with attribution, requires express permission for commercial or
promotional uses, and directs uncertain uses to its community team. That policy
does not unambiguously establish that this derived geometry is covered or state
whether source-specific attribution is required for this particular use beyond
the site-wide fan disclaimer. See
[Frontier's official guidance](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media).

Before production exposure of the RLE-derived boundaries, the project owner or
qualified reviewer must confirm geometry coverage and required attribution.
The upstream MIT copyright and permission notice is now retained in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) for the reused code and
data. The separate Frontier coverage question remains open, so the production
route cannot cut over.

## Next Authorized Work

Stage 26E may continue by rerunning GPU timing on an environment exposing the
required extension or with a captured system trace, and by closing the
remaining region-geometry and attribution questions. Route cutover and
superseded-map deletion remain unauthorized until every blocking gate is
recorded as closed.
