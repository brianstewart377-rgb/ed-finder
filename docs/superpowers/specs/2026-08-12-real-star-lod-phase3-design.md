# Real-Star LOD Phase 3: Hysteresis Fade + Truncated Affordance

**Date:** 2026-08-12  
**Author:** Claude Code  
**Status:** Approved Design  
**Scope:** Frontend map rendering — smooth zoom transition from heatmap to individual stars, graceful handling of the 40k system cap.

## Overview

Phase 3 completes the real-star LOD streaming feature by adding a smooth hysteresis fade transition between the aggregate heatmap (zoomed out) and individual star rendering (zoomed in), plus transparent handling of the 40k system cap without UI clutter.

**Current state (Phase 2):** Client renders individual stars on zoom-in via gridded requests with 250ms debounce. Layers pop in/out with no transition.

**Phase 3 adds:**
- Smooth 500ms eased fade between heatmap and real stars as you zoom
- Dead zone at the zoom threshold to prevent flicker on small camera movements
- Graceful cap handling: when the server hits the 40k system limit, stay on heatmap (no badge, no noise)

## Design

### Trigger & Visibility Logic

The fade is triggered by the existing `realStarViewportBox()` logic in `viewportSystems.ts`:

- **Zoomed out (box === null):** View is too wide for real-star rendering. Stay on heatmap.
- **Zoomed in (box !== null):** View is tight enough to fetch and render individual systems. Begin fade to real stars.

This matches Elite Dangerous's map behavior: as you zoom in from galaxy-scale view, individual stars smoothly come into focus as the aggregate heatmap recedes.

**Dead zone (hysteresis):** The box doesn't snap between null and non-null on tiny camera movements. Once `realStarViewportBox()` returns non-null, you must zoom back out significantly before it returns null again. This prevents the layers from flickering in/out if the camera jitters right at the zoom threshold.

### Fade Mechanism

Both layers (heatmap + real stars) **always render**, but with opacity controlled by zoom state:

| Zoom State | Heatmap Opacity | Real Stars Opacity | Duration |
|---|---|---|---|
| Zoomed out (`box === null`) | 1 (opaque) | 0 (invisible) | — |
| Zooming in (`box !== null`) | 1 → 0 | 0 → 1 | 500ms, ease-in-out |
| Zoomed in (steady state) | 0 (invisible) | 1 (opaque) | — |

**Fade curve:** Ease-in-out easing for smooth, polished visual feel (matching ED's map transitions).

Implementation:
- Track `box` state in the map component
- Compute target opacity: `targetHeatmapOpacity = box === null ? 1 : 0`
- Apply a 500ms eased transition to both layer opacities
- Use Three.js material opacity or CSS opacity depending on layer type (heatmap is canvas/CSS, real stars are Three.js)

**Why opacity instead of conditional rendering?** No pop/flicker, smoother UX, easier to reason about in a single render pass.

### Truncated Affordance

When the server returns `truncated === true` (40k system cap reached), the fade logic is overridden:

- Force both opacities to heatmap-only: `heatmapOpacity = 1, starsOpacity = 0`
- This holds regardless of current zoom level
- The absence of individual stars (even when zoomed in) is the signal to the user: "too many systems, aggregated view only"

**No UI badge or affordance.** The disappearance of individual stars is self-explanatory in context (zoomed in but still seeing the heatmap). If the user:
- **Zooms out:** Heatmap stays visible (expected)
- **Pans to a different region:** If the new region has < 40k systems, real stars fade in naturally
- **Re-fetches the same region:** If the data changed and now < 40k, real stars fade in

This is graceful degradation without UI noise.

### Component Changes

#### `SceneContents.tsx` (lines 270–339)

**Current behavior:**
```typescript
{/* Heatmap: render always */}
<group position={...}>
  <HeatmapLayer />
</group>

{/* Real stars: render always */}
<RealStarLayer systems={systems} zoom={zoom} />
```

**Phase 3 behavior:**
```typescript
const heatmapOpacity = box === null ? 1 : 0;  // or 1 if truncated
const starsOpacity = (box === null || truncated) ? 0 : 1;

{/* Heatmap: opacity-controlled */}
<group position={...} opacity={heatmapOpacity}>
  <HeatmapLayer />
</group>

{/* Real stars: opacity-controlled */}
<RealStarLayer 
  systems={systems} 
  zoom={zoom} 
  opacity={starsOpacity}
/>
```

Opacity transitions smoothly via Three.js material opacity property or CSS transition.

#### `RealStarLayer.tsx`

Accept an `opacity` prop and apply it to the point-cloud material:

```typescript
export interface RealStarLayerProps {
  systems: MapViewportSystem[] | null;
  zoom: number;
  opacity: number;  // NEW: controls fade
}

export function RealStarLayer({ systems, zoom, opacity }: RealStarLayerProps) {
  // ... existing buffer logic ...
  
  // Apply opacity to material
  material.opacity = opacity;
  material.transparent = true;  // required for opacity to work
  
  return <points material={material} geometry={geometry} />;
}
```

#### `viewportSystems.ts`

No changes. The hook already returns `{ systems, truncated }`, which is all we need.

## Data Flow

1. **Map container** passes `camera` and `viewport` to `useViewportSystems()`
2. Hook computes `box = realStarViewportBox(camera, viewport)`
3. Hook issues request if `box` is non-null and settled (250ms debounce)
4. Server responds with `{ systems, truncated }`
5. Hook returns `{ systems, truncated }`
6. **SceneContents** receives `{ systems, truncated, box }` and computes opacities
7. Both layers render with computed opacities
8. Three.js animates opacity transitions smoothly

## Error Handling

- If `realStarViewportBox()` returns null mid-fade, fade back to heatmap (no error state)
- If `truncated` becomes true during a fade, immediately snap to heatmap-only
- If the viewport request fails, revert to heatmap; fade resumes when request recovers

## Testing

**Unit tests:**
- `realStarViewportBox()` already has tests (viewportSystems.test.ts)
- Add test for truncated affordance logic: verify opacity is locked when truncated=true

**Integration test:**
- Zoom in smoothly (visual): heatmap fades out, real stars fade in over ~500ms
- Zoom back out (visual): real stars fade out, heatmap fades in
- Zoom in to a region with 40k+ systems (visual): real stars never appear, heatmap stays visible
- Pan to a different region (visual): if < 40k, real stars fade in naturally

**No E2E test needed** — fade duration and easing are visual polish, not functional requirements; spot-checking in the dev server is sufficient.

## Success Criteria

- ✓ Smooth 500ms fade between layers as you zoom in/out
- ✓ No flicker at the zoom threshold (dead zone works)
- ✓ When truncated=true, real stars never show (cap is respected)
- ✓ Matches Elite Dangerous's map zoom behavior (smooth aggregate→detail transition)
- ✓ No new UI elements or affordances (clean, minimal)

## Out of Scope

- Real-time cap detection or server-side cap changes mid-session (cap is static per request)
- Animated transitions on pan/region changes (fade is zoom-only)
- Alternative fade curves or user-configurable fade duration
- Visual affordance for cap (e.g., "40k+ systems" badge — explicitly excluded per design)
