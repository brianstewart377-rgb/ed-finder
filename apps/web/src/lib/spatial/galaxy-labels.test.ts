import { describe, expect, it, vi } from 'vitest';

import type {
  CameraState,
  GalaxySceneContract,
  GalaxySystemPoint,
  SpatialContribution,
} from './contracts';
import {
  galaxyLabelCandidates,
  galaxySystemPointIndex,
  MAXIMUM_SYSTEM_LABEL_CANDIDATES,
  nearbyCatalogueLabelLimit,
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

  it('declutters system collisions while displacing region labels', () => {
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

  it('hovering a region does not change any label placement (emphasis only)', () => {
    const region = (id: string) =>
      ({
        kind: 'region',
        text: `Region ${id}`,
        target: { kind: 'region', id },
      }) as const;
    // Clustered so the greedy solver must displace them — the setup that made
    // hover reorder + reflow neighbours before the fix.
    const candidates = [
      label('r1', 0, 0, region('1')),
      label('r2', 2, 0, region('2')),
      label('r3', -2, 0, region('3')),
      label('r4', 0, 3, region('4')),
    ];
    const place = (list: GalaxyLabelCandidate[]) =>
      Object.fromEntries(
        layoutGalaxyLabels(list, camera, viewport).map((l) => [
          l.key,
          `${l.xPx}:${l.yPx}`,
        ]),
      );
    const base = place(candidates);
    const withHover = place(
      candidates.map((c) => (c.key === 'r3' ? { ...c, hovered: true } : c)),
    );
    expect(withHover).toEqual(base);
  });

  it('keeps all 42 region names map-anchored at Galaxy scale', () => {
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
    expect(atlas.every((entry) => entry.placement === 'map')).toBe(true);
    expect(new Set(atlas.map((entry) => entry.text)).size).toBe(42);
  });
});

function point(systemId64: string, x = 0, z = 0): GalaxySystemPoint {
  return {
    systemId64,
    name: `Star ${systemId64}`,
    positionLy: { x, y: 0, z },
    primaryStar: { type: 'G2', subtype: 'G (White-Yellow) Star' },
  };
}

function contribution(
  owner: 'FINDER' | 'CATALOGUE',
  systems: readonly GalaxySystemPoint[],
  layerId = owner === 'FINDER' ? 'finder-systems' : 'catalogue-systems',
): SpatialContribution {
  return {
    id: owner,
    owner,
    revision: 1,
    layers: [
      {
        id: layerId,
        version: 1,
        representation: 'AUTHORITATIVE',
        targetCount: systems.length,
        truncated: false,
        payload: { systems },
      },
    ],
  };
}

function galaxy(
  catalogue: readonly GalaxySystemPoint[],
  finder: readonly GalaxySystemPoint[] = [],
): GalaxySceneContract {
  return {
    kind: 'galaxy',
    revision: 1,
    camera: { ...camera, distanceLy: 500 },
    selection: [],
    contributions: [
      contribution('CATALOGUE', catalogue),
      contribution('FINDER', finder),
    ],
  };
}

describe('Galaxy system label candidates', () => {
  it('includes both catalogue layer names and keeps the raw point and canonical id64', () => {
    const catalogue = point('catalogue');
    const scene = galaxy([catalogue]);
    for (const layerId of ['catalogue-stars', 'catalogue-systems']) {
      const result = galaxyLabelCandidates({
        ...scene,
        contributions: [contribution('CATALOGUE', [catalogue], layerId)],
      });
      expect(result).toHaveLength(1);
      expect(result[0]).toMatchObject({
        key: 'system:catalogue',
        text: 'Star catalogue',
        source: 'catalogue',
        target: { kind: 'system', systemId64: 'catalogue' },
        point: { primaryStar: { type: 'G2' } },
      });
      expect(result[0].point).toBe(catalogue);
    }
  });

  it('ranks selected > hovered > anchor > Finder > nearest catalogue', () => {
    const scene = {
      ...galaxy(
        [
          point('nearest'),
          point('anchor', 5),
          point('hovered', 10),
          point('selected', 15),
          point('further', 20),
        ],
        [point('finder', 25)],
      ),
      selection: [{ kind: 'system', systemId64: 'selected' }] as const,
    };
    const result = galaxyLabelCandidates(scene, undefined, {
      hoveredSystemId64: 'hovered',
      anchor: point('anchor', 5),
      viewport,
    });
    expect(result.map((candidate) => candidate.key)).toEqual([
      'system:selected',
      'system:hovered',
      'system:anchor',
      'system:finder',
      'system:nearest',
      'system:further',
    ]);
  });

  it('retains a supplied anchor and special catalogue targets above the local band', () => {
    const scene = {
      ...galaxy(
        [point('selected'), point('hovered'), point('ordinary')],
        [point('finder')],
      ),
      camera: { ...camera, distanceLy: 40_000 },
      selection: [{ kind: 'system', systemId64: 'selected' }] as const,
    };
    const result = galaxyLabelCandidates(scene, undefined, {
      hoveredSystemId64: 'hovered',
      anchor: point('external-anchor'),
    });
    expect(result.map((candidate) => candidate.key)).toEqual([
      'system:selected',
      'system:hovered',
      'system:external-anchor',
      'system:finder',
    ]);
  });

  it.each([
    [100, 12],
    [500, 12],
    [501, 8],
    [1_500, 8],
    [1_501, 4],
    [3_500, 4],
    [3_501, 2],
    [9_500, 2],
    [9_501, 0],
    [100_000, 0],
  ])(
    'bounds ordinary catalogue labels at %i LY to %i',
    (distanceLy, expected) => {
      const scene = galaxy(
        Array.from({ length: 100 }, (_, index) =>
          point(String(index), index / 10),
        ),
      );
      const result = galaxyLabelCandidates({
        ...scene,
        camera: { ...camera, distanceLy },
      });
      expect(nearbyCatalogueLabelLimit(distanceLy)).toBe(expected);
      expect(result).toHaveLength(expected);
      expect(result.map((candidate) => candidate.target)).toEqual(
        Array.from({ length: expected }, (_, index) => ({
          kind: 'system',
          systemId64: String(index),
        })),
      );
    },
  );

  it('chooses the nearest screen positions, omitting offscreen and behind-camera stars', () => {
    const nearCentre = point('near-centre', 2);
    const scene = galaxy([
      point('offscreen', 20_000),
      { ...point('behind'), positionLy: { x: 0, y: 600, z: 0 } },
      point('further-on-screen', 100),
      nearCentre,
    ]);
    expect(
      galaxyLabelCandidates(scene).map((candidate) => candidate.key),
    ).toEqual(['system:near-centre', 'system:further-on-screen']);
  });

  it('deduplicates by id64, retaining Finder summary and catalogue star class', () => {
    const catalogue = point('same');
    const finder = {
      ...point('same'),
      primaryStar: undefined,
      summary: { population: 123 },
    };
    const scene = galaxy([catalogue], [finder]);
    const result = galaxyLabelCandidates(scene);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      source: 'finder',
      point: { primaryStar: { type: 'G2' }, summary: { population: 123 } },
    });
    expect(galaxySystemPointIndex(scene).get('same')).toBe(result[0].point);
  });

  it('keeps the raw catalogue class when a duplicate Finder point has a broader type', () => {
    const catalogue = { ...point('same'), primaryStar: { type: 'G2' } };
    const finder = {
      ...point('same'),
      primaryStar: { type: 'G', subtype: '2 V' },
      summary: { population: 123 },
    };
    const scene = galaxy([catalogue], [finder]);
    const result = galaxyLabelCandidates(scene);
    expect(result[0].point).toMatchObject({
      primaryStar: { type: 'G2', subtype: '2 V' },
      summary: { population: 123 },
    });
    expect(galaxySystemPointIndex(scene).get('same')).toBe(result[0].point);
  });

  it('bounds the set even with many Finder and selected systems', () => {
    const systems = Array.from({ length: 500 }, (_, index) =>
      point(String(index), index),
    );
    const scene = galaxy(systems, systems);
    const candidates = galaxyLabelCandidates({
      ...scene,
      selection: systems.map((value) => ({
        kind: 'system',
        systemId64: value.systemId64,
      })),
    });
    expect(candidates).toHaveLength(MAXIMUM_SYSTEM_LABEL_CANDIDATES);
    expect(galaxyLabelCandidates(scene)).toHaveLength(24);
  });

  it('reuses the source index and nearest retrieval across hover and selection changes', () => {
    const positionRead = vi.fn(() => ({ x: 150, y: 0, z: 0 }));
    const distant = {
      ...point('distant'),
      get positionLy() {
        return positionRead();
      },
    };
    const scene = galaxy([
      distant,
      ...Array.from({ length: 15 }, (_, index) => point(String(index), index)),
    ]);
    galaxyLabelCandidates(scene);
    const index = galaxySystemPointIndex(scene);
    const previousReads = positionRead.mock.calls.length;
    const selected = {
      ...scene,
      camera: { ...scene.camera, revision: 5 },
      contributions: scene.contributions.map((value) => ({ ...value })),
      selection: [{ kind: 'system', systemId64: '1' }] as const,
    };
    galaxyLabelCandidates(selected, undefined, { hoveredSystemId64: '0' });
    expect(galaxySystemPointIndex(selected)).toBe(index);
    expect(positionRead).toHaveBeenCalledTimes(previousReads);
    galaxyLabelCandidates({
      ...selected,
      camera: { ...selected.camera, focusLy: { x: 5, y: 0, z: 0 } },
    });
    expect(positionRead.mock.calls.length).toBeGreaterThan(previousReads);
  });

  it('drops lower-ranked overlaps and preserves the winning system identity', () => {
    const scene = {
      ...galaxy(
        [
          point('nearest'),
          point('anchor'),
          point('hovered'),
          point('selected'),
        ],
        [point('finder')],
      ),
      selection: [{ kind: 'system', systemId64: 'selected' }] as const,
    };
    const candidates = galaxyLabelCandidates(scene, undefined, {
      hoveredSystemId64: 'hovered',
      anchor: point('anchor'),
      viewport,
    });
    const projected = layoutGalaxyLabels(candidates, scene.camera, viewport);
    expect(projected).toHaveLength(1);
    expect(projected[0]).toMatchObject({
      key: 'system:selected',
      text: 'Star selected',
      target: { kind: 'system', systemId64: 'selected' },
    });
    for (let rank = 1; rank < candidates.length; rank += 1) {
      const remaining = layoutGalaxyLabels(
        candidates.slice(rank),
        scene.camera,
        viewport,
      );
      expect(remaining).toHaveLength(1);
      expect(remaining[0].target).toEqual(candidates[rank].target);
    }
  });

  it('breaks equal-priority overlapping label ties by nearer screen position', () => {
    const result = layoutGalaxyLabels(
      [label('a-further', 10, 0), label('z-nearer', 0, 0)],
      camera,
      viewport,
    );
    expect(result.map((candidate) => candidate.key)).toEqual(['z-nearer']);
  });
});
