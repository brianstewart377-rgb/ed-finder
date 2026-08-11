import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import type { MapViewportSystem } from '@/lib/api';
import { spectralStarColor } from '@/lib/starColor';
import { realStarViewportBox, buildRealStarBuffers } from './viewportSystems';

describe('realStarViewportBox', () => {
  it('returns null when zoomed out (view too wide -> stay on heatmap)', () => {
    const box = realStarViewportBox({ center: { x: 0, z: 0 }, zoom: 100 }, { width: 1000, height: 800 });
    expect(box).toBeNull();
  });

  it('returns a grid-rounded, margined, camera-centered box when zoomed in', () => {
    const box = realStarViewportBox({ center: { x: 1000, z: 2000 }, zoom: 2 }, { width: 1000, height: 800 });
    expect(box).not.toBeNull();
    // Fetched box stays under the server's 15k too_wide guard.
    expect(box!.max_x - box!.min_x).toBeLessThanOrEqual(14_500);
    expect(box!.max_z - box!.min_z).toBeLessThanOrEqual(14_500);
    // Rounded to the 250 LY grid.
    expect(box!.min_x % 250).toBe(0);
    expect(box!.max_z % 250).toBe(0);
    // Fixed vertical (depth) range.
    expect(box!.min_y).toBe(-6000);
    expect(box!.max_y).toBe(6000);
    // Centered on the camera.
    expect((box!.min_x + box!.max_x) / 2).toBeCloseTo(1000, -2);
    expect((box!.min_z + box!.max_z) / 2).toBeCloseTo(2000, -2);
  });
});

describe('buildRealStarBuffers', () => {
  it('maps galaxy coords to three space (x, z, y) and colors by spectral class', () => {
    const systems: MapViewportSystem[] = [
      { id64: 1, name: 'A', x: 10, y: 20, z: 30, star: 'M', populated: false },
      { id64: 2, name: 'B', x: -5, y: 0, z: 7, star: 'O', populated: true },
    ];
    const { positions, colors } = buildRealStarBuffers(systems);
    expect(Array.from(positions.slice(0, 3))).toEqual([10, 30, 20]);
    expect(Array.from(positions.slice(3, 6))).toEqual([-5, 7, 0]);
    const m = new THREE.Color(spectralStarColor('M'));
    expect(colors[0]).toBeCloseTo(m.r, 5);
    expect(colors[1]).toBeCloseTo(m.g, 5);
    expect(colors[2]).toBeCloseTo(m.b, 5);
  });
});
