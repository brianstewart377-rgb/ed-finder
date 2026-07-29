# Task 26F-UX-9 rendered evidence

Captured from `VITE_STAGE26E_PRODUCTION_MAP=enabled yarn dev` at
`http://127.0.0.1:4319/#map` in a 1280×720 in-app browser viewport.

- `whole-galaxy-reach-and-normal-current-label.jpg` shows the corrected
  191.68 LY/px whole-galaxy fit. Formidine Rift and Kepler's Crest are both
  visible above the floating attribution HUD. The current `Galactic Centre`
  label uses the same normal label layer; the old giant ambient layer is
  absent.
- `normal-sized-persistent-current-region.jpg` shows `Arcadian Stream` at
  10.98 LY/px after pan and zoom. Its authoritative centroid projects above
  the usable map area, so the persistent ordinary label is pinned to the
  overlay-safe top inset. It remains normal map-label typography rather than
  the removed 100px-class ambient treatment.
- `reachability-observation.json` records the before/after projection
  measurements and an exhaustive authoritative-grid check for all 42 region
  label anchors.
- `keyboard-pan-observation.json` is the renderer's completed-gesture trace.
  It records real animation-frame velocity and camera-center samples from a
  focused map after a W input. Velocity rises across acceleration samples,
  then falls through the coast to exactly zero; camera Z stays monotonic.

The first motion trace exposed stale parent commits briefly rewinding the
camera center. The final implementation now recognizes its pending camera
emissions (the same principle used by smooth zoom), and the committed evidence
is from the corrected monotonic trace.
