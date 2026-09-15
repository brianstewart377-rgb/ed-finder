# Implementation slice 09 — exact stars, adaptive grid and zoom

**Date:** 2026-09-14
**Status:** implemented fixture/local-renderer candidate; production catalogue
streaming remains M3/M4

## Benchmark and scope

The user supplied the
[Elite Dangerous Galaxy Map tutorial](https://www.youtube.com/watch?v=k2l9V4c90cU&t=4s)
as a visual benchmark and clarified that the relevant features are the zoomed-in
real-star presentation, correct positions, depth grid and camera journey—not a
request to copy the surrounding control panel.

The visual review sampled the full 8:09 tutorial. The important moments were:

| Approximate time | Visual lesson translated into ED-Finder requirements                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 01:05–02:10      | Search/focus moves into a selected real system without losing the surrounding 3-D field; the target has a crisp ring and anchored details. |
| 04:30–05:35      | Named individual systems stay readable during closer navigation; the perspective plane makes distance and tilt apparent.                   |
| 06:20–07:20      | Dense individual targets retain their spatial relationships while the display changes; filtering is separate from target placement.        |

This is interaction and visual research only. No Frontier assets, shaders,
layout or trade dress are copied.

## V2 baseline and improvement

The V2 review records good camera presets, pan/zoom, top-down, tilt, grid-snapped
queries and semantic-detail intent. It also records unreliable aggregate-to-star
transition state and a procedural visible fallback when real detail is absent.

V3 improves the renderer foundation in this slice by making coordinate and
presentation responsibilities explicit:

- `GalaxySystemPoint.positionLy` is copied into the Babylon thin-instance
  translation matrix without scale, projection or jitter;
- zoom changes the camera and non-factual marker radius, never the translation;
- the grid is a separate `SCHEMATIC` renderer resource on canonical Galactic
  `Y=0` and declares that it does not affect system positions;
- a deterministic 1/2/5 interval sequence produces increasingly coarse
  light-year cells while zooming out;
- line count is bounded and line alpha fades towards the visible grid edge;
- the active minor-grid interval is visible beside camera range; and
- grid geometry may refine during a camera transition without rebuilding the
  factual Finder, region or density resources.

## Implemented files

- `apps/web/src/lib/spatial/galaxy-grid.ts`
  - deterministic adaptive LY grid specification;
  - Galactic-plane truth and bounded geometry.
- `apps/web/src/lib/spatial/babylon/adapter.ts`
  - faded minor, major and Galactic-axis line resources;
  - camera/resize-aware grid refinement;
  - smaller constant-screen-scale star cores;
  - explicit exact-coordinate presentation metadata.
- `apps/web/src/lib/spatial/SpatialCanvas.svelte`
  - visible camera range and grid interval.
- focused unit and camera-session tests
  - exact thin-instance matrix translations;
  - stable factual mesh identity while the schematic grid refines.
- browser diagnostics
  - wide, local, tilted, top-down, region and density captures on WebGPU and
    forced WebGL2 at 1280×720 and 1440×900;
  - explicit assertion that the grid interval becomes finer on the local
    fixture-neighbourhood view.

Validation on 2026-09-14: 30 test files / 244 tests, Svelte check with zero
errors and warnings, lint, production build, and the 4/4 WebGPU/WebGL2 browser
matrix with 24 screenshots all pass. The 964.19 kB Babylon client chunk remains
an RC1 bundle-hardening item.

## Truth boundary and remaining gate

The Review Lab uses a deterministic coordinate fixture, so its stars are not a
claim that production catalogue streaming is complete. The shipping path still
requires M3/M4 to provide bounded generation-pinned individual-star packets
from the canonical catalogue and to reconcile them with the density pyramid.

Until then:

- the exact renderer placement and zoom behaviour are implemented and tested;
- the production real-star population and aggregate-to-star cross-fade remain
  open;
- absent real packets remain absent—no procedural star cloud or swirl may fill
  the gap.
