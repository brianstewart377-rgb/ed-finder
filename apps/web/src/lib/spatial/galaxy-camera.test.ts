import { describe, expect, it } from 'vitest';

import type { CameraState } from './contracts';
import {
  fitGalaxyCamera,
  fitGalaxyPlaneCamera,
  focusGalaxyCamera,
  GALAXY_CAMERA_FOV_RAD,
  GALAXY_CAMERA_MAX_DISTANCE_LY,
  GALAXY_CAMERA_MAX_PITCH_RAD,
  GALAXY_CAMERA_MIN_DISTANCE_LY,
  GALAXY_CAMERA_MIN_PITCH_RAD,
  galaxyCameraPose,
  interpolateGalaxyCamera,
  normalizeGalaxyCamera,
  orbitGalaxyCamera,
  panGalaxyCamera,
  topDownGalaxyCamera,
  zoomGalaxyCamera,
} from './galaxy-camera';

const camera: CameraState = {
  focusLy: { x: 123.5, y: -45.25, z: 678.125 },
  distanceLy: 1_000,
  bearingRad: 0,
  pitchRad: Math.PI / 4,
  projection: 'perspective',
  revision: 4,
};
const viewport = { width: 1_280, height: 720 };

describe('renderer-neutral Galaxy camera', () => {
  it('clamps navigation values without scaling or rounding factual coordinates', () => {
    expect(
      normalizeGalaxyCamera({
        ...camera,
        distanceLy: -1,
        pitchRad: -1,
        bearingRad: 3 * Math.PI,
      }),
    ).toEqual({
      ...camera,
      distanceLy: GALAXY_CAMERA_MIN_DISTANCE_LY,
      pitchRad: GALAXY_CAMERA_MIN_PITCH_RAD,
      bearingRad: -Math.PI,
    });
    expect(
      normalizeGalaxyCamera({ ...camera, distanceLy: 1e10, pitchRad: 4 }),
    ).toMatchObject({
      distanceLy: GALAXY_CAMERA_MAX_DISTANCE_LY,
      pitchRad: GALAXY_CAMERA_MAX_PITCH_RAD,
    });
  });

  it.each([
    { distanceLy: NaN },
    { pitchRad: Infinity },
    { bearingRad: -Infinity },
    { focusLy: { x: 0, y: NaN, z: 0 } },
    { revision: -1 },
    { revision: 0.5 },
    { projection: 'invented' },
  ])('rejects invalid state %o before it reaches the renderer', (invalid) => {
    expect(() =>
      normalizeGalaxyCamera({ ...camera, ...invalid } as CameraState),
    ).toThrow(RangeError);
  });

  it('maintains true spherical distance and an orthogonal up basis at every bearing', () => {
    for (const bearingRad of [0, Math.PI / 2, Math.PI, -Math.PI / 2]) {
      for (const pitchRad of [
        GALAXY_CAMERA_MIN_PITCH_RAD,
        Math.PI / 4,
        Math.PI / 2,
      ]) {
        const pose = galaxyCameraPose({ ...camera, bearingRad, pitchRad });
        const offset = {
          x: pose.positionLy.x - pose.targetLy.x,
          y: pose.positionLy.y - pose.targetLy.y,
          z: pose.positionLy.z - pose.targetLy.z,
        };
        expect(Math.hypot(offset.x, offset.y, offset.z)).toBeCloseTo(
          camera.distanceLy,
        );
        expect(Math.hypot(pose.up.x, pose.up.y, pose.up.z)).toBeCloseTo(1);
        expect(
          offset.x * pose.up.x + offset.y * pose.up.y + offset.z * pose.up.z,
        ).toBeCloseTo(0);
      }
    }
    const front = galaxyCameraPose(camera);
    expect(front.positionLy.z).toBeLessThan(camera.focusLy.z);
    expect(front.positionLy.x).toBe(camera.focusLy.x);
    const side = galaxyCameraPose({ ...camera, bearingRad: Math.PI / 2 });
    expect(side.positionLy.x).toBeGreaterThan(camera.focusLy.x);
    expect(side.positionLy.z).toBeCloseTo(camera.focusLy.z);
  });

  it('uses exact top-down coordinates and preserves bearing through the pole', () => {
    const topDown = topDownGalaxyCamera({ ...camera, bearingRad: Math.PI / 2 });
    const pose = galaxyCameraPose(topDown);
    expect(topDown.bearingRad).toBeCloseTo(Math.PI / 2);
    expect(topDown.revision).toBe(camera.revision + 1);
    expect(pose.positionLy).toEqual({
      x: camera.focusLy.x,
      y: camera.focusLy.y + camera.distanceLy,
      z: camera.focusLy.z,
    });
    expect(pose.up.x).toBeCloseTo(-1);
    expect(pose.up.y).toBe(0);
    expect(pose.up.z).toBeCloseTo(0);
  });

  it('maps pan to the actual screen axes as bearing rotates and preserves focus height', () => {
    const topDown = { ...camera, pitchRad: Math.PI / 2 };
    const span = 2 * camera.distanceLy * Math.tan(GALAXY_CAMERA_FOV_RAD / 2);
    const right = panGalaxyCamera(topDown, viewport.height, 0, viewport);
    expect(right.focusLy.x - camera.focusLy.x).toBeCloseTo(span);
    expect(right.focusLy.y).toBe(camera.focusLy.y);
    expect(right.focusLy.z).toBeCloseTo(camera.focusLy.z);
    const down = panGalaxyCamera(topDown, 0, viewport.height, viewport);
    expect(down.focusLy.z - camera.focusLy.z).toBeCloseTo(-span);
    const rotatedRight = panGalaxyCamera(
      { ...topDown, bearingRad: Math.PI / 2 },
      viewport.height,
      0,
      viewport,
    );
    expect(rotatedRight.focusLy.x).toBeCloseTo(camera.focusLy.x);
    expect(rotatedRight.focusLy.z - camera.focusLy.z).toBeCloseTo(span);
    const rotatedDown = panGalaxyCamera(
      { ...topDown, bearingRad: Math.PI / 2 },
      0,
      viewport.height,
      viewport,
    );
    expect(rotatedDown.focusLy.x - camera.focusLy.x).toBeCloseTo(span);
    const tiltedDown = panGalaxyCamera(camera, 0, viewport.height, viewport);
    expect(tiltedDown.focusLy.z - camera.focusLy.z).toBeCloseTo(
      -span / Math.sin(camera.pitchRad),
    );
  });

  it('zooms exponentially with reciprocal steps, a fixed focus, and extreme-input bounds', () => {
    const out = zoomGalaxyCamera(camera, 250);
    const back = zoomGalaxyCamera(out, -250);
    expect(out.distanceLy / camera.distanceLy).toBeCloseTo(Math.exp(0.25));
    expect(back.distanceLy).toBeCloseTo(camera.distanceLy);
    expect(back.focusLy).toEqual(camera.focusLy);
    expect(back.revision).toBe(camera.revision + 2);
    expect(zoomGalaxyCamera(camera, Number.MAX_VALUE).distanceLy).toBeCloseTo(
      GALAXY_CAMERA_MAX_DISTANCE_LY,
    );
    expect(zoomGalaxyCamera(camera, -Number.MAX_VALUE).distanceLy).toBe(
      GALAXY_CAMERA_MIN_DISTANCE_LY,
    );
  });

  it('bounds orbital elevation and wraps bearing without changing the target or distance', () => {
    const orbit = orbitGalaxyCamera(camera, 3 * Math.PI, -2 * Math.PI);
    expect(orbit).toMatchObject({
      focusLy: camera.focusLy,
      distanceLy: camera.distanceLy,
      bearingRad: -Math.PI,
      pitchRad: GALAXY_CAMERA_MIN_PITCH_RAD,
      revision: camera.revision + 1,
    });
  });

  it('interpolates the short 20-degree turn across wrap, with geometric distance and exact endpoints', () => {
    const from = {
      ...camera,
      bearingRad: (170 * Math.PI) / 180,
      distanceLy: 100,
    };
    const to = {
      ...camera,
      focusLy: { x: 500, y: 20, z: -90 },
      bearingRad: (-170 * Math.PI) / 180,
      pitchRad: Math.PI / 2,
      distanceLy: 10_000,
      revision: 8,
    };
    expect(interpolateGalaxyCamera(from, to, -1)).toEqual(
      normalizeGalaxyCamera(from),
    );
    expect(interpolateGalaxyCamera(from, to, 2)).toEqual(
      normalizeGalaxyCamera(to),
    );
    const half = interpolateGalaxyCamera(from, to, 0.5);
    expect(Math.abs(half.bearingRad)).toBeCloseTo(Math.PI);
    expect(half.distanceLy).toBeCloseTo(1_000);
    expect(half.focusLy.x).toBeCloseTo((from.focusLy.x + to.focusLy.x) / 2);
    expect(half.focusLy.y).toBeCloseTo((from.focusLy.y + to.focusLy.y) / 2);
    expect(half.focusLy.z).toBeCloseTo((from.focusLy.z + to.focusLy.z) / 2);
    expect(half.revision).toBe(to.revision);
    expect(interpolateGalaxyCamera(to, from, 0.25).bearingRad).toBeLessThan(
      to.bearingRad,
    );
  });

  it('focuses exactly and fits enclosing geometry for both portrait and landscape views', () => {
    const bounds = {
      min: { x: -10, y: -20, z: -30 },
      max: { x: 30, y: 40, z: 50 },
    };
    const focused = focusGalaxyCamera(camera, bounds.max, 5_000);
    expect(focused).toEqual({
      ...camera,
      focusLy: bounds.max,
      distanceLy: 5_000,
      revision: camera.revision + 1,
    });
    const fit = fitGalaxyCamera(camera, bounds, viewport, 1);
    const portrait = fitGalaxyCamera(
      camera,
      bounds,
      { width: 300, height: 900 },
      1,
    );
    expect(fit.focusLy).toEqual({ x: 10, y: 10, z: 10 });
    expect(fit.distanceLy).toBeCloseTo(
      Math.hypot(20, 30, 40) / Math.sin(GALAXY_CAMERA_FOV_RAD / 2),
    );
    expect(portrait.distanceLy).toBeGreaterThan(fit.distanceLy);
    const orthographic = fitGalaxyCamera(
      { ...camera, projection: 'orthographic' },
      bounds,
      viewport,
      1,
    );
    expect(orthographic.distanceLy).toBeCloseTo(
      Math.hypot(20, 30, 40) / Math.tan(GALAXY_CAMERA_FOV_RAD / 2),
    );
  });

  it('fits a top-down planar source without enclosing empty depth', () => {
    const bounds = {
      min: { x: -50_000, y: 0, z: -50_000 },
      max: { x: 50_000, y: 0, z: 50_000 },
    };
    const planar = fitGalaxyPlaneCamera(
      camera,
      bounds,
      { width: 1_200, height: 600 },
      1.1,
    );
    expect(planar.pitchRad).toBe(Math.PI / 2);
    expect(planar.focusLy).toEqual({ x: 0, y: 0, z: 0 });
    expect(planar.distanceLy).toBeCloseTo(
      (50_000 / Math.tan(GALAXY_CAMERA_FOV_RAD / 2)) * 1.1,
    );
    expect(planar.distanceLy).toBeLessThan(
      fitGalaxyCamera(camera, bounds, { width: 1_200, height: 600 }).distanceLy,
    );
  });

  it('rejects invalid gesture, transition, and fit inputs without mutating prior camera state', () => {
    expect(() =>
      panGalaxyCamera(camera, 0, 1, { width: 0, height: 720 }),
    ).toThrow(RangeError);
    expect(() => panGalaxyCamera(camera, NaN, 0, viewport)).toThrow(RangeError);
    expect(() => zoomGalaxyCamera(camera, Infinity)).toThrow(RangeError);
    expect(() => orbitGalaxyCamera(camera, Infinity, 0)).toThrow(RangeError);
    expect(() => interpolateGalaxyCamera(camera, camera, NaN)).toThrow(
      RangeError,
    );
    expect(() =>
      fitGalaxyCamera(
        camera,
        {
          min: { x: 1, y: 0, z: 0 },
          max: { x: 0, y: 0, z: 0 },
        },
        viewport,
      ),
    ).toThrow(RangeError);
    expect(camera.revision).toBe(4);
    expect(camera.focusLy).toEqual({ x: 123.5, y: -45.25, z: 678.125 });
  });
});
