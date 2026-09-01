import { describe, expect, it } from 'vitest';
import { clampCamera, freshFallbackCanvas, recoveryOutcome } from './BabylonMapRuntime';

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
});
