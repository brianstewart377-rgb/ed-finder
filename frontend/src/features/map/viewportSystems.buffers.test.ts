import { describe, expect, it } from 'vitest';
import type { MapViewportSystem } from '@/lib/api';
import { buildRealStarBuffers } from './viewportSystems';

describe('buildRealStarBuffers — geometry and color verification', () => {
  it('produces correct position buffer layout (x, z, y per system)', () => {
    const systems: MapViewportSystem[] = [
      { id64: 1, name: 'Sol', x: 100, y: 0, z: 50, main_star_class: 'G', populated: true },
      { id64: 2, name: 'Sirius', x: 200, y: 10, z: 60, main_star_class: 'A', populated: false },
    ];

    const { positions } = buildRealStarBuffers(systems);

    expect(positions.length).toBe(6); // 2 systems × 3 coords
    // First system: x=100, z→y=50, y→z=0 (Three.js axes: x, z, y)
    expect(positions[0]).toBe(100);
    expect(positions[1]).toBe(50);
    expect(positions[2]).toBe(0);
    // Second system
    expect(positions[3]).toBe(200);
    expect(positions[4]).toBe(60);
    expect(positions[5]).toBe(10);
  });

  it('produces correct color buffer layout (RGB per system)', () => {
    const systems: MapViewportSystem[] = [
      { id64: 1, name: 'Test', x: 0, y: 0, z: 0, main_star_class: 'O', populated: false },
      { id64: 2, name: 'Test', x: 0, y: 0, z: 0, main_star_class: 'M', populated: false },
    ];

    const { colors } = buildRealStarBuffers(systems);

    expect(colors.length).toBe(6); // 2 systems × 3 color components
    // Verify color values are normalized 0-1 (not 0-255)
    for (let i = 0; i < colors.length; i++) {
      expect(colors[i]).toBeGreaterThanOrEqual(0);
      expect(colors[i]).toBeLessThanOrEqual(1);
    }
  });

  it('maps spectral types to correct hue ranges', () => {
    const testCases: [string, 'hot' | 'warm' | 'cool'][] = [
      ['O', 'cool'],  // Blue
      ['B', 'cool'],  // Blue-white
      ['A', 'cool'],  // White
      ['F', 'warm'],  // Yellow-white
      ['G', 'warm'],  // Yellow (like our Sun)
      ['K', 'warm'],  // Orange
      ['M', 'hot'],   // Red
    ];

    testCases.forEach(([starClass, expectedHue]) => {
      const systems: MapViewportSystem[] = [
        { id64: 1, name: 'Test', x: 0, y: 0, z: 0, main_star_class: starClass as string | null, populated: false },
      ];

      const { colors } = buildRealStarBuffers(systems);
      const [r, g, b] = [colors[0], colors[1], colors[2]];

      switch (expectedHue) {
        case 'cool': // O, B, A: blue dominant or equal
          expect(b).toBeGreaterThanOrEqual(Math.max(r, g) * 0.9);
          break;
        case 'warm': // F, G, K: red/yellow dominant
          expect(r + g).toBeGreaterThan(b * 1.3);
          break;
        case 'hot': // M: red dominant
          expect(r).toBeGreaterThan(g);
          expect(r).toBeGreaterThan(b);
          break;
      }
    });
  });

  it('handles null main_star_class with default color', () => {
    const systems: MapViewportSystem[] = [
      { id64: 1, name: 'Unknown', x: 0, y: 0, z: 0, main_star_class: null, populated: false },
    ];

    const { colors } = buildRealStarBuffers(systems);
    const [r, g, b] = [colors[0], colors[1], colors[2]];

    // Should fall back to a neutral color (not crash or produce invalid values)
    expect(r).toBeGreaterThanOrEqual(0);
    expect(g).toBeGreaterThanOrEqual(0);
    expect(b).toBeGreaterThanOrEqual(0);
    expect(r).toBeLessThanOrEqual(1);
    expect(g).toBeLessThanOrEqual(1);
    expect(b).toBeLessThanOrEqual(1);
  });

  it('produces buffers with correct total length (systems.length × components)', () => {
    const sizes = [1, 10, 100, 1000, 40_000]; // Including max viewport cap

    sizes.forEach((size) => {
      const systems = Array.from({ length: size }, (_, i) => ({
        id64: i,
        name: `System ${i}`,
        x: i * 10,
        y: i,
        z: i * -10,
        main_star_class: 'G' as string | null,
        populated: false,
      }));

      const { positions, colors } = buildRealStarBuffers(systems);

      expect(positions.length).toBe(size * 3); // 3 coords per system
      expect(colors.length).toBe(size * 3);   // 3 color components per system
    });
  });

  it('preserves spectral color consistency across multiple calls', () => {
    const system: MapViewportSystem = {
      id64: 1,
      name: 'Consistent',
      x: 100,
      y: 50,
      z: 200,
      main_star_class: 'F',
      populated: false,
    };

    const results = Array.from({ length: 5 }, () => buildRealStarBuffers([system]));
    const firstColors = results[0].colors;

    results.slice(1).forEach((result) => {
      expect(result.colors[0]).toBe(firstColors[0]); // R
      expect(result.colors[1]).toBe(firstColors[1]); // G
      expect(result.colors[2]).toBe(firstColors[2]); // B
    });
  });

  it('handles empty system array', () => {
    const { positions, colors } = buildRealStarBuffers([]);

    expect(positions.length).toBe(0);
    expect(colors.length).toBe(0);
    expect(positions instanceof Float32Array).toBe(true);
    expect(colors instanceof Float32Array).toBe(true);
  });

  it('color output uses spectralStarColor library as source', () => {
    // Just verify that spectralStarColor is being used (not hardcoded)
    // by checking that different spectral classes produce different colors
    const systems: MapViewportSystem[] = [
      { id64: 1, name: 'Hot Blue', x: 0, y: 0, z: 0, main_star_class: 'O', populated: false },
      { id64: 2, name: 'Cool Red', x: 0, y: 0, z: 0, main_star_class: 'M', populated: false },
    ];

    const { colors: bufferColors } = buildRealStarBuffers(systems);

    // O-class should be predominantly blue
    const [oR, oG, oB] = [bufferColors[0], bufferColors[1], bufferColors[2]];
    // M-class should be predominantly red
    const [mR, mG, mB] = [bufferColors[3], bufferColors[4], bufferColors[5]];

    // O should have high blue, M should have high red
    expect(oB).toBeGreaterThan(oG);
    expect(oB).toBeGreaterThan(oR);
    expect(mR).toBeGreaterThan(mB);
    expect(mR).toBeGreaterThan(mG);
  });

  it('coordinate transform is correct for Three.js world space', () => {
    // ED uses galactic (x, y, z); Three.js uses (x, z, y) for our orientation
    const edSystem: MapViewportSystem = {
      id64: 1,
      name: 'Transform Test',
      x: 1234,
      y: 5678,
      z: 9012,
      main_star_class: 'G',
      populated: false,
    };

    const { positions } = buildRealStarBuffers([edSystem]);

    // ED (x, y, z) → Three.js (x, z, y)
    expect(positions[0]).toBe(1234);  // ED x → Three.js x
    expect(positions[1]).toBe(9012);  // ED z → Three.js y
    expect(positions[2]).toBe(5678);  // ED y → Three.js z
  });
});
