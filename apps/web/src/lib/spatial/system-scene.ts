import type { SystemDetail, SystemDetailBody } from '$lib/api/client';

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

const derived = <T>(value: T, source: string, note: string): Truth<T> => ({
  value,
  representation: 'DERIVED',
  provenance: [{ source, note }],
});

const BODY_TYPE_LABELS: Readonly<Record<string, string>> = {
  star: 'Star',
  planet: 'Planet',
  barycentre: 'Barycentre',
  belt_cluster: 'Belt cluster',
};

/** Display label for a V3 public body-type code. */
export function bodyTypeLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  return BODY_TYPE_LABELS[code] ?? code.replaceAll('_', ' ');
}

/** Spectral + luminosity class as catalogued, e.g. `G2 V`. */
export function stellarClassification(
  body: Pick<SystemDetailBody, 'spectralClass' | 'luminosityClass'>,
): string | null {
  const spectral = body.spectralClass?.trim();
  if (!spectral) return null;
  const luminosity = body.luminosityClass?.trim();
  return luminosity ? `${spectral} ${luminosity}` : spectral;
}

/**
 * Presentation-only stellar subtype phrased the way the shared stellar
 * presentation recognises classes (e.g. `G (G2 V) Star`, `White Dwarf (DA)
 * Star`). Derived from the catalogued spectral/luminosity class; never shown
 * as a catalogue fact.
 */
export function stellarPresentationSubtype(
  body: Pick<
    SystemDetailBody,
    'bodyType' | 'spectralClass' | 'luminosityClass'
  >,
): string | null {
  if (body.bodyType !== 'star') return null;
  const spectral = body.spectralClass?.trim();
  const full = stellarClassification(body);
  if (!spectral || !full) return null;
  // Catalogued classes carry numeric subclasses (`N0`, `H0`, `DA6`, `WC8`);
  // match on the family with the trailing subclass removed.
  const family = spectral.replace(/\d+(?:\.\d+)?$/u, '');
  if (/^N$/i.test(family)) return 'Neutron Star';
  if (/^SupermassiveBlackHole$/i.test(family)) return 'Supermassive Black Hole';
  if (/^H$/i.test(family)) return 'Black Hole';
  if (/^D/i.test(family)) return `White Dwarf (${full}) Star`;
  if (/^W/i.test(family)) return `Wolf-Rayet (${full}) Star`;
  if (/^TTS$/i.test(family)) return `T Tauri (${full}) Star`;
  if (/^AeBe$/i.test(family)) return `Herbig Ae/Be (${full}) Star`;
  if (/^(?:C|CN|CJ|CH|CHd|CS|MS|S)$/.test(family))
    return `${full} (Carbon) Star`;
  const letter = spectral.charAt(0).toUpperCase();
  if ('OBAFGKMLTY'.includes(letter)) return `${letter} (${full}) Star`;
  return `${full} Star`;
}

function bodyDisplayRadius(body: SystemDetailBody): number {
  const identity = `${bodyTypeLabel(body.bodyType) ?? ''} ${
    stellarPresentationSubtype(body) ?? ''
  }`.toLowerCase();
  if (identity.includes('black hole')) return 1.6;
  if (identity.includes('star')) return identity.includes('dwarf') ? 1.45 : 2.2;
  if (identity.includes('belt')) return 0.28;
  return 0.68;
}

function ringDescriptor(
  body: SystemDetailBody,
  source: string,
): BodyVisualDescriptor['rings'] {
  const rings = body.rings.filter((ring) => ring.kind === 'RING');
  return {
    // The V3 catalogue lists known rings; it does not assert absence.
    state: rings.length > 0 ? 'PRESENT' : 'UNKNOWN',
    bands: rings.map((ring) => ({
      id: ring.ringKey,
      ...(ring.ringType ? { ringClass: factual(ring.ringType, source) } : {}),
      ...(typeof ring.innerRadiusKm === 'number'
        ? { innerRadiusM: factual(ring.innerRadiusKm * 1000, source) }
        : {}),
      ...(typeof ring.outerRadiusKm === 'number'
        ? { outerRadiusM: factual(ring.outerRadiusKm * 1000, source) }
        : {}),
    })),
  };
}

export function buildSystemScene(
  system: SystemDetail,
  revision: number,
  selectedBodyId?: number,
): SystemSceneContract {
  const source = 'ED-Finder V3 canonical catalogue';
  const bodies = system.bodies
    .filter(
      (body): body is typeof body & { id: number } =>
        typeof body.id === 'number' && Number.isSafeInteger(body.id),
    )
    .map((body): BodyVisualDescriptor => {
      const label = bodyTypeLabel(body.bodyType);
      const subtype = stellarPresentationSubtype(body);
      return {
        ref: { systemId64: system.id64, bodyId: body.id },
        name: body.name,
        ...(label ? { class: factual(label, source) } : {}),
        ...(subtype
          ? {
              subtype: derived(
                subtype,
                source,
                'presentation phrase derived from the catalogued spectral class',
              ),
            }
          : {}),
        ...(typeof body.radiusKm === 'number' && body.radiusKm > 0
          ? { physicalRadiusM: factual(body.radiusKm * 1000, source) }
          : {}),
        ...(typeof body.distanceFromArrivalLs === 'number' &&
        body.distanceFromArrivalLs >= 0
          ? {
              distanceFromArrivalLs: factual(
                body.distanceFromArrivalLs,
                source,
              ),
            }
          : {}),
        displayRadius: bodyDisplayRadius(body),
        orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
        rings: ringDescriptor(body, source),
      };
    });
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
