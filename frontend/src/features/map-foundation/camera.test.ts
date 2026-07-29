import { describe, expect, it } from 'vitest';
import {
  clampCameraCenter,
  DEFAULT_CAMERA_PITCH_DEG,
  easeInOutSine,
  interpolateZoomLog,
  MAX_ZOOM_LY_PER_PIXEL,
  MIN_CAMERA_PITCH_DEG,
  MIN_ZOOM_LY_PER_PIXEL,
  snapCameraTopDown,
  zoomCamera,
  zoomLevelForDelta,
} from './camera';

const bounds = { minX: -49_000, maxX: 49_000, minZ: -22_000, maxZ: 74_000 };

describe('unified map camera', () => {
  it('starts at a moderate Elite-style tilt and snaps overhead without moving context', () => {
    const camera = {
      center: { x: 4_000, z: 18_000 },
      zoom: 24,
      pitchDeg: DEFAULT_CAMERA_PITCH_DEG,
      bearingDeg: 0,
    };

    expect(DEFAULT_CAMERA_PITCH_DEG).toBe(42);
    expect(snapCameraTopDown(camera)).toEqual({
      ...camera,
      pitchDeg: MIN_CAMERA_PITCH_DEG,
    });
  });

  it('pins a whole-galaxy view to the real extent and bounds closer pans with margin', () => {
    expect(clampCameraCenter(
      { x: 500_000, z: -500_000 },
      150,
      { width: 1280, height: 720 },
      bounds,
    )).toEqual({ x: 0, z: 26_000 });

    const closer = clampCameraCenter(
      { x: 500_000, z: -500_000 },
      10,
      { width: 1000, height: 500 },
      bounds,
    );
    expect(closer.x).toBeLessThanOrEqual(47_920);
    expect(closer.z).toBeGreaterThanOrEqual(-24_500);
  });

  it('zooms continuously without changing pitch and clamps both zoom and pan extent', () => {
    const camera = {
      center: { x: 500_000, z: -500_000 },
      zoom: 24,
      pitchDeg: DEFAULT_CAMERA_PITCH_DEG,
      bearingDeg: 0,
    };

    const closer = zoomCamera(camera, -120, { width: 1280, height: 720 }, bounds);
    expect(closer.zoom).toBeLessThan(camera.zoom);
    expect(closer.pitchDeg).toBe(DEFAULT_CAMERA_PITCH_DEG);
    expect(closer.center.x).toBeLessThan(bounds.maxX);
    expect(closer.center.z).toBeGreaterThan(bounds.minZ);

    expect(zoomCamera(camera, -1_000_000, { width: 1, height: 1 }).zoom)
      .toBe(MIN_ZOOM_LY_PER_PIXEL);
    expect(zoomCamera(camera, 1_000_000, { width: 1, height: 1 }).zoom)
      .toBe(MAX_ZOOM_LY_PER_PIXEL);
  });

  it('uses symmetric sine easing and logarithmic scale interpolation', () => {
    expect(easeInOutSine(0)).toBe(0);
    expect(easeInOutSine(0.5)).toBeCloseTo(0.5);
    expect(easeInOutSine(1)).toBe(1);
    expect(easeInOutSine(0.25)).toBeCloseTo(1 - easeInOutSine(0.75));

    expect(interpolateZoomLog(100, 25, 0)).toBeCloseTo(100);
    expect(interpolateZoomLog(100, 25, 0.5)).toBeCloseTo(50);
    expect(interpolateZoomLog(100, 25, 1)).toBeCloseTo(25);
    expect(zoomLevelForDelta(100, -220)).toBeCloseTo(100 * Math.exp(-0.22));
  });
});
