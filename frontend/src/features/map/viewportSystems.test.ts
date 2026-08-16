import { describe, it, expect } from 'vitest';
import { shouldEnableRealStarDetail, realStarViewportBox } from './viewportSystems';

describe('viewportSystems', () => {
  describe('shouldEnableRealStarDetail', () => {
    it('should enable real-star detail when zoomed in below enter threshold', () => {
      const camera = {
        center: { x: 0, z: 0 },
        zoom: 5, // Zoomed in enough (thresholds are 120k/150k LY)
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };
      const wasEnabled = false;

      const result = shouldEnableRealStarDetail(camera, viewport, wasEnabled);
      expect(result).toBe(true);
    });

    it('should NOT enable when zoomed out beyond enter threshold', () => {
      const camera = {
        center: { x: 0, z: 0 },
        zoom: 1000, // Very zoomed out (span >> 150k LY)
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };
      const wasEnabled = false;

      const result = shouldEnableRealStarDetail(camera, viewport, wasEnabled);
      expect(result).toBe(false);
    });

    it('should use exit threshold when already enabled (hysteresis)', () => {
      const camera = {
        center: { x: 0, z: 0 },
        zoom: 1, // Zoomed in enough to trigger real-stars
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };

      // When zoomed in, both enabled and disabled should return true
      const resultDisabled = shouldEnableRealStarDetail(camera, viewport, false);
      expect(resultDisabled).toBe(true);

      const resultEnabled = shouldEnableRealStarDetail(camera, viewport, true);
      expect(resultEnabled).toBe(true);
    });
  });

  describe('realStarViewportBox', () => {
    it('should return a box when zoomed in enough', () => {
      const camera = {
        center: { x: 1000, z: 2000 },
        zoom: 0.5,
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };

      const box = realStarViewportBox(camera, viewport);
      expect(box).not.toBeNull();
      expect(box!.min_x).toBeLessThan(box!.max_x);
      expect(box!.min_z).toBeLessThan(box!.max_z);
      expect(Math.abs(box!.min_y)).toBeLessThanOrEqual(6000);
      expect(Math.abs(box!.max_y)).toBeLessThanOrEqual(6000);
    });

    it('should return null when zoomed out too far', () => {
      const camera = {
        center: { x: 0, z: 0 },
        zoom: 200,
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };

      const box = realStarViewportBox(camera, viewport);
      expect(box).toBeNull();
    });

    it('should include camera center in the box', () => {
      const camera = {
        center: { x: 5000, z: 10000 },
        zoom: 1,
        pitchDeg: 0.5,
      };
      const viewport = {
        width: 1000,
        height: 800,
      };

      const box = realStarViewportBox(camera, viewport);
      expect(box).not.toBeNull();
      expect(box!.min_x).toBeLessThanOrEqual(5000);
      expect(box!.max_x).toBeGreaterThanOrEqual(5000);
      expect(box!.min_z).toBeLessThanOrEqual(10000);
      expect(box!.max_z).toBeGreaterThanOrEqual(10000);
    });
  });
});
