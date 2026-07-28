# 26F UX polish rendered evidence

Captured from the production build served locally at
`http://127.0.0.1:4173/` on 2026-07-28. The browser viewport was
1440 × 1050.

## Observations

- `full-galaxy-controls-labels.png` shows the discoverable zoom controls,
  muted camera-centre reference lines, darker void, and the complete galaxy
  view. The rendered overlay contained 38 visible region labels and a DOM
  bounds check found zero labels clipped by the map viewport.
- `tilted-solid-boundaries.png` shows the joined `Line2` boundary paths at
  63° pitch and 175 LY/px. The lines were visually continuous at the shallow
  angle that previously exposed stippling.
- `close-zoom-label-scale.png` shows the same tilted camera at 104 LY/px.
  Region-label scale increased from `0.9` at the full view to
  `1.2009834304039093`; 32 labels were visible and a second bounds check
  again found zero viewport-clipped labels.
- The `+` button changed camera zoom from `217.96920712462608` to
  `174.92438609448942`; the `−` button returned it to
  `217.96920712462608`.

## Missing-label investigation

Two independent causes were present:

1. `stableRegionLabels` discarded most of the authoritative 42 labels before
   camera projection, using fixed angular-sector quotas.
2. Projection allowed label centres up to 120 px outside the map while the
   label overlay intentionally clips overflow, so surviving edge labels could
   be visibly cut off.

The replacement projects all authoritative labels, rejects labels that cannot
fit fully within the viewport, and declutters the remainder in screen space.
It preserves decluttering instead of removing it.

## Visual reference

[RavenColonialWeb](https://github.com/njthomson/RavenColonialWeb)
(GPL-3.0) was inspected only for the owner-specified visual structure and mood.
No source code or colour values were copied; ED-Finder's existing orange-on-dark
identity remains the implementation source of truth.
