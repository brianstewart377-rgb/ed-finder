import type { SystemDetail, SystemDetailBody } from '$lib/api/client';
import { stellarFamilyFromCatalogue } from './stellar-presentation';

import type {
  BodyFamily,
  BodyVisualDescriptor,
  SpatialTarget,
  SystemSceneContract,
  Truth,
} from './contracts';

const factual = <T>(value: T, source?: string): Truth<T> => ({
  value,
  representation: 'AUTHORITATIVE',
  ...(source ? { provenance: [{ source }] } : {}),
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

/** Classify the retained class fact for presentation, never from other body data. */
export function bodyFamilyFromClass(bodyClass: string | null): BodyFamily {
  switch (bodyClass?.trim().toLowerCase()) {
    case 'earth-like world':
      return { family: 'earth-like' };
    case 'water world':
      return { family: 'water-world' };
    case 'ammonia world':
      return { family: 'ammonia-world' };
    case 'high metal content world':
      return { family: 'high-metal-content' };
    case 'metal-rich body':
      return { family: 'metal-rich' };
    case 'rocky body':
      return { family: 'rocky' };
    case 'rocky ice world':
    case 'rocky ice body':
      return { family: 'rocky-ice' };
    case 'icy body':
      return { family: 'icy' };
    case 'class i gas giant':
      return { family: 'gas-giant', variant: 'I' };
    case 'class ii gas giant':
      return { family: 'gas-giant', variant: 'II' };
    case 'class iii gas giant':
      return { family: 'gas-giant', variant: 'III' };
    case 'class iv gas giant':
      return { family: 'gas-giant', variant: 'IV' };
    case 'class v gas giant':
      return { family: 'gas-giant', variant: 'V' };
    case 'gas giant with water-based life':
    case 'gas giant with water based life':
      return { family: 'gas-giant-life', variant: 'water' };
    case 'gas giant with ammonia-based life':
    case 'gas giant with ammonia based life':
      return { family: 'gas-giant-life', variant: 'ammonia' };
    case 'helium-rich gas giant':
    case 'helium gas giant':
      return { family: 'helium-gas-giant' };
    case 'water giant':
      return { family: 'water-giant' };
    default:
      return { family: 'unknown' };
  }
}

type BodyFamilyPresentation = Readonly<{
  label: string;
  colour: readonly [number, number, number];
}>;

/** The legend and renderer share a restrained, illustrative (not observed) palette. */
export const BODY_FAMILY_PRESENTATIONS = {
  'earth-like': { label: 'Earth-like', colour: [0.16, 0.58, 0.57] },
  'water-world': { label: 'Water world', colour: [0.12, 0.32, 0.64] },
  'ammonia-world': { label: 'Ammonia world', colour: [0.62, 0.39, 0.22] },
  'high-metal-content': {
    label: 'High metal content',
    colour: [0.52, 0.46, 0.4],
  },
  'metal-rich': { label: 'Metal-rich', colour: [0.34, 0.3, 0.28] },
  rocky: { label: 'Rocky', colour: [0.72, 0.57, 0.4] },
  'rocky-ice': { label: 'Rocky ice', colour: [0.62, 0.7, 0.76] },
  icy: { label: 'Icy', colour: [0.82, 0.92, 0.97] },
  'gas-giant-I': { label: 'Gas giant · I', colour: [0.8, 0.78, 0.67] },
  'gas-giant-II': { label: 'Gas giant · II', colour: [0.88, 0.76, 0.53] },
  'gas-giant-III': { label: 'Gas giant · III', colour: [0.42, 0.56, 0.68] },
  'gas-giant-IV': { label: 'Gas giant · IV', colour: [0.67, 0.35, 0.24] },
  'gas-giant-V': { label: 'Gas giant · V', colour: [0.46, 0.15, 0.13] },
  'gas-giant-life-water': {
    label: 'Life-bearing giant · water',
    colour: [0.41, 0.63, 0.46],
  },
  'gas-giant-life-ammonia': {
    label: 'Life-bearing giant · ammonia',
    colour: [0.61, 0.45, 0.68],
  },
  'helium-gas-giant': { label: 'Helium gas giant', colour: [0.88, 0.84, 0.75] },
  'water-giant': { label: 'Water giant', colour: [0.64, 0.83, 0.94] },
  unknown: { label: 'Unknown class', colour: [0.48, 0.48, 0.52] },
} as const satisfies Readonly<Record<string, BodyFamilyPresentation>>;

export function bodyFamilyPresentation(
  bodyFamily: BodyFamily,
): BodyFamilyPresentation {
  if (bodyFamily.family === 'gas-giant') {
    return BODY_FAMILY_PRESENTATIONS[`gas-giant-${bodyFamily.variant}`];
  }
  if (bodyFamily.family === 'gas-giant-life') {
    return BODY_FAMILY_PRESENTATIONS[`gas-giant-life-${bodyFamily.variant}`];
  }
  return BODY_FAMILY_PRESENTATIONS[bodyFamily.family];
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
  const family = stellarFamilyFromCatalogue(spectral);
  if (family === 'neutron') return 'Neutron Star';
  if (family === 'supermassive-black-hole') return 'Supermassive Black Hole';
  if (family === 'black-hole') return 'Black Hole';
  if (family === 'white-dwarf') return `White Dwarf (${full}) Star`;
  if (family === 'wolf-rayet') return `Wolf-Rayet (${full}) Star`;
  if (family === 'TTS') return `T Tauri (${full}) Star`;
  if (family === 'AeBe') return `Herbig Ae/Be (${full}) Star`;
  if (family === 'carbon') return `${full} (Carbon) Star`;
  if (family.length === 1) return `${family} (${full}) Star`;
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
        ...(body.bodyType === 'planet' && body.bodyClass != null
          ? {
              bodyClass: factual(
                body.bodyClass,
                body.bodyClassSource ?? undefined,
              ),
            }
          : {}),
        ...(body.bodyType === 'planet'
          ? { bodyFamily: bodyFamilyFromClass(body.bodyClass) }
          : {}),
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
