# Stage 26F-0 rendered evidence

Captured at `2026-07-25T20:23:35.238Z` from branch
`codex/26f-0-wire-real-2d-map`, based on
`origin/main` `7c04f3ed342bb42e7ecc9a93264f0f45e0378bb6`.

The sequence uses the real production route and the real MIT-licensed
`elite-dangerous-region-map.svg`. The layer requests were served by the normal
map API against a disposable, isolated Review Lab database. No fixture or
fallback layer data was added to production frontend code.

## Sequence

1. [Authoritative 2D baseline](./2026-07-25T20-23-35-238Z-01-2d-authoritative-base.png)
   — `ProductionMapTab` renders `AuthoritativeRegionMap` directly; the 42 named
   regions and Ben Peddell/MIT credit are visible.
2. [Heatmap enabled](./2026-07-25T20-23-35-238Z-02-2d-heatmap-24-cells.png)
   — 24 live API cells add visible coloured density points over the region SVG.
3. [Clusters enabled](./2026-07-25T20-23-35-238Z-03-2d-heatmap-and-12-clusters.png)
   — 12 live API cluster hulls add visible glowing ring geometry while the
   heatmap remains present.
4. [Timeline enabled](./2026-07-25T20-23-35-238Z-04-2d-all-layers-timeline-37-buckets.png)
   — 37 live API buckets / 292 systems add the visible discovery-density plot.
5. [3D projection](./2026-07-25T20-23-35-238Z-05-3d-all-layers.png)
   — switching to 3D replaces the authoritative flat chart with the spatial
   WebGL scene while preserving the enabled layers and timeline plot.

## Data finding

The ordinary local development database could not supply positive layer
evidence:

- `systems = 40`
- `ratings = 40`
- `mv_map_heatmap_200ly = 0`
- `cluster_summary = 0`
- `mv_map_timeline_month = 0`
- `/api/map/heatmap` returned 0 cells
- `/api/map/clusters/hulls` returned 0 hulls
- `/api/map/timeline` returned 0 points

Those empty responses were also present under the corresponding `map:*` Redis
cache keys. This is a development-data population/refresh defect, not a toggle
or renderer defect. When an enabled endpoint returns an empty collection, the
rendered map now says which layer is empty instead of implying that invisible
geometry was drawn.

For positive rendering evidence only, the disposable Review Lab database was
populated with 288 spatially distributed rated systems, 12 aggregate cluster
anchors, and 36 months of discovery dates; its heatmap and timeline
materialized views were refreshed before capture. The isolated stack and its
volumes were destroyed after verification.

## Timeline finding

Before this task, timeline data produced only the text `TimelineSummary`;
neither `ProductionMapTab` nor `R3FMapFoundation` drew timeline geometry. The
minimal density plot shown in steps 4 and 5 is the first rendered timeline
geometry. It is derived from the API bucket counts and does not change query
semantics.
