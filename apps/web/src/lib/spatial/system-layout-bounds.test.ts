import { describe, expect, it } from 'vitest';

import { systemDetailFromV3, type BodyV1 } from '$lib/api/client';
import { v3Body, v3Ring, v3System } from '$lib/api/v3-system-fixtures';

import {
  buildSystemScene,
  systemBodyLayout,
  type SystemBodyLayout,
} from './system-scene';

const bodyKey = (id: number): string => String(10_000 + id);

function body(id: number, parentId: number, axisKm: number): BodyV1 {
  return v3Body({
    body_id: bodyKey(id),
    frontier_body_id: String(id),
    direct_parent_body_id: bodyKey(parentId),
    name: `Body ${id}`,
    body_type: 'planet',
    is_main_star: false,
    spectral_class: null,
    luminosity_class: null,
    radius_km: 6_400,
    semi_major_axis_km: axisKm,
    distance_from_arrival_ls: axisKm / 299_792.458,
  });
}

const star = () =>
  v3Body({ body_id: bodyKey(0), frontier_body_id: '0', name: 'Sol-like' });

function denseSystem() {
  return buildSystemScene(
    systemDetailFromV3(
      v3System(),
      [
        star(),
        ...Array.from({ length: 9 }, (_, index) =>
          body(index + 1, 0, 50_000_000 * 2 ** index),
        ),
        body(31, 3, 384_400),
        body(32, 3, 600_000),
        body(311, 31, 12_000),
      ],
      [v3Ring({ body_id: bodyKey(3) })],
      [],
    ),
    1,
  );
}

const separation = (left: SystemBodyLayout, right: SystemBodyLayout) =>
  Math.hypot(
    left.position.x - right.position.x,
    left.position.y - right.position.y,
    left.position.z - right.position.z,
  );

// The current torus has diameter 3.2r and thickness 0.18r (minimum 0.06).
// Assert against the visible geometry, including its outer edge.
function glyphRadius(layout: SystemBodyLayout): number {
  const radius = layout.body.displayRadius;
  return layout.body.rings?.state === 'PRESENT'
    ? radius * 1.6 + Math.max(0.06, radius * 0.18) / 2
    : radius;
}

describe('hierarchical system layout region bounds', () => {
  it('separates rendered bodies and rings in a dense planetary system with nested moons', () => {
    const layouts = systemBodyLayout(denseSystem().bodies);
    for (let left = 0; left < layouts.length; left++) {
      for (let right = left + 1; right < layouts.length; right++) {
        const first = layouts[left]!;
        const second = layouts[right]!;
        expect(
          separation(first, second),
          `${first.body.name} overlaps ${second.body.name}`,
        ).toBeGreaterThan(glyphRadius(first) + glyphRadius(second));
      }
    }
  });

  it('contains every visible body and descendant region within its allocated parent region', () => {
    const layouts = systemBodyLayout(denseSystem().bodies);
    const byId = new Map(
      layouts.map((layout) => [layout.body.ref.bodyId, layout]),
    );
    for (const layout of layouts) {
      expect(layout.regionRadius, layout.body.name).toBeGreaterThanOrEqual(
        glyphRadius(layout),
      );
      if (layout.parentBodyId === null) continue;
      const parent = byId.get(layout.parentBodyId)!;
      expect(
        separation(layout, parent) + layout.regionRadius,
        `${layout.body.name} exceeds ${parent.body.name}'s region`,
      ).toBeLessThanOrEqual(parent.regionRadius + 1e-9);
    }
  });

  it('keeps all moon descendants away from every sibling planet radial band', () => {
    const layouts = systemBodyLayout(denseSystem().bodies);
    const byId = new Map(
      layouts.map((layout) => [layout.body.ref.bodyId, layout]),
    );
    const origin = byId.get(0)!;
    const siblings = layouts.filter(
      (layout) => layout.parentBodyId === 0 && layout.body.ref.bodyId !== 3,
    );
    for (const moonId of [31, 32, 311]) {
      const moon = byId.get(moonId)!;
      const moonDistance = separation(moon, origin);
      for (const sibling of siblings) {
        const siblingDistance = separation(sibling, origin);
        expect(
          Math.abs(moonDistance - siblingDistance),
          `${moon.body.name} crosses ${sibling.body.name}'s radial band`,
        ).toBeGreaterThan(moon.regionRadius + sibling.regionRadius);
      }
    }
  });

  it('keeps finite, deterministic positions when a large forest is shuffled', () => {
    const bodies = [star()];
    for (let planet = 1; planet <= 256; planet++) {
      bodies.push(body(planet, 0, 100_000 * 1.05 ** planet));
      for (let moon = 1; moon <= 3; moon++)
        bodies.push(body(1000 + planet * 3 + moon, planet, moon * 200_000));
    }
    const scene = buildSystemScene(
      systemDetailFromV3(v3System(), bodies, [], []),
      1,
    );
    const expected = systemBodyLayout(scene.bodies);
    const shuffled = [
      ...scene.bodies.filter((_, index) => index % 2 === 1).reverse(),
      ...scene.bodies.filter((_, index) => index % 2 === 0).reverse(),
    ];
    const sorted = (layouts: readonly SystemBodyLayout[]) =>
      [...layouts].sort(
        (left, right) => left.body.ref.bodyId - right.body.ref.bodyId,
      );
    expect(sorted(systemBodyLayout(shuffled))).toEqual(sorted(expected));
    for (const layout of expected) {
      expect(Number.isFinite(layout.position.x)).toBe(true);
      expect(Number.isFinite(layout.position.z)).toBe(true);
      expect(layout.regionRadius).toBeGreaterThanOrEqual(glyphRadius(layout));
    }
  });
});
