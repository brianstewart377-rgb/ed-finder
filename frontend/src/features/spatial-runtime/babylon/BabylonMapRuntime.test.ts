import { describe, expect, it } from 'vitest';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import { clampCamera, freshFallbackCanvas, galaxyPlanePointFromRay, recoveryOutcome, sourceStreamTruncated, thinInstanceBufferBytes } from './BabylonMapRuntime';
import { createSpatialFixture } from '../fixtures';
import { normalizeScene, selectGpuSceneBuffers } from '../scene-data';

describe('BabylonMapRuntime helpers', () => {
  it('uses a fresh DOM canvas for WebGL2 fallback without losing canvas attributes', () => {
    const host = document.createElement('div');
    const bound = document.createElement('canvas');
    bound.width = 123; bound.height = 45; bound.className = 'map-canvas';
    host.append(bound);

    const fallback = freshFallbackCanvas(bound);

    expect(fallback).not.toBe(bound);
    expect(host.firstChild).toBe(fallback);
    expect(fallback.width).toBe(123);
    expect(fallback.height).toBe(45);
    expect(fallback.className).toBe('map-canvas');
  });

  it('classifies a backend-changing rebuild as fallback', () => {
    expect(recoveryOutcome('WEBGPU', 'WEBGL2')).toBe('FALLBACK');
    expect(recoveryOutcome('WEBGL2', 'WEBGL2')).toBe('RECOVERED');
  });

  it('clamps semantic camera limits without changing projection', () => {
    expect(clampCamera({ focusLy: { x: 1, y: 2, z: 3 }, distanceLy: 0, bearingRad: 1, pitchRad: 99, projection: 'perspective', revision: 2 }))
      .toMatchObject({ distanceLy: 1, pitchRad: Math.PI / 2, projection: 'perspective' });
  });

  it('keeps client LOD culling separate from source truncation telemetry', () => {
    const scene = createSpatialFixture(40_000);
    expect(selectGpuSceneBuffers(scene, normalizeScene(scene)).truncated).toBe(true);
    expect(sourceStreamTruncated(scene)).toBe(false);

    const truncatedScene = {
      ...scene,
      contributions: scene.contributions.map((contribution) => ({
        ...contribution,
        layers: contribution.layers.map((layer) => ({ ...layer, truncated: true })),
      })),
    };
    expect(sourceStreamTruncated(truncatedScene)).toBe(true);
  });

  it('measures the uploaded Float32 thin-instance matrix and color payload', () => {
    expect(thinInstanceBufferBytes(0)).toBe(0);
    expect(thinInstanceBufferBytes(3)).toBe(3 * (16 + 4) * Float32Array.BYTES_PER_ELEMENT);
  });

  it('queries the galaxy plane at an off-centre camera ray instead of camera focus', () => {
    const originLy = { x: 10_000, y: 200, z: -5_000 };
    const centre = galaxyPlanePointFromRay(
      { origin: new Vector3(0, 100, 0), direction: new Vector3(0, -1, 0) },
      originLy,
    );
    const offCentre = galaxyPlanePointFromRay(
      { origin: new Vector3(0, 100, 0), direction: new Vector3(0.25, -1, -0.5) },
      originLy,
    );

    expect(centre).toEqual({ x: 10_000, z: -5_000 });
    expect(offCentre).toEqual({ x: 10_025, z: -5_050 });
    expect(offCentre).not.toEqual(centre);
  });
});
