# Babylon Map implementation slice 05 — projected labels

**Status:** implemented fixture label-layout slice; M1/M2 acceptance remains open
**Review date:** 2026-09-13
**Repository state:** `03aabce5` plus the uncommitted map implementation

This continues the
[V2-first comparison protocol](../../v3-babylon-map-delivery-plan.md#v2-first-continuous-improvement-protocol)
and the
[navigation/density slice](implementation-slice-04-navigation-density.md).

## V2 baseline and V3 improvement

V2 already projected authoritative region anchors into a DOM overlay and kept
the selected system label visible outside the whole-Galaxy preset. It also
provided a useful safe-area input and scale-dependent label sizing. Those are
the right architectural instincts: Babylon/Three owns spatial projection while
HTML provides crisp text.

The retained V2 evidence also shows region and Finder labels colliding. Its
declutterer used fixed centre-distance ordering and a fixed separation test;
region and system labels were solved separately, so neither layer knew which
target should win a shared screen area. Its selected-region behaviour could
clamp an off-screen anchor into the viewport, which risks implying a false
on-screen location.

V3 now uses one renderer-neutral label-layout pass for accepted region and
system targets. It projects with the exact Babylon camera basis, then solves a
shared collision field with explicit placement priorities:

1. selected system;
2. selected region;
3. hovered region;
4. region containing the camera focus;
5. ordinary Finder systems;
6. Galactic Centre; and
7. other regions, ordered deterministically by screen-centre distance and key.

Priority never decides whether a region name exists. Every region whose
source-derived anchor is in frame tries a bounded set of nearby placements; if
all collision-free positions fail, its label is clamped inside the safe area
and retained even when overlap is unavoidable. Off-screen anchors remain
off-screen rather than implying a false location. At whole-Galaxy scale, all 42
exact names are placed in ordered side rails with source-anchor leader lines.
System names still use collision and count budgets: wide views hide ordinary
system names but retain the selected system. This is the first semantic-scale
label policy, not the finished star/density LOD state machine.

## Truth and rendering boundaries

- Region names and positions come only from the accepted 42-region payload and
  its source-derived `labelLy` anchors.
- All 42 exact region names are guaranteed in the whole-Galaxy atlas. In closer
  views every in-frame region anchor retains its name; region priority affects
  placement and emphasis only, never visibility.
- System names and positions come only from accepted `finder-systems` points.
- Layout creates CSS-pixel offsets but no world coordinates, occupancy or
  spatial facts.
- The overlay is `aria-hidden`; the native region picker and fixture target list
  remain the accessible semantic mirrors. Visual text does not masquerade as a
  complete target-navigation surface.
- Projection supports the same perspective and orthographic extents as the
  Babylon adapter and responds to camera events and resize revisions.

The selected system uses a restrained warm glass treatment and beacon. Region
labels are lower-contrast cartographic text; current, hovered and selected
regions receive explicit emphasis. Hover resolves against the authoritative
lookup, brightens the complete exact-fill mesh, temporarily includes that mesh
with a translucent emissive treatment beneath the stellar density, and gives
its label/leader a matching cyan response. Whole-fill post-process glow is
deliberately excluded because it floods close views when a region extends past
the viewport. Clearing hover restores the factual base treatment. Selection
remains the distinct persistent amber state. All overlay elements are
non-interactive so they cannot intercept Babylon picking or camera gestures.

## Plane-fit correction

The first labelled overview exposed a separate V3 presentation fault. The
general camera fit enclosed a 3-D sphere around a flat x/z region source, leaving
the map too small for useful labels. A dedicated top-down plane fit now computes
the limiting horizontal/vertical extent against the actual viewport FOV and
returns the overview to canonical bearing zero. It fills substantially more of
the canvas without clipping the 42-region source square. The general 3-D fit is
unchanged for non-planar scenes.

## Evidence

Deterministic tests cover:

- exact centre and bearing-aware projection;
- shared collision priority and bounded displacement;
- the system-only distance gate and label budget;
- region non-suppression under collision and safe-area pressure;
- the exact 42-name whole-Galaxy atlas and its leader-line endpoints;
- exact-region hover illumination and clear-state restoration;
- planar overview fit versus the general enclosing-sphere fit; and
- Svelte overlay integration, accepted system names and selected styling.

Local WebGPU/WebGL2 diagnostics at 1280×720 and 1440×900 assert three local
system labels, all 42 exact region names and 42 anchor leaders after overview,
canonical overview bearing, existing camera/selection behaviour and non-blank
density/overview canvas captures. Images remain local diagnostic evidence, not
product visual acceptance or a physical-GPU receipt.

Validation at the current map checkpoint: 29 Vitest files / 234 tests pass; Svelte check
reports zero errors/warnings; ESLint and the production build pass; and all four
isolated browser diagnostic scenarios pass across WebGPU and forced WebGL2. The
main Babylon client chunk is 958.79 kB pre-gzip (226.64 kB gzip). The existing
chunk-size warning and exact 3,128.63 kB region asset remain open optimization
inputs.

## Remaining work

- Screen-space overlap selection and a native overlap chooser shared with the
  same candidate registry.
- Complete keyboard/spatial target traversal and virtualized production target
  list.
- A unified semantic zoom/hysteresis reducer for density, stars and labels.
- Representative production-density and production-scale label/performance
  evidence.
- Rich target badges, route/reference labels and direction/range aids.
- Product-route, Firefox and retained physical-GPU visual acceptance.
- System Map body/facility labels and hierarchy-aware placement.

No production data, database or deployment operation is part of this slice.
