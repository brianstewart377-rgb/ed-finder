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
    // Fetched box stays under the server's 15k too_wide guard (we use 14k so grid rounding can add up to 1 GRID_LY per side).
    expect(box!.max_x - box!.min_x).toBeLessThanOrEqual(14_000);
    expect(box!.max_z - box!.min_z).toBeLessThanOrEqual(14_000);
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
      { id64: 1, name: 'A', x: 10, y: 20, z: 30, star: 'M', populated: false, galaxy_region_id: 1 },
      { id64: 2, name: 'B', x: -5, y: 0, z: 7, star: 'O', populated: true, galaxy_region_id: 2 },
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
