import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { realStarViewportBox, shouldEnableRealStarDetail, realStarViewportSpan } from './viewportSystems';

describe('viewport systems settle timer logic', () => {
  const viewport = { width: 1280, height: 720 };
  const camera = { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0.5 };

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('should create box when detail is enabled', () => {
    const shouldEnable = shouldEnableRealStarDetail(camera, viewport, false);
    expect(shouldEnable).toBe(true);

    const box = realStarViewportBox(camera, viewport);
    expect(box).not.toBeNull();
    expect(box?.min_x).toBeDefined();
    expect(box?.max_x).toBeDefined();
    expect(box?.min_z).toBeDefined();
    expect(box?.max_z).toBeDefined();
  });

  it('box should be stable when camera values stay same', () => {
    const box1 = realStarViewportBox(camera, viewport);
    const box2 = realStarViewportBox(camera, viewport);

    // Same camera/viewport should produce same box values
    expect(box1?.min_x).toBe(box2?.min_x);
    expect(box1?.max_x).toBe(box2?.max_x);
    expect(box1?.min_z).toBe(box2?.min_z);
    expect(box1?.max_z).toBe(box2?.max_z);
  });

  it('box should change when camera position changes', () => {
    const box1 = realStarViewportBox(camera, viewport);
    const panCamera = { ...camera, center: { x: 1000, z: 1000 } };
    const box2 = realStarViewportBox(panCamera, viewport);

    // Different camera position should produce different box
    expect(box1?.min_x).not.toBe(box2?.min_x);
    expect(box1?.max_x).not.toBe(box2?.max_x);
  });

  it('box should change when zoom changes', () => {
    const box1 = realStarViewportBox(camera, viewport);
    const zoomedCamera = { ...camera, zoom: 5 };  // Zoom out but stay below 8000 LY threshold
    const box2 = realStarViewportBox(zoomedCamera, viewport);

    // Different zoom should produce different box span
    const span1 = Math.max(box1!.max_x - box1!.min_x, box1!.max_z - box1!.min_z);
    const span2 = Math.max(box2!.max_x - box2!.min_x, box2!.max_z - box2!.min_z);
    expect(span2).toBeGreaterThan(span1);
  });

  it('threshold should have hysteresis', () => {
    // For hysteresis: span should be between ENTER (5000) and EXIT (8000) LY thresholds
    // Math: zoom * 640 * 0.78 * 1.25 * 2 = span (approximate)
    // For span=6500 LY: zoom ≈ 6500 / (640 * 0.78 * 1.25 * 2) ≈ 6.4
    const boundaryCamera = { center: { x: 0, z: 0 }, zoom: 6.4, pitchDeg: 0.5 };
    const span = realStarViewportSpan(boundaryCamera, viewport);

    console.log(`[hysteresis test] zoom=6.4 produces span=${span.maxSpan.toFixed(0)} LY`);

    // When disabled, enter threshold is 5000 LY
    const shouldEnterFromDisabled = shouldEnableRealStarDetail(boundaryCamera, viewport, false);

    // When enabled, exit threshold is 8000 LY (higher)
    const shouldExitFromEnabled = shouldEnableRealStarDetail(boundaryCamera, viewport, true);

    // At boundary, should not toggle (prevents flicker)
    // span should be > 5000 (don't enter from off) but <= 8000 (can stay enabled)
    expect(shouldEnterFromDisabled).toBe(false);
    expect(shouldExitFromEnabled).toBe(true);
  });

  it('settle timer is tested via runtime contract tests', () => {
    // The actual settle timer behavior is tested in viewportSystems.runtime.test.tsx
    // which uses React hooks properly. This test just documents that.
    expect(true).toBe(true);
  });

  it('should detect when viewport span exceeds exit threshold', () => {
    // At high zoom-out level, span should exceed 150k threshold
    // Use normal viewport with very high zoom (zoomed way out)
    const camera = { center: { x: 0, z: 0 }, zoom: 200, pitchDeg: 0.5 };
    const span = realStarViewportSpan(camera, viewport);

    console.log(`[wide viewport test] zoom=200 produces span=${span.maxSpan.toFixed(0)} LY`);

    const shouldEnable = shouldEnableRealStarDetail(camera, viewport, true);
    const box = realStarViewportBox(camera, viewport);

    // When zoomed out this far, span > 150k, so detail should be disabled
    expect(shouldEnable).toBe(false);
    expect(box).toBeNull();
  });
});
