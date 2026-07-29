# Task 26F-UX-4 rendered evidence

Observed on the flagged local production-map route with
`VITE_STAGE26E_PRODUCTION_MAP=enabled`.

## Reference footage decisions

- The observed roughly 500 ms accelerate/decelerate movement maps to a
  500 ms `easeInOutSine` transition.
- Zoom is interpolated in log space so equal zoom-in and zoom-out input feels
  symmetrical.
- A new input retargets the active transition from its current value and
  velocity instead of queuing another transition.
- Each emitted camera retains the current centre exactly so scenery scales
  around the same focal point.
- The reference's full-viewport canvas and layered HUD drove a Map-only fixed
  viewport shell. Navigation, map modes, zoom, layers, status, selection, and
  legal attribution are overlays; the canvas remains behind all of them.

## Browser observations

- At 1440 x 900, the rendered map viewport rectangle was
  `x=0, y=0, width=1440, height=900`: 100% width and 100% height.
- The same layout was checked at 1280 x 720. The Map-only navigation switches
  to its compact menu and the map header and control strip become two
  non-overlapping overlay rows.
- `prefers-reduced-motion` was false for the motion observation.
- A real Zoom In button click produced multiple monotonically decreasing
  rendered zoom values and settled exactly on the log-scale target. Browser
  control round-trips add latency to the timestamps, so the exact 500 ms
  duration is asserted by the deterministic animation test; the live DOM
  samples demonstrate that the rendered route does not snap.
- Camera centre before and after the observed transition was exactly
  `[-240.80722891566256, 25762.566265060246]`.
- An early browser probe exposed a stale-prop cancellation defect that stopped
  the transition after its first frame. The fix now recognises any still-
  pending frame emitted by the hook, and a regression test covers delayed
  React commits.

## Files

- `immersive-layout-1440x900.png` — desktop full-galaxy view with a
  full-viewport canvas and floating overlays.
- `immersive-layout-1280x720.png` — compact responsive Map-only overlay at the
  narrower acceptance viewport.
- `zoom-observation.json` — values read from the real rendered route during
  Zoom In interactions.
