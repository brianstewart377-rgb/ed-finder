# Split R3FMapFoundation.tsx Into Scene-Concern Files — Design

## Context

`frontend/src/features/map-foundation/R3FMapFoundation.tsx` is 1663 lines —
more than 3x the next-largest file in its directory (`ProductionMapTab.tsx`
at 524 lines; every other sibling file is under 300 lines). It is item 4 of
the ongoing code-splitting refactor series (item 1: `PlannerCanvasPreview.tsx`
removal, PR #419; item 2: `api.ts` domain-module split, PR #420; item 3:
`MyWorkWorkspace.tsx` component split, PR #421).

**This file is materially higher-stakes than items 1-3.** Per
`docs/ROADMAP.md` (the canonical roadmap — `CLAUDE.md`'s cached summary of
Stage 26A as "the active map authorization contract" is stale): Three.js/R3F
won the Stage 26B three-renderer bake-off, Stage 26C-26D built the production
foundation on it, and **Stage 26E production cutover is complete and in
observation** — commit `3b53477` (then `c0eef72`) deployed this exact
component as the live public map at ed-finder.app, currently being watched
for browser/accessibility/visual/performance regressions post-cutover. The
user confirmed proceeding with this split, with an explicitly elevated
verification bar (manual interaction testing against the live map, not just
static checks) rather than skipping or deferring the item.

## File Structure Today

Read in full before this design was written. Structural map (line numbers
refer to the file as read):

- **Module constants** (56-71): galaxy/keyboard/reduced-motion constants.
- **Types** (73-74): `MapControlKey`, `KeyboardPanPhase`.
- **Pure helpers** (76-198): `mapControlKey`, `protectsFocusFromMap`,
  `keyboardPanTarget`, `galacticCoreGlowPresentation`, `positions`,
  `cameraDistanceForView`, `attenuatedPointSize`, `configureRenderCamera`,
  `projectWorldPoint`.
- **R3F scene sub-components** (200-909), each a component rendered as a
  descendant of `<Canvas>` (several call `useThree()`, so they must stay
  mounted under the Canvas's R3F reconciler — file location does not affect
  this; React context works the same across file boundaries):
  `CameraProjection`, `RendererSizeSync`, `GpuTimingBridge`,
  `RegionBoundaryLines`, `CameraCenterGuide`, `makeGalaxyPointCloud`,
  `makeGalaxyTexture`, `makeGalacticCoreGlowTexture`, `GalacticCoreGlow`,
  `GalaxyBackdrop`, `niceRangeStep`, `rangeStepForView`, `RangeGrid`,
  `ReferenceMarker`, `SceneContents` (the big per-frame scene composer).
- **Label-projection pure functions** (911-995): `projectLabels`,
  `projectSystemLabels`.
- **Main exported component** (997-1663): `R3FMapFoundation` — ~250 lines of
  tightly-interlocked keyboard pan/zoom physics state (12+ `useRef`s and 10+
  `useCallback`s that all close over each other and component-scoped refs:
  `sampleKeyboardPan` → `retargetKeyboardPan` → `applyKeyboardPan` /
  `applyKeyboardZoom` → `applyKeyboardInput` → `keyboardTick` →
  `ensureKeyboardFrame`, plus `recordKeyboardPanFrame`, `stopKeyboardInput`,
  `cancelKeyboardFrame`), pointer/gesture event handling, and the final JSX
  render (the wrapping `<div>`, `<Canvas>`, and four HTML overlay label
  layers).

## Decision

**Extract only the already-self-contained pieces with clean, prop-based
interfaces.** The keyboard/pointer physics block is a single cohesive unit
of interlocking closures over component-scoped refs — extracting it would
require converting it into a custom hook with an explicit parameter/return
contract, which is a *structural* change (different risk class than every
other item in this series: not a pure cut-paste-fix-imports move). That is
out of scope here. It stays in the main file untouched, exactly as today.

Three new files, plus two small additions to the existing `camera.ts`:

1. **`GalaxyBackdrop.tsx`** (new, ~200 lines) — `GALAXY_CENTER`,
   `GALAXY_RADIUS_LY`, `GALAXY_POINT_COUNT`, `GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY`,
   `GALACTIC_CORE_GLOW_WIDE_RADIUS_LY`, `GALACTIC_CORE_GLOW_CLOSE_ZOOM`,
   `GALACTIC_CORE_GLOW_WIDE_ZOOM`, `GALACTIC_CORE_GLOW_HEIGHT_LY` (all
   exported — the main file needs `GALAXY_CENTER` and
   `GALACTIC_CORE_GLOW_HEIGHT_LY` for its `galacticCoreProjection`
   calculation), `makeGalaxyPointCloud`/`makeGalaxyTexture`/
   `makeGalacticCoreGlowTexture` (private), `galacticCoreGlowPresentation`
   (exported — main file needs it too), `GalacticCoreGlow` and
   `GalaxyBackdrop` (exported components).

2. **`SceneDecorations.tsx`** (new, ~220 lines) — `niceRangeStep` (private),
   `rangeStepForView` (exported — main file needs it for the readout text
   and `rangeLabels`), `RegionBoundaryLines`, `CameraCenterGuide`,
   `RangeGrid`, `ReferenceMarker` (exported components).

3. **`SceneContents.tsx`** (new, ~260 lines) — `positions` (private; grepped
   every call site in the current file — used only inside `SceneContents`
   itself, lines 736/740/752, never in the main component body, so it moves
   here in full rather than staying in the main file), `configureRenderCamera`
   (private — only its own `projectWorldPoint`/`projectLabels`/
   `projectSystemLabels` in this same file call it), `projectWorldPoint`
   (exported — main file needs it for `galacticCoreProjection`),
   `CameraProjection`, `RendererSizeSync`, `GpuTimingBridge`, `SceneContents`
   (exported components — the main file renders `RendererSizeSync`,
   `GpuTimingBridge`, and `SceneContents` directly; `CameraProjection` is
   only rendered inside `SceneContents`'s own JSX, so it stays unexported
   from the main file's perspective but must still be `export`ed from this
   file since `SceneContents` — defined in the same file — uses it),
   `projectLabels`, `projectSystemLabels` (exported — main file needs both).

4. **`camera.ts`** (existing, 138 lines, pure math with zero Three.js/React
   imports today) gains two small pure exports that fit its existing
   character: `cameraDistanceForView` and `attenuatedPointSize` — both plain
   zoom/viewport math with no Three.js dependency, unlike
   `configureRenderCamera`/`projectWorldPoint` which directly construct and
   manipulate `THREE.PerspectiveCamera`/`THREE.Vector3` and so belong with
   the Three.js-coupled scene code (`SceneContents.tsx`) instead, keeping
   `camera.ts`'s current dependency-free character intact. Both new exports
   are needed by more than one consumer (`attenuatedPointSize` by both
   `ReferenceMarker` in `SceneDecorations.tsx` and `SceneContents` in
   `SceneContents.tsx`; `cameraDistanceForView` by `SceneContents.tsx` and,
   indirectly, nothing else) — routing them through the existing shared
   utility file avoids a direct dependency between the two new sibling
   files.

5. **`R3FMapFoundation.tsx`** (shrinks from 1663 to roughly 1000 lines) —
   keeps the keyboard-physics constants/types (`KEYBOARD_PAN_PIXELS_PER_SECOND`
   etc., `REDUCED_MOTION_QUERY`, `MapControlKey`, `KeyboardPanPhase`),
   `mapControlKey`/`protectsFocusFromMap`/`keyboardPanTarget` (used only by
   the keyboard-physics block that stays), and the full exported
   `R3FMapFoundation` function unchanged except for its import block and the
   fact that `SceneContents`, `RendererSizeSync`,
   `GpuTimingBridge`, `GALAXY_CENTER`, `GALACTIC_CORE_GLOW_HEIGHT_LY`,
   `galacticCoreGlowPresentation`, `rangeStepForView`, `projectWorldPoint`,
   `projectLabels`, `projectSystemLabels` are now imports instead of
   file-local definitions.

## Dependency Graph

Acyclic, one direction only:

```
camera.ts (existing, +2 exports)
    ^                    ^
    |                    |
GalaxyBackdrop.tsx   SceneDecorations.tsx
    ^                    ^
    |                    |
    +---- SceneContents.tsx ----+
              ^
              |
     R3FMapFoundation.tsx (main)
```

`SceneContents.tsx` imports `GalaxyBackdrop`/`GalacticCoreGlow` from
`GalaxyBackdrop.tsx` and `RegionBoundaryLines`/`CameraCenterGuide`/
`RangeGrid`/`ReferenceMarker` from `SceneDecorations.tsx` (both rendered
inside `SceneContents`'s own JSX). The main file imports from all three new
files plus the two new `camera.ts` exports, but the three new files never
import from the main file or from each other except via `SceneContents.tsx`
as described. No circular imports.

## No Logic Changes

Every function body, every JSX tree, every prop moves verbatim. No renderer
behavior, camera math, keyboard-control feel, visual output, or performance
characteristic changes. This is pure code movement.

## Verification (elevated bar — see Context)

Same automated gate as items 1-3: `yarn typecheck`, `yarn lint`,
`yarn knip --files`, `yarn test`, `yarn build`.

Plus, because this is the live production map renderer under active
post-cutover observation, an elevated manual verification pass against a
live local dev server + local API server:
- Load the Map route and confirm the galaxy view, region boundaries, and
  labels render identically to pre-change behavior.
- Pan (drag and WASD), zoom (scroll/pinch/Z-X keys), and tilt (shift-drag)
  the camera; confirm smooth motion with no console errors.
- Click/hover a system to confirm selection and hover-highlight still work.
- Switch view presets (galaxy / reference / results) if reachable from the
  UI in this environment, to exercise `RangeGrid`/`ReferenceMarker`'s
  conditional rendering.
- Confirm the render-stats readout and keyboard-shortcut `aria-label`
  affordances are unchanged.
- Compare against the existing `R3FMapFoundation.test.tsx` (589 lines) test
  suite results before and after — this suite already exercises data-testid/
  data-attribute contracts (`data-camera-*`, `data-current-region-*`,
  `data-galactic-core-*`, `data-keyboard-pan-*`) that would catch a wiring
  mistake typecheck cannot.

## Out of Scope

- The keyboard/pointer physics block and final JSX render in the main file
  (see Decision above — a hook extraction is a different, riskier class of
  change, not attempted here).
- No behavior, visual, or performance changes of any kind.
- No other file in `map-foundation/` is touched.
