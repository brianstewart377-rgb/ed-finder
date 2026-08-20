# Map Testing Strategy — Best-in-Class Rendering Verification

## Goal
Ensure map rendering, interactions, and performance are genuinely working, not just mocked. Tests must verify the actual 3D scene, not just logic or API calls.

## Current Gaps
- ❌ React Three Fiber completely mocked in unit tests
- ❌ No visual verification (stars/heatmap actually appear on canvas)
- ❌ No buffer/geometry verification (position/color data correct)
- ❌ No animation timing tests (fade actually animates)
- ❌ No WebGL state verification (uniforms, material states)

## Testing Pyramid

### Layer 1: Pure Logic Unit Tests ✅ (Already strong)
- Math: coordinate transforms, camera setup, frustum calculations
- Easing: fade curves, animation timing
- Thresholds: hysteresis boundary detection
- **Coverage:** 100% branches for deterministic functions

**Example:** `shouldEnableRealStarDetail` threshold logic

### Layer 2: Buffer & Geometry Unit Tests (NEW - needs implementation)
- ✅ `buildRealStarBuffers()` produces correct dimensions
- ✅ Position data matches system coordinates (x→x, y→z, z→y)
- ✅ Color buffers contain valid RGB values
- ✅ Spectral colors map correctly (O→blue, M→red)
- ✅ Handles empty arrays without crashing
- ✅ Large arrays (40k systems) stay within memory budgets

**Test:** `viewportSystems.buffers.test.ts`

```typescript
it('buildRealStarBuffers produces correct position/color layout', () => {
  const systems = [
    { x: 100, y: 0, z: 50, main_star_class: 'O', ... },
    { x: 200, y: 10, z: 60, main_star_class: 'M', ... },
  ];
  const { positions, colors } = buildRealStarBuffers(systems);
  
  // Check positions: [x, z, y] per system (3 values each)
  expect(positions.length).toBe(6);
  expect([positions[0], positions[1], positions[2]]).toEqual([100, 50, 0]);
  
  // Check colors: RGB per system (3 values each)
  expect(colors.length).toBe(6);
  // O-class should be blue-ish
  const oClassColor = [colors[0], colors[1], colors[2]];
  expect(oClassColor[2]).toBeGreaterThan(oClassColor[0]); // B > R
});
```

### Layer 3: Interaction & State Unit Tests ✅ (Existing, needs expansion)
- `useViewportSystems` hook with settle timer
- Camera change detection
- Query caching behavior
- Error state handling

**Status:** Mostly covered, but test infrastructure issues (vitest timeout)

### Layer 4: Integration Tests with Real Canvas (NEW - critical)
Create a test harness that:
- Mounts actual R3F/Three.js scene (not mocked)
- Renders to an offscreen canvas
- Queries WebGL state (uniforms, buffers, materials)
- Measures frame timing without mocks

**Example tools:**
- Three.js's built-in `WebGLRenderTarget` for headless rendering
- Query shader uniforms: `material.uniforms.uOpacity.value`
- Verify buffer binding: `geometry.attributes.position`
- Snapshot canvas pixels for color verification

### Layer 5: E2E Visual Tests with Playwright (NEW - highest confidence)
Real browser, real rendering, real verification.

**Test categories:**

#### A. Real-Star Rendering
```typescript
test('real stars render when zoomed in', async ({ page }) => {
  // 1. Zoom in to trigger viewport query
  // 2. Wait for API response
  // 3. Query page for actual rendered points:
  //    - Verify canvas pixel count changes
  //    - Check for expected colors in canvas
  //    - Verify glow effect present (pixel brightness > base)
  // 4. Compare canvas pixels before/after zoom
});

test('star colors match spectral type', async ({ page }) => {
  // 1. Zoom to a known system (Sol, spectral G)
  // 2. Measure canvas color at star position
  // 3. Verify it's in yellow-ish range (G-class color)
  // 4. Compare to reference color chart
});
```

