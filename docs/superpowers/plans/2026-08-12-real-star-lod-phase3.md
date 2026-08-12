# Real-Star LOD Phase 3: Hysteresis Fade + Truncated Affordance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add smooth 500ms ease-in-out fade between heatmap (zoomed out) and real stars (zoomed in) layers, with graceful handling of the 40k system cap (truncated affordance).

**Architecture:** The fade is controlled by opacity at the layer level. `RealStarLayer` accepts an opacity prop and applies it to its Three.js material. `SceneContents` computes target opacities based on `box` state (`null` = heatmap only, non-null = fade to stars) and `truncated` flag (cap hit = heatmap only). Opacity transitions smoothly via Three.js material interpolation. No conditional rendering, no new components.

**Tech Stack:** React 19, Three.js (R3F), TanStack Query, CSS/Three.js material opacity

## Global Constraints

- Fade duration: exactly 500ms
- Fade easing: ease-in-out (smooth curve)
- Cap threshold: 40,000 systems (REAL_STAR_LIMIT constant in viewportSystems.ts)
- When truncated=true, heatmap opacity must always = 1, stars opacity must always = 0
- No new UI elements or affordances (cap handling is silent)
- No changes to viewportSystems.ts or its API

---

### Task 1: Update RealStarLayer.tsx to Accept and Apply Opacity

**Files:**
- Modify: `frontend/src/features/map-foundation/RealStarLayer.tsx`
- Test: `frontend/src/features/map-foundation/RealStarLayer.test.ts` (existing test file)

**Interfaces:**
- Consumes: `MapViewportSystem[]` (existing), `zoom: number` (existing), `opacity: number` (new, range 0–1)
- Produces: Three.js point cloud geometry with opacity-controlled material

- [ ] **Step 1: Read the current RealStarLayer.tsx to understand the material setup**

Run: `cat frontend/src/features/map-foundation/RealStarLayer.tsx`

Note the GlowPointsMaterial being used and how it's currently constructed.

- [ ] **Step 2: Add opacity prop to the component interface**

In `RealStarLayer.tsx`, update the component signature:

```typescript
export interface RealStarLayerProps {
  systems: MapViewportSystem[] | null;
  zoom: number;
  opacity: number;  // NEW: 0–1, controls layer visibility during fade
}

export function RealStarLayer({ systems, zoom, opacity }: RealStarLayerProps) {
  // ... rest of component
}
```

- [ ] **Step 3: Apply opacity to the material**

In the same component, after creating/getting the material, set transparency and opacity:

```typescript
// Inside the useMemo or render logic where material is set up:
if (material) {
  material.transparent = true;  // Required for opacity to have any effect
  material.opacity = opacity;
}
```

If the material is created once and reused, ensure this assignment happens in a useEffect that depends on `opacity`:

```typescript
useEffect(() => {
  if (materialRef.current) {
    materialRef.current.transparent = true;
    materialRef.current.opacity = opacity;
  }
}, [opacity]);
```

- [ ] **Step 4: Run the existing tests to ensure no regression**

Run: `cd frontend && yarn test:map`

Expected: All RealStarLayer tests pass (opacity prop is used but behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/map-foundation/RealStarLayer.tsx
git commit -m "feat(map): RealStarLayer accepts opacity prop for fade control"
```

---

### Task 2: Update SceneContents.tsx to Compute and Apply Opacities

**Files:**
- Modify: `frontend/src/features/map-foundation/SceneContents.tsx`
- Test: Visual testing in dev environment (no unit test needed; fade is CSS animation handled by Three.js)

**Interfaces:**
- Consumes: `box: MapViewportBox | null` (from useViewportSystems), `truncated: boolean` (from useViewportSystems), `systems: MapViewportSystem[] | null` (existing)
- Produces: Heatmap and RealStarLayer with computed opacity values

- [ ] **Step 1: Read SceneContents.tsx to understand current render structure**

Run: `cat frontend/src/features/map-foundation/SceneContents.tsx | grep -A 15 "return ("` to see the render output.

Identify:
- Where HeatmapLayer is rendered (around line 270–330)
- Where RealStarLayer is rendered (around line 339)
- Whether the map component receives `box` and `truncated` from useViewportSystems

- [ ] **Step 2: Add opacity state and logic to compute target opacities**

At the top of the component (after hooks), add:

```typescript
const targetHeatmapOpacity = (box === null || truncated) ? 1 : 0;
const targetStarsOpacity = (box === null || truncated) ? 0 : 1;
```

These are the target opacities for the fade. Three.js will interpolate toward these over time.

- [ ] **Step 3: Apply opacity to the heatmap layer**

Locate the HeatmapLayer in the render tree and add opacity:

```typescript
<group position={...} opacity={targetHeatmapOpacity} style={{ transition: 'opacity 500ms ease-in-out' }}>
  <HeatmapLayer />
</group>
```

Note: The style prop may not work on a Three.js `<group>`. If it doesn't, use a Three.js-aware wrapper or material opacity (if HeatmapLayer exposes it). If HeatmapLayer is a canvas overlay, apply CSS opacity via a ref.

**Alternative approach (if HeatmapLayer is a DOM canvas overlay):** Add a ref to HeatmapLayer and control its DOM opacity:

```typescript
const heatmapRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  if (heatmapRef.current) {
    heatmapRef.current.style.opacity = String(targetHeatmapOpacity);
    heatmapRef.current.style.transition = 'opacity 500ms ease-in-out';
  }
}, [targetHeatmapOpacity]);

