import { describe, it, expect } from 'vitest';
import { galaxyDensity } from '../galaxyDensity';

describe('galaxyDensity (Boxel Octree + Milky Way Luminosity)', () => {
  it('returns high density at galactic center', () => {
    const centerDensity = galaxyDensity.computeDensity({ x: 0, y: 0, z: 0 });
    expect(centerDensity).toBeGreaterThan(0.7);
  });

  it('returns lower density in outer regions', () => {
    const outerDensity = galaxyDensity.computeDensity({ x: 40000, y: 0, z: 0 });
    expect(outerDensity).toBeLessThan(0.25);
  });

  it('returns high density in spiral arms', () => {
    // Approximate spiral arm location
    const armDensity = galaxyDensity.computeDensity({ x: 10000, y: 0, z: 10000 });
    expect(armDensity).toBeGreaterThan(0.35);
  });

  it('returns lower density between spiral arms', () => {
    // Gap between arms
    const betweenDensity = galaxyDensity.computeDensity({ x: 5000, y: 0, z: -5000 });
    expect(betweenDensity).toBeLessThan(0.35);
  });

  it('attenuates density above/below galactic plane', () => {
    const planeDensity = galaxyDensity.computeDensity({ x: 5000, y: 0, z: 5000 });
    const highDensity = galaxyDensity.computeDensity({ x: 5000, y: 5000, z: 5000 });
    expect(planeDensity).toBeGreaterThan(highDensity);
  });

  it('assigns boxel layers correctly (core region: small boxels)', () => {
    const coreLayer = galaxyDensity.getBoxelLayer({ x: 0, y: 0, z: 0 });
    expect(coreLayer).toBeGreaterThanOrEqual(4); // Layers 4-7 (small boxels)
  });

  it('assigns boxel layers correctly (disk region: mixed boxels)', () => {
    const diskLayer = galaxyDensity.getBoxelLayer({ x: 15000, y: 0, z: 0 });
    expect(diskLayer).toBeGreaterThanOrEqual(1);
    expect(diskLayer).toBeLessThanOrEqual(6);
  });

  it('assigns boxel layers correctly (outer region: large boxels)', () => {
    const outerLayer = galaxyDensity.getBoxelLayer({ x: 40000, y: 0, z: 0 });
    expect(outerLayer).toBeLessThanOrEqual(3); // Layers 0-3 (large boxels)
  });

  it('applies LOD culling at high zoom distances', () => {
    const densityNoZoom = galaxyDensity.computeDensity({ x: 1000, y: 0, z: 1000 });
    const densityHighZoom = galaxyDensity.computeDensity({ x: 1000, y: 0, z: 1000 }, 10000);
    // High zoom distance suppresses small-boxel detail
    expect(densityHighZoom).toBeLessThanOrEqual(densityNoZoom);
  });

  it('Milky Way luminosity peaks near core', () => {
    const coreLuminosity = galaxyDensity.getMilkyWayLuminosity(0, 0);
    const diskLuminosity = galaxyDensity.getMilkyWayLuminosity(15000, 0);
    expect(coreLuminosity).toBeGreaterThan(diskLuminosity);
  });

  it('returns 0 luminosity beyond the galaxy radius', () => {
    // Far outside the 50,000 LY galactic radius bound
    const beyondRadius = galaxyDensity.getMilkyWayLuminosity(100000, 100000);
    expect(beyondRadius).toBe(0);
  });
});
