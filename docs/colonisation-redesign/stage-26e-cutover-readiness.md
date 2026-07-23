# Stage 26E Cutover Readiness

## Status

Stage 26E is in progress. The isolated production-candidate foundation now has
measured desktop-browser, viewport, accessibility, visual-regression, and
steady-state frame evidence. Its isolated boundary now carries the remaining
production feature shapes, continuous authoritative region boundaries, and a
closed owner-reviewed region-data gate. The same bounded region layer is wired
into the production `#map` candidate and the full regression passes. The Vite
production configuration now selects the Stage 26E map by default, while an
explicit disabled override preserves the established renderer as rollback.
Merge, deployment, and public smoke-checking remain; this document does not yet
claim the public site has changed.

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
- The candidate is composed on the production `#map` route with the exact
  enabled value supplied by the default Vite production configuration. The
  explicit `VITE_STAGE26E_PRODUCTION_MAP=disabled` override builds the
  established renderer and omits the Stage 26E region asset.
- With 500 live Finder systems, 50,000 heatmap cells, 2,000 aggregate hulls,
  100 timeline points, 42 region labels, and 22,595 continuous boundary
  segments, Chromium CDP reported composed-route heap maxima of 30,353,992
  bytes at 1280x720 and 27,463,288 bytes at 1440x900. Both pass the predeclared
  256 MiB live-route budget. The build-emitted region response is 2,312,898
  bytes against a separate 4 MiB guard, and its typed positions occupy 542,280
  bytes.
- The retained interaction journey passes at both viewports; the compatibility
  matrix passes all six Chromium/Firefox/WebKit viewport cells; the dedicated
  Axe journey and 1440x900 visual golden also pass. The exact live-route
  candidate passes both viewports with zero detectable Axe violations.
- A normal `yarn build:typecheck` emits and validates
  `stage26e/authoritative-regions.json`. A separate explicit disabled build
  omits it and passes the inverse build contract, preserving a tested
  build-time rollback boundary.
- The ordinary production-app smoke passes seven tests, including Map
  navigation, a 200 response for the region asset, the activated route state,
  and the default-visible Regions toggle.

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
composition and live production-shaped payloads. It does not by itself close
GPU timing or authorize route cutover; the separate hardware-backed measurement
below closes the GPU evidence gate.

## Closed Production Feature Parity

The isolated typed boundary now supports Finder systems, selected-system
context, compare and exact cluster highlights, overlap choice, camera return
state, explicit Planner hand-off, live heatmap response shapes, aggregate
cluster hulls, timeline summary/bucket state, Results/Galaxy/Reference presets,
bounded authoritative region labels and continuous boundaries, and typed
ready/empty/error composition. Invalid overlay coordinates are omitted rather
than invented, and the large-result preset calculation is iterative rather
than spreading an unbounded result array onto the call stack.

This closes the feature-parity adapter, bounded region delivery, pre-activation
regression, and build-activation gates. Merge, production deployment, and a
public browser smoke-check are now the next route steps. The established
renderer remains available through the explicit disabled rollback build;
superseded-map removal remains later and explicit.

## Closed GPU Evidence

### GPU timing

The initial automated Chromium environment did not expose
`EXT_disjoint_timer_query_webgl2`. A hardware-backed Chromium rerun now wraps
the real `WebGLRenderer.render(scene, camera)` call for the visible 500,000-
system candidate scene. At 1280x720, 30/30 valid queries produced 1.358 ms p95;
at 1440x900, 30/30 produced 1.747 ms p95. No samples were discarded as
disjoint. The browser reported hardware-accelerated ANGLE/Direct3D 11 rather
than a software rasterizer.

After replacing the sparse sampled region dividers with 22,595 merged,
continuous exact-grid segments (542,280 position bytes), the renderer enables
antialiasing and presents the boundaries as solid amber structural lines. The
retained rerun produced 18.982 ms p95 at 1280x720 and 27.243 ms p95 at
1440x900. Both runs again returned 30/30 valid queries with no disjoint samples
and remain below the provisional 50 ms budget.

This closes the unknown-GPU-time evidence gate without substituting JavaScript
callback or request-animation-frame duration. The retained receipt is
[`hardware-gpu-timing.json`](../../artifacts/map-foundation/stage-26e/hardware-gpu-timing.json).
For a repeat measurement in normal Chrome, run `yarn map-foundation:dev` from
`frontend/`, open
`http://127.0.0.1:4175/map-foundation/index.html?gpu-test=1`, wait for `ready`,
and select **Run GPU timing**. The diagnostic is development-only and does not
change production route selection.

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
footer. The footer now also carries the owner-approved EDSM/EDDN community-data
acknowledgement and Elite Dangerous trademark/unofficial-tool attribution.

Frontier's official media guidance permits specified non-commercial fan and
community uses with attribution, requires express permission for commercial or
promotional uses, and directs uncertain uses to its community team. See
[Frontier's official guidance](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media).

On 2026-07-22, the project owner confirmed that ED-Finder's non-commercial use
of the 42 region names and derived RLE geometry is covered by that guidance.
The application now uses Frontier's official long-form attribution wording.
This closes the internal project gate as an owner governance decision, not as
independent legal advice. The upstream MIT copyright and permission notice is
retained in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) for the reused code and
data. ED-Finder remains free and non-commercial; no donation mechanism is
implemented or relied on by this review, and community donation precedent is
not treated as formal permission.

## Next Authorized Work

Stage 26E activation is implemented locally. The next bounded steps are to
merge this configuration, deploy the ordinary production build, verify the
public root and `#map` route plus the region asset, and retain
`VITE_STAGE26E_PRODUCTION_MAP=disabled` as the immediate rebuild rollback.
Superseded-map deletion remains a later, explicit step after a stable period.

The supplied Raven Colonial reference identifies a useful post-cutover visual
follow-up: an explicit 2D/3D control, a restrained oblique tabletop preset,
map-plane region labels, and a faint orientation grid. ED-Finder may adapt
those interaction principles through its existing bearing/pitch state, without
copying Raven assets or widening the current cutover slice.