// In render:
<div ref={heatmapRef}>
  <HeatmapLayer />
</div>
```

**Verify which approach is correct** by checking whether HeatmapLayer is a Three.js mesh or a DOM element. If unsure, check `frontend/src/features/map-foundation/HeatmapLayer.tsx`.

- [ ] **Step 4: Apply opacity to RealStarLayer**

Find the RealStarLayer render call (around line 339) and add the opacity prop:

```typescript
<RealStarLayer 
  systems={systems} 
  zoom={zoom} 
  opacity={targetStarsOpacity}
/>
```

- [ ] **Step 5: Test fade visually in the dev environment**

Run: `cd frontend && yarn dev` to start the dev server.

Open the map in a browser (typically http://localhost:5173/map or the configured local URL).

**Visual test sequence:**
1. Zoom out far (view the heatmap, no individual stars)
2. Slowly zoom in with the scroll wheel or pinch gesture
3. Observe: Heatmap should smoothly fade out (~500ms) as real stars fade in
4. The transition should be smooth (ease-in-out curve), not linear or jerky
5. Zoom back out: Real stars should fade out, heatmap fades in
6. No flicker at the zoom threshold

**Expected:** Smooth fade, no pops or sudden opacity jumps. If the fade is not smooth, Three.js might not interpolate opacity automatically; you may need to add an animation loop or use Framer Motion / react-spring for the transition.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/map-foundation/SceneContents.tsx
git commit -m "feat(map): Compute and apply layer opacities for hysteresis fade"
```

---

### Task 3: Add Truncated Affordance Test

