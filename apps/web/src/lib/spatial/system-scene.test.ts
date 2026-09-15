import { describe, expect, it } from 'vitest';

import type { SystemDetail } from '$lib/api/client';
import { parseId64 } from '$lib/domain/id64';

import { buildSystemScene, systemBodyLayout } from './system-scene';

const fixture: SystemDetail = {
  id64: parseId64('10477373803'),
  name: 'Reference System',
  bodies: [
    {
      id: 0,
      name: 'Reference System',
      body_type: 'Star',
      subtype: 'G (White-Yellow) Star',
      distance_from_star: 0,
      radius: 695_700_000,
      ring_state: 'not_ringed',
    },
    {
      id: 3,
      name: 'Reference System 3',
      body_type: 'Planet',
      subtype: 'Gas giant with water based life',
      distance_from_star: 11_450,
      radius: 70_000_000,
      ring_state: 'ringed',
      rings: [
        {
          ring_name: 'Reference System 3 A Ring',
          ring_class: 'Icy',
          inner_radius: 90_000_000,
          outer_radius: 130_000_000,
          source: 'journal',
        },
      ],
    },
  ],
  stations: [],
};

describe('system scene', () => {
  it('keeps body facts authoritative and layout explicitly schematic', () => {
    const scene = buildSystemScene(fixture, 4);
    expect(scene.kind).toBe('system');
    expect(scene.fidelity).toBe('S1');
    expect(scene.bodies[1]).toMatchObject({
      name: 'Reference System 3',
      class: { value: 'Planet', representation: 'AUTHORITATIVE' },
      distanceFromArrivalLs: {
        value: 11_450,
        representation: 'AUTHORITATIVE',
      },
      orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
      rings: { state: 'PRESENT' },
    });
  });

  it('uses catalogue distance only to order a deterministic semantic layout', () => {
    const scene = buildSystemScene(fixture, 4);
    const layout = systemBodyLayout(scene.bodies);
    expect(layout[0]?.position).toEqual({ x: 0, y: 0, z: 0 });
    expect(layout[1]?.orbitRadius).toBeGreaterThan(4.8);
    expect(layout[1]?.position.y).toBe(0);
    expect(systemBodyLayout(scene.bodies)).toEqual(layout);
  });

  it('focuses a known selected body without inventing missing body ids', () => {
    const scene = buildSystemScene(
      {
        ...fixture,
        bodies: [...(fixture.bodies ?? []), { id: null, name: 'Unknown' }],
      },
      8,
      3,
    );
    expect(scene.bodies).toHaveLength(2);
    expect(scene.camera.focus).toEqual({
      kind: 'body',
      ref: { systemId64: fixture.id64, bodyId: 3 },
    });
  });
});