#### B. Zoom Threshold Behavior
```typescript
test('zoom threshold has hysteresis (no flicker)', async ({ page }) => {
  // 1. Start at galaxy view (stars hidden)
  // 2. Zoom in past ENTER threshold (5000 LY)
  // 3. Verify stars appear
  // 4. Zoom back out but STAY above ENTER threshold
  // 5. Verify stars still visible (hysteresis prevents exit)
  // 6. Zoom out past EXIT threshold (8000 LY)
  // 7. Verify stars disappear
  // 8. Measure time at boundary - should see NO intermediate flashes
});
```

#### C. Fade Animation
```typescript
test('real-star fade animates smoothly', async ({ page }) => {
  // 1. Zoom in to trigger real stars
  // 2. Capture canvas pixel samples every 50ms
  // 3. Measure brightness curve (should be smooth easing, not step)
  // 4. Verify matches easeInOutCubic curve shape
  // 5. Duration should be ~500ms (REAL_STAR_FADE_DURATION_S)
});
```

#### D. Large Dataset Performance
```typescript
test('rendering 40k stars stays under 50ms per frame', async ({ page }) => {
  // 1. Mock API to return 40k systems (the cap)
  // 2. Zoom in to trigger rendering
  // 3. Measure frame time for 10 frames
  // 4. Verify p95 < 50ms (verified in Stage 26E)
});
```

#### E. Interaction with Real Stars
```typescript
test('clicking a real star selects it', async ({ page }) => {
  // 1. Zoom in to trigger real stars
  // 2. Identify a rendered star (via API response + canvas position math)
  // 3. Click at star pixel location
  // 4. Verify selectSystem interaction fired with correct id64
  // 5. Verify system appears selected (highlight ring)
});
```

### Layer 6: Regression Suite (Continuous)
- Run full E2E every deploy
- Screenshot comparison for visual regressions (glow effect, colors)
- Performance regression detection (frame time trending)
- Zoom threshold margin testing (confirm still above enter, below exit)

## Implementation Roadmap

### Phase 1: Buffer Tests (This PR)
- Add `viewportSystems.buffers.test.ts`
- Test buildRealStarBuffers correctness
- Verify spectral color mapping
- Memory budget tests

### Phase 2: Canvas Integration (Follow-up)
- Create E2E test harness with real R3F/Three.js
- Canvas pixel analysis utilities
- Zoom behavior verification
- Fade animation timing tests

### Phase 3: Full Visual E2E (Stabilization)
- Real-star rendering Playwright tests
- Interaction verification
- Performance regression suite
- Color accuracy validation

## Key Metrics to Track

| Metric | Target | How to Test |
|--------|--------|------------|
| Real stars appear when zoomed in | 100% | E2E canvas pixel analysis |
| Spectral colors are accurate | ±10% hue error | E2E color sampling |
| No flicker at zoom threshold | 0 flashes in 10s | E2E temporal analysis |
| Fade duration | 500ms ±50ms | E2E animation timing |
| Frame time with 40k stars | <50ms p95 | E2E performance measurement |
| Interaction latency | <100ms | E2E click-to-event timing |

## Tools & Libraries

- **Three.js testing:** `canvas.getContext('webgl2')` for context queries
- **Pixel analysis:** `canvas.getImageData()` for color verification
- **Playwright:** `page.locator('canvas').screenshot()` for visual regression
- **Animation timing:** `page.evaluate()` with `performance.now()` for frame measurements

## Success Criteria

All of the following must pass in CI before merging Phase 2:
- ✅ All unit tests for buffer building (new)
- ✅ TypeScript strict mode with no errors
- ✅ Zoom threshold behavior E2E test
- ✅ Real-star rendering E2E test (stars appear)
- ✅ Fade animation timing within ±50ms
- ✅ No performance regressions vs baseline
- ✅ No accessibility violations (Axe)
- ✅ No console errors or warnings in E2E

This ensures Phase 2 is not just shipped, but proven to work in the real product environment.