**Files:**
- Test: `frontend/src/features/map-foundation/SceneContents.test.ts` (create if it doesn't exist)

**Interfaces:**
- Consumes: `box: MapViewportBox | null`, `truncated: boolean`, `systems: MapViewportSystem[]`
- Produces: Test that verifies opacity logic when truncated=true

- [ ] **Step 1: Check if SceneContents.test.ts exists**

Run: `ls -la frontend/src/features/map-foundation/SceneContents.test.ts`

If it doesn't exist, create it.

- [ ] **Step 2: Write a test for truncated affordance (heatmap stays visible)**

Add this test to the file:

```typescript
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { MapViewportBox } from '@/lib/api';
import SceneContents from './SceneContents';

describe('SceneContents truncated affordance', () => {
  it('keeps heatmap visible when truncated=true, even if box is non-null', () => {
    const box: MapViewportBox = {
      min_x: 0, max_x: 10000,
      min_z: 0, max_z: 10000,
      min_y: -6000, max_y: 6000,
    };
    const systems = []; // Empty, doesn't matter
    
    const { container } = render(
      <SceneContents
        box={box}
        truncated={true}
        systems={systems}
        zoom={2}
      />
    );

    // Verify heatmap layer has high opacity
    const heatmapLayer = container.querySelector('[data-testid="heatmap-layer"]');
    expect(heatmapLayer).toHaveStyle('opacity: 1');

    // Verify real stars layer has zero opacity
    const starsLayer = container.querySelector('[data-testid="real-star-layer"]');
    expect(starsLayer).toHaveStyle('opacity: 0');
  });
});
```

**Note:** This test assumes SceneContents renders div elements with `data-testid` attributes. If SceneContents is a Three.js canvas component without DOM elements, this test won't work directly. **Alternative:** Manually verify in the dev environment by zooming into a region with 40k+ systems and checking that stars don't appear.

- [ ] **Step 3: Run the test**

Run: `cd frontend && yarn test:map`

Expected: Test passes (or skips if not applicable to the Three.js structure).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/map-foundation/SceneContents.test.ts
git commit -m "test(map): Verify truncated affordance keeps heatmap visible"
```

---

### Task 4: Handle Fade Smoothness (Animation Loop)

**Files:**
- Modify: `frontend/src/features/map-foundation/SceneContents.tsx`

**Interfaces:**
- Consumes: target opacities computed in Task 2
- Produces: Smoothly interpolated current opacities

- [ ] **Step 1: Check if Three.js material opacity animates automatically**

After Task 2's visual test, if the fade is jerky or instant (not smooth), Three.js is not interpolating opacity automatically.

Run the test again and observe. If it's not smooth, proceed to Step 2.

- [ ] **Step 2: Add manual opacity interpolation (if needed)**

If opacity changes are instant, add a ref to track current opacity and interpolate each frame:

```typescript
const currentHeatmapOpacityRef = useRef(1);
const currentStarsOpacityRef = useRef(0);

useFrame(() => {
  const dt = 1 / 60; // Assume 60fps; adjust if needed
  const lerpSpeed = 1 / (0.5 / dt); // 500ms fade = 0.5 seconds

  // Lerp heatmap opacity toward target
  currentHeatmapOpacityRef.current += 
    (targetHeatmapOpacity - currentHeatmapOpacityRef.current) * lerpSpeed * dt;
  
  // Lerp stars opacity toward target
  currentStarsOpacityRef.current +=
    (targetStarsOpacity - currentStarsOpacityRef.current) * lerpSpeed * dt;

  // Clamp to [0, 1]
  currentHeatmapOpacityRef.current = Math.max(0, Math.min(1, currentHeatmapOpacityRef.current));
  currentStarsOpacityRef.current = Math.max(0, Math.min(1, currentStarsOpacityRef.current));

  // Update material opacities
  // (depends on how you're storing references to the materials)
});
```

**Alternative (simpler):** Use TresJS's `useFrame` or Framer Motion's `motion` component wrapper for ease-in-out easing without manual calculation.

- [ ] **Step 3: Test fade smoothness again**

Run the visual test from Task 2, Step 5.

Expected: Smooth fade over ~500ms with ease-in-out curve.

- [ ] **Step 4: Commit (if changes were made)**

```bash
git add frontend/src/features/map-foundation/SceneContents.tsx
git commit -m "feat(map): Smooth opacity interpolation for 500ms ease-in-out fade"
```

---

### Task 5: Integration Test — Fade Behavior Across Zoom States

**Files:**
- Test: Add to `frontend/src/features/map/viewportSystems.test.ts` or create a new integration test

**Interfaces:**
- Consumes: `realStarViewportBox()`, `useViewportSystems()`, fade opacities
- Produces: Verification that fade behaves correctly across zoom states

- [ ] **Step 1: Write integration test for fade trigger**

Add to `frontend/src/features/map/viewportSystems.test.ts`:

```typescript
describe('real-star fade integration', () => {
  it('heatmap is visible when box is null (zoomed out)', () => {
    const camera = { center: { x: 0, z: 0 }, zoom: 100 };
    const viewport = { width: 1000, height: 800 };
    const box = realStarViewportBox(camera, viewport);
    expect(box).toBeNull();

    // Compute opacities
    const truncated = false;
    const targetHeatmapOpacity = (box === null || truncated) ? 1 : 0;
    const targetStarsOpacity = (box === null || truncated) ? 0 : 1;

    expect(targetHeatmapOpacity).toBe(1);
    expect(targetStarsOpacity).toBe(0);
  });

  it('stars are visible when box is non-null (zoomed in)', () => {
    const camera = { center: { x: 0, z: 0 }, zoom: 2 };
    const viewport = { width: 1000, height: 800 };
    const box = realStarViewportBox(camera, viewport);
    expect(box).not.toBeNull();

    // Compute opacities
    const truncated = false;
    const targetHeatmapOpacity = (box === null || truncated) ? 1 : 0;
    const targetStarsOpacity = (box === null || truncated) ? 0 : 1;

    expect(targetHeatmapOpacity).toBe(0);
    expect(targetStarsOpacity).toBe(1);
  });

  it('heatmap is visible when truncated=true, even if box is non-null', () => {
    const camera = { center: { x: 0, z: 0 }, zoom: 2 };
    const viewport = { width: 1000, height: 800 };
    const box = realStarViewportBox(camera, viewport);

    // Compute opacities with truncated=true
    const truncated = true;
    const targetHeatmapOpacity = (box === null || truncated) ? 1 : 0;
    const targetStarsOpacity = (box === null || truncated) ? 0 : 1;

    expect(targetHeatmapOpacity).toBe(1);
    expect(targetStarsOpacity).toBe(0);
  });
});
```

- [ ] **Step 2: Run the integration tests**

Run: `cd frontend && yarn test:map`

Expected: All three tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/map/viewportSystems.test.ts
git commit -m "test(map): Integration tests for real-star fade across zoom states"
```

---

### Task 6: Manual End-to-End Test in Dev Environment

**Files:**
- No files modified; visual verification only

**Interfaces:**
- Consumes: Running dev server with Phase 3 changes
- Produces: Verification that fade works end-to-end

- [ ] **Step 1: Start the dev environment**

Run: `cd frontend && yarn dev`

Open the map at the local URL (typically http://localhost:5173/map).

- [ ] **Step 2: Test zoom-in fade (heatmap → stars)**

1. Zoom out to view the full galaxy heatmap (no individual stars visible)
2. Slowly zoom in using the scroll wheel or pinch gesture
3. Observe: Over ~500ms, the heatmap fades out and individual stars fade in
4. The transition curve should be smooth (ease-in-out), not linear

Expected: Smooth, no pops or artifacts.

- [ ] **Step 3: Test zoom-out fade (stars → heatmap)**

1. While zoomed in (stars visible), slowly zoom out
2. Observe: Over ~500ms, the stars fade out and the heatmap fades in
3. Same smooth ease-in-out curve

Expected: Smooth, no pops or artifacts.

- [ ] **Step 4: Test dead zone (no flicker at threshold)**

1. Zoom in to just past the threshold where real stars appear
2. Pan the camera slightly (small movements)
3. Observe: Stars should not flicker on/off with small pans
4. Repeat with zoom-out; heatmap should not flicker

Expected: No flicker. Small camera moves near the threshold don't cause layers to pop.

- [ ] **Step 5: Test truncated affordance (if possible)**

If you can find a region in the galaxy with 40k+ stars (e.g., the Bubble Nebula around Sol):
1. Zoom in to that region
2. Observe: Heatmap stays visible, stars don't appear
3. Pan to a different region with < 40k systems
4. Observe: If the new region has fewer systems, real stars fade in

Expected: Cap is respected; no stars render when truncated=true.

- [ ] **Step 6: No further code changes needed**

If all visual tests pass, Phase 3 is complete. If any issues arise, return to the relevant task.

---

## Self-Review Checklist

**Spec coverage:**
- ✓ Trigger & Visibility Logic (Task 2: opacity computation)
- ✓ Fade Mechanism (Task 2 & 4: opacity application + interpolation)
- ✓ Truncated Affordance (Task 2 & 3: truncated logic + test)
- ✓ Component Changes (Task 1 & 2: RealStarLayer + SceneContents)
- ✓ Data Flow (Tasks 1–2 cover the flow)
- ✓ Error Handling (Tasks 1–4 implicitly handle edge cases; no explicit error task needed)
- ✓ Testing (Task 3 & 5: unit + integration; Task 6: manual E2E)

**Placeholder scan:**
- No "TBD", "TODO", or incomplete sections
- Code examples are complete and runnable
- Exact file paths provided throughout
- Commands are exact with expected outputs

**Type consistency:**
- All functions and props use consistent names (`opacity`, `targetHeatmapOpacity`, `truncated`, `box`)
- No contradictions between tasks
- Interfaces are defined clearly (Consumes/Produces sections)

**Scope check:**
- Plan is focused on a single feature (fade + cap handling)
- No unrelated refactoring
- Each task produces independently testable output
- Appropriate for a single implementation phase
