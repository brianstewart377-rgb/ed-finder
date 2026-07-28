import { describe, expect, it } from 'vitest';
import {
  buildBoundaryPolylines,
  declutterRegionLabels,
  regionLabelScale,
  safariGestureZoomDelta,
} from './map-presentation';

describe('map presentation polish', () => {
  it('joins degree-two boundary segments into solid Line2 paths without crossing junctions', () => {
    const paths = buildBoundaryPolylines([
      { source: [0, 0, 0], target: [1, 0, 0] },
      { source: [1, 0, 0], target: [2, 0, 0] },
      { source: [2, 0, 0], target: [3, 0, 0] },
      { source: [2, 0, 0], target: [2, 1, 0] },
    ]);

    expect(paths).toHaveLength(3);
    expect(paths.some((path) => path.length === 9)).toBe(true);
    expect(paths.reduce((segments, path) => segments + path.length / 3 - 1, 0)).toBe(4);
  });

  it('keeps complete labels inside the viewport and declutters in screen space', () => {
    const labels = declutterRegionLabels([
      { id: 1, name: 'Galactic Centre', position: [0, 0, 0], screen: { x: 500, z: 300 }, depthVisible: true },
      { id: 2, name: 'Near centre', position: [0, 0, 0], screen: { x: 510, z: 304 }, depthVisible: true },
      { id: 3, name: 'Outer Arm', position: [0, 0, 0], screen: { x: 760, z: 420 }, depthVisible: true },
      { id: 4, name: 'Clipped edge', position: [0, 0, 0], screen: { x: 20, z: 300 }, depthVisible: true },
    ], { width: 1_000, height: 600 }, 150);

    expect(labels.find((label) => label.id === 1)?.visible).toBe(true);
    expect(labels.find((label) => label.id === 2)?.visible).toBe(false);
    expect(labels.find((label) => label.id === 3)?.visible).toBe(true);
    expect(labels.find((label) => label.id === 4)?.visible).toBe(false);
  });

  it('grows ambient labels on close zoom and maps Safari pinch scale to zoom direction', () => {
    expect(regionLabelScale(25)).toBeGreaterThan(regionLabelScale(150));
    expect(regionLabelScale(0.001)).toBeLessThanOrEqual(2.35);
    expect(safariGestureZoomDelta(1, 1.5)).toBeLessThan(0);
    expect(safariGestureZoomDelta(1, 0.5)).toBeGreaterThan(0);
  });
});
