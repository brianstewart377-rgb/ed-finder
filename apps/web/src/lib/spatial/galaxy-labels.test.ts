import { describe, expect, it } from 'vitest';

import type { CameraState } from './contracts';
import {
  layoutGalaxyLabels,
  projectGalaxyLabel,
  type GalaxyLabelCandidate,
} from './galaxy-labels';

const camera: CameraState = {
  focusLy: { x: 0, y: 0, z: 0 },
  distanceLy: 1_000,
  bearingRad: 0,
  pitchRad: Math.PI / 2,
  projection: 'perspective',
  revision: 1,
};
const viewport = { width: 1_000, height: 500 };

function label(
  key: string,
  x: number,
  z: number,
  overrides: Partial<GalaxyLabelCandidate> = {},
): GalaxyLabelCandidate {
  return {
    key,
    kind: 'system',
    text: key,
    positionLy: { x, y: 0, z },
    target: { kind: 'system', systemId64: key },
    selected: false,
    hovered: false,
    current: false,
    ...overrides,
  };
}

describe('Galaxy label projection and layout', () => {
  it('projects the camera focus to the exact viewport centre', () => {
    expect(projectGalaxyLabel(camera.focusLy, camera, viewport)).toMatchObject({
      xPx: 500,
      yPx: 250,
      depthLy: 1_000,
    });
  });

  it('matches bearing-aware screen-right projection', () => {
    const right = projectGalaxyLabel({ x: 100, y: 0, z: 0 }, camera, viewport);
    expect(right?.xPx).toBeGreaterThan(500);
    const rotated = projectGalaxyLabel(
      { x: 0, y: 0, z: 100 },
      { ...camera, bearingRad: Math.PI / 2 },
      viewport,
    );
    expect(rotated?.xPx).toBeGreaterThan(500);
  });

  it('declutters ordinary collisions but displaces selected labels', () => {
    const result = layoutGalaxyLabels(
      [
        label('ordinary-a', 0, 0),
        label('ordinary-b', 2, 0),
        label('selected', 4, 0, { selected: true }),
        label('current-region', 5, 0, {
          kind: 'region',
          target: { kind: 'region', id: '1' },
          current: true,
        }),
      ],
      camera,
      viewport,
    );
    expect(result.map((entry) => entry.key)).toContain('selected');
    expect(result).toHaveLength(2);
    expect(
      new Set(result.map((entry) => `${entry.xPx}:${entry.yPx}`)).size,
    ).toBe(2);
  });

  it('uses the system distance gate and explicit system budget only', () => {
    const candidates = [
      label('system-ordinary', -15_000, 0),
      label('system-selected', 15_000, 0, { selected: true }),
      label('region-a', -25_000, 0, {
        kind: 'region',
        target: { kind: 'region', id: '1' },
      }),
      label('region-b', 25_000, 0, {
        kind: 'region',
        target: { kind: 'region', id: '2' },
      }),
    ];
    const wide = layoutGalaxyLabels(
      candidates,
      { ...camera, distanceLy: 100_000 },
      viewport,
      { maximumSystemLabels: 1 },
    );
    expect(wide.filter((entry) => entry.kind === 'region')).toHaveLength(2);
    expect(
      wide.filter((entry) => entry.kind === 'system').map((entry) => entry.key),
    ).toEqual(['system-selected']);
  });

  it('keeps every in-frame region label inside the configured safe area', () => {
    const labels = layoutGalaxyLabels(
      [
        label('edge', 720, 0, {
          kind: 'region',
          target: { kind: 'region', id: '1' },
        }),
        label('centre', 0, 0, {
          kind: 'region',
          target: { kind: 'region', id: '2' },
        }),
      ],
      camera,
      viewport,
      { safeArea: { left: 80, right: 80, top: 50, bottom: 50 } },
    );
    expect(labels.map((entry) => entry.key)).toEqual(['centre', 'edge']);
    for (const entry of labels) {
      expect(entry.xPx).toBeGreaterThan(80);
      expect(entry.xPx).toBeLessThan(920);
      expect(entry.yPx).toBeGreaterThan(50);
      expect(entry.yPx).toBeLessThan(450);
    }
  });

  it('never suppresses an in-frame region because of collision priority', () => {
    const regions = [
      label('high-priority-region', 0, 0, {
        kind: 'region',
        target: { kind: 'region', id: '1' },
        selected: true,
      }),
      label('ordinary-region-a', 0, 0, {
        kind: 'region',
        target: { kind: 'region', id: '2' },
      }),
      label('ordinary-region-b', 0, 0, {
        kind: 'region',
        target: { kind: 'region', id: '3' },
      }),
    ];

    const result = layoutGalaxyLabels(regions, camera, viewport, {
      safeArea: { left: 100, right: 100, top: 100, bottom: 100 },
    });

    expect(result.map((entry) => entry.key).sort()).toEqual(
      regions.map((entry) => entry.key).sort(),
    );
  });

  it('places all 42 region names in ordered atlas rails at Galaxy scale', () => {
    const regions = Array.from({ length: 42 }, (_, index) =>
      label(
        `region-${index + 1}`,
        (index - 20.5) * 1_800,
        (((index * 13) % 41) - 20) * 1_600,
        {
          kind: 'region',
          text: `Region ${index + 1}`,
          target: { kind: 'region', id: String(index + 1) },
        },
      ),
    );
    const atlas = layoutGalaxyLabels(
      regions,
      { ...camera, distanceLy: 150_000 },
      viewport,
    );
    expect(atlas).toHaveLength(42);
    expect(
      atlas.filter((entry) => entry.placement === 'atlas-left'),
    ).toHaveLength(21);
    expect(
      atlas.filter((entry) => entry.placement === 'atlas-right'),
    ).toHaveLength(21);
    expect(new Set(atlas.map((entry) => entry.text)).size).toBe(42);
    for (const entry of atlas) {
      expect(entry.leaderEndXPx).not.toBe(entry.anchorXPx);
    }
  });
});
