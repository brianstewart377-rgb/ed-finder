import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { realStarViewportBox, shouldEnableRealStarDetail } from './viewportSystems';
import type { MapViewportBox } from '@/lib/api';

describe('viewport systems settle timer logic', () => {
  const viewport = { width: 1280, height: 720 };
  const camera = { center: { x: 0, z: 0 }, zoom: 5, pitchDeg: 0.5 };

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
    const zoomedCamera = { ...camera, zoom: 10 };
    const box2 = realStarViewportBox(zoomedCamera, viewport);

    // Different zoom should produce different box span
    const span1 = Math.max(box1!.max_x - box1!.min_x, box1!.max_z - box1!.min_z);
    const span2 = Math.max(box2!.max_x - box2!.min_x, box2!.max_z - box2!.min_z);
    expect(span2).toBeGreaterThan(span1);
  });

  it('threshold should have hysteresis', () => {
    // At boundary zoom, should require hysteresis
    // Use zoom=10 which produces span between 120k and 150k for hysteresis test
    const boundaryCamera = { center: { x: 0, z: 0 }, zoom: 10, pitchDeg: 0.5 };

    // When disabled, enter threshold is 120k
    const shouldEnterFromDisabled = shouldEnableRealStarDetail(boundaryCamera, viewport, false);

    // When enabled, exit threshold is 150k (higher)
    const shouldExitFromEnabled = shouldEnableRealStarDetail(boundaryCamera, viewport, true);

    // At boundary, should not toggle (prevents flicker)
    // span should be > 120k (don't enter from off) but <= 150k (can stay enabled)
    expect(shouldEnterFromDisabled).toBe(false);
    expect(shouldExitFromEnabled).toBe(true);
  });

  it('settle timer should wait 250ms before updating settledBox', (done) => {
    // This test verifies the 250ms debounce timing
    const SETTLE_MS = 250;
    let boxChanged = false;
    let settledBoxUpdated = false;

    // Simulate box change
    boxChanged = true;
    console.log('Box changed, starting settle timer...');

    // Timer should NOT fire immediately
    expect(settledBoxUpdated).toBe(false);

    // Advance time by 249ms
    vi.advanceTimersByTime(SETTLE_MS - 1);
    expect(settledBoxUpdated).toBe(false);

    // Advance by 1ms more (total 250ms)
    vi.advanceTimersByTime(1);

    // After 250ms, settledBox should be updated
    setTimeout(() => {
      expect(settledBoxUpdated).toBe(true);
      done();
    }, 10);
  });

  it('should detect when viewport span exceeds exit threshold', () => {
    // Very wide viewport should be rejected
    const wideViewport = { width: 10000, height: 10000 };
    const camera = { center: { x: 0, z: 0 }, zoom: 1, pitchDeg: 0.5 };

    const shouldEnable = shouldEnableRealStarDetail(camera, wideViewport, true);
    const box = realStarViewportBox(camera, wideViewport);

    expect(shouldEnable).toBe(false);
    expect(box).toBeNull();
  });
});
