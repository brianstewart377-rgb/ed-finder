import type { SystemDetail } from '$lib/api/client';

import type {
  BodyVisualDescriptor,
  SpatialTarget,
  SystemSceneContract,
  Truth,
} from './contracts';

const factual = <T>(value: T, source: string): Truth<T> => ({
  value,
  representation: 'AUTHORITATIVE',
  provenance: [{ source }],
});

function bodyDisplayRadius(
  body: NonNullable<SystemDetail['bodies']>[number],
): number {
  const identity =
    `${body.body_type ?? ''} ${body.subtype ?? ''}`.toLowerCase();
  if (identity.includes('star')) return identity.includes('dwarf') ? 1.45 : 2.2;
  if (identity.includes('black hole')) return 1.6;
  if (identity.includes('gas giant')) return 1.1;
  if (identity.includes('belt')) return 0.28;
  return 0.68;
}

function ringDescriptor(
  body: NonNullable<SystemDetail['bodies']>[number],
): BodyVisualDescriptor['rings'] {
  const state =
    body.ring_state === 'ringed'
      ? 'PRESENT'
      : body.ring_state === 'not_ringed'
        ? 'ABSENT'
        : 'UNKNOWN';
  return {
    state,
    bands: (body.rings ?? []).map((ring, index) => ({
      id: ring.ring_name ?? `${body.id}:ring:${index}`,
      ...(ring.ring_class
        ? { ringClass: factual(ring.ring_class, ring.source ?? 'catalogue') }
        : {}),
      ...(typeof ring.inner_radius === 'number'
        ? {
            innerRadiusM: factual(
              ring.inner_radius,
              ring.source ?? 'catalogue',
            ),
          }
        : {}),
      ...(typeof ring.outer_radius === 'number'
        ? {
            outerRadiusM: factual(
              ring.outer_radius,
              ring.source ?? 'catalogue',
            ),
          }
        : {}),
    })),
  };
}

export function buildSystemScene(
  system: SystemDetail,
  revision: number,
  selectedBodyId?: number,
): SystemSceneContract {
  const source = 'ED-Finder catalogue / system detail';
  const bodies = (system.bodies ?? [])
    .filter(
      (body): body is typeof body & { id: number } =>
        typeof body.id === 'number' && Number.isSafeInteger(body.id),
    )
    .map((body): BodyVisualDescriptor => ({
      ref: { systemId64: system.id64, bodyId: body.id },
      name: body.name ?? `Body ${body.id}`,
      ...(body.body_type ? { class: factual(body.body_type, source) } : {}),
      ...(body.subtype ? { subtype: factual(body.subtype, source) } : {}),
      ...(typeof body.radius === 'number' && body.radius > 0
        ? { physicalRadiusM: factual(body.radius, source) }
        : {}),
      ...(typeof body.distance_from_star === 'number' &&
      body.distance_from_star >= 0
        ? {
            distanceFromArrivalLs: factual(body.distance_from_star, source),
          }
        : {}),
      displayRadius: bodyDisplayRadius(body),
      orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
      rings: ringDescriptor(body),
    }));
  const focus: SpatialTarget =
    selectedBodyId !== undefined &&
    bodies.some((body) => body.ref.bodyId === selectedBodyId)
      ? {
          kind: 'body',
          ref: { systemId64: system.id64, bodyId: selectedBodyId },
        }
      : { kind: 'system', systemId64: system.id64 };

  return {
    kind: 'system',
    revision,
    systemId64: system.id64,
    fidelity: bodies.length > 0 ? 'S1' : 'S0',
    camera: {
      systemId64: system.id64,
      focus,
      semanticDistance: 38,
      bearingRad: -0.85,
      pitchRad: 0.58,
      revision,
    },
    bodies,
    infrastructure: [],
    contributions: [],
  };
}

export type SystemBodyLayout = Readonly<{
  body: BodyVisualDescriptor;
  orbitRadius: number;
  position: Readonly<{ x: number; y: number; z: number }>;
}>;

export function systemBodyLayout(
  bodies: readonly BodyVisualDescriptor[],
): readonly SystemBodyLayout[] {
  const orbiting = bodies.filter(
    (body) => (body.distanceFromArrivalLs?.value ?? 0) > 0,
  );
  const orbitingIndex = new Map(
    [...orbiting]
      .sort(
        (left, right) =>
          (left.distanceFromArrivalLs?.value ?? 0) -
            (right.distanceFromArrivalLs?.value ?? 0) ||
          left.ref.bodyId - right.ref.bodyId,
      )
      .map((body, index) => [body.ref.bodyId, index]),
  );
  return bodies.map((body) => {
    const distance = body.distanceFromArrivalLs?.value ?? 0;
    if (distance <= 0) {
      return { body, orbitRadius: 0, position: { x: 0, y: 0, z: 0 } };
    }
    const rank = orbitingIndex.get(body.ref.bodyId) ?? 0;
    const orbitRadius = Math.min(34, 4.8 + Math.log10(1 + distance) * 3.6);
    const angle = rank * 2.399963229728653;
    return {
      body,
      orbitRadius,
      position: {
        x: Math.cos(angle) * orbitRadius,
        y: 0,
        z: Math.sin(angle) * orbitRadius,
      },
    };
  });
}
