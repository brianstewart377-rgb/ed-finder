# Task 26F-UX-2 rendered evidence

Date: 2026-07-28  
Branch: `codex/26f-ux-unified-camera`  
Working point: `bf5f6adc53fa78dfc3ab886fdcfddce3a6f23dc7`  
Review viewport: 1280 × 720  
Live API target: `https://ed-finder.app`

## Continuous-camera sequence

All three frames use the same perspective renderer and the same 50-system
Finder result set. The centre and zoom remained unchanged while the pitch
changed continuously:

| Frame | Pitch | Camera centre | Zoom | Evidence |
| --- | ---: | --- | ---: | --- |
| Top-down snap | 0.5° | x 0, z 0 | 0.986236 LY/px | [Top-down](2026-07-28-final-real-results-top-down.png) |
| Default tilted view | 42° | x 0, z 0 | 0.986236 LY/px | [Tilted](2026-07-28-final-real-height-tilted.png) |
| Near-flat view | 72° | x 0, z 0 | 0.986236 LY/px | [Near-flat](2026-07-28-final-real-height-near-flat.png) |

The 42° default was chosen as a moderate in-game-style framing: it exposes the
disc's structure and real height immediately without approaching the compressed
72° near-flat limit.

The tilted and near-flat frames visibly place real Finder systems above and
below the galactic plane. The Finder API response used by the map includes
real `coords.x`, `coords.y`, and `coords.z` values; no generated height map is
used.

## Height-flow audit

The real schema field is `systems.y REAL`, exposed by the API as `coords.y`.
Galactic X/Z remain the map plane and galactic Y is mapped to the remaining
Three.js Z axis. The audit fixed all flattening sites in the production
foundation path:

- Finder, Compare, saved-system, evidence, detail, cluster, and planner
  hand-offs now retain `coords.y`.
- Finder system point buffers and projected system labels use `coords.y`.
- Heatmap voxels use API `cy`.
- Aggregate cluster hulls use API `y`.
- Descriptor cluster member edges use each endpoint's `coords.y`.
- Descriptor hull vertices and fallback anchor rings use their real height.

## Live layer and legend checks

- [Layer legend](2026-07-28-final-layer-legend.png) shows the verified
  definitions for Regions, Heatmap, Clusters, and Timeline.
- [Heatmap](2026-07-28-final-heatmap-corrected.png) shows 49,999 real
  three-dimensional voxel cells after the server's 50,000-cell cap and the
  adapter's rejection of one aggregate row without finite coordinates.
- [Whole-galaxy clusters](2026-07-28-final-whole-galaxy-clusters.png) shows
  2,000 aggregate hulls in the same perspective scene as the 42 authoritative
  region boundaries.
- The live Timeline response rendered 102 monthly buckets, 187,819,898
  tracked systems, and a latest bucket of 2026-07-01.

## Pan-bound observation

At whole-galaxy scale, an extreme drag was attempted with the camera at 42°
and 217.969207 LY/px. Before and after the drag, the clamped centre remained:

`x = -240.80722891566256`, `z = 25762.566265060246`

The galaxy therefore remained in view rather than being draggable indefinitely
into empty space.

## Verification

- TypeScript: passed.
- Focused map suite: 6 files, 61 tests passed.
- Full frontend suite: 117 files, 761 tests passed.
- Standalone map-foundation browser suite: 2 viewports, 2 tests passed.
- ESLint: 0 errors; 3 pre-existing warnings outside this change.
- Production build: passed.
- Production map build contract: 2,312,898-byte authoritative source,
  42 labels, and 22,595 boundaries.

The optional live-route memory harness was also attempted locally, but its two
cases timed out at the prerequisite “load 500 live Finder systems” step because
the harness expected an API at `127.0.0.1:8001`; the captured server log shows
repeated `ECONNREFUSED` responses. This is recorded as an environment block,
not as a passing check. The branch does not modify the harness, its Vite
wrapper, or `vite.config.ts`; that existing wrapper enables the route but does
not start the API which the Vite config describes as the external supervisor
backend. The protected CI E2E job does provision an API explicitly and points
the frontend proxy at it, so the real protected run remains the authoritative
integration result for this PR.
