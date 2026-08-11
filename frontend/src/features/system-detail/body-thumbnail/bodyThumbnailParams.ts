import type { SystemBody } from '../../../types/api';
import { spectralStarColor } from '../../../lib/starColor';

// Maps an Elite-Dangerous body to the parameters used to render its procedural
// thumbnail. `body_type` is coarse (Star/Planet/Moon/Barycentre/Unknown); the
// fine ED class (Icy body, High metal content world, Gas giant, ...) lives in
// the free-text `subtype`, so the mapping keys off subtype + the boolean flags.

export interface BodyThumbnailParams {
  /** 'none' → do not render a thumbnail (barycentres, null/unknown-without-subtype). */
  kind: 'planet' | 'star' | 'none';
  /** Base surface color, hex. Stars use this as their glow color. */
  base: string;
  /** Accent for bands / clouds / surface detail, hex. */
  accent: string;
  /** Render banded gas-giant flow instead of a rocky/icy surface. */
  gasGiant: boolean;
  /** Draw a ring around the body. */
  rings: boolean;
  /** Draw an atmospheric rim halo. */
  atmosphere: boolean;
  /** Atmosphere rim color, hex. */
  atmosphereColor: string;
  /** Surface noise contrast, 0 (smooth) .. 1 (rough). */
  contrast: number;
}

const has = (s: string | null | undefined, needle: string): boolean =>
  (s ?? '').toLowerCase().includes(needle);

export function bodyThumbnailParams(body: SystemBody): BodyThumbnailParams {
  const type = body.body_type ?? '';
  const subtype = body.subtype ?? '';

  if (type === 'Barycentre') {
    return neutral('none');
  }

  if (type === 'Star') {
    const color = spectralStarColor(body.spectral_class);
    return { kind: 'star', base: color, accent: color, gasGiant: false, rings: false, atmosphere: true, atmosphereColor: color, contrast: 0.35 };
  }

  // --- planets & moons, classed by subtype / flags ---
  if (body.is_earth_like || has(subtype, 'earth-like')) {
    return planet('#2f6f4f', '#d8ecff', { atmosphere: true, atmosphereColor: '#9fd0ff', contrast: 0.5 });
  }
  if (body.is_water_world || has(subtype, 'water world')) {
    return planet('#20486f', '#eaf4ff', { atmosphere: true, atmosphereColor: '#bfe0ff', contrast: 0.45 });
  }
  if (body.is_ammonia_world || has(subtype, 'ammonia')) {
    return planet('#8a6a37', '#e6c98f', { atmosphere: true, atmosphereColor: '#d8b878', contrast: 0.5 });
  }
  if (has(subtype, 'giant')) { // gas giant / water giant / helium-rich giant
    const [base, accent] = gasGiantColors(subtype);
    return { kind: 'planet', base, accent, gasGiant: true, rings: gasGiantHasRings(subtype), atmosphere: true, atmosphereColor: accent, contrast: 0.7 };
  }
  if (has(subtype, 'high metal content')) {
    return planet('#5a4b40', '#8a7360', { contrast: 0.75 });
  }
  if (has(subtype, 'metal-rich') || has(subtype, 'metal rich')) {
    return planet('#7c7168', '#c9bcae', { contrast: 0.8 });
  }
  if (has(subtype, 'rocky ice')) {
    return planet('#6d7c86', '#cfe2ec', { contrast: 0.6 });
  }
  if (has(subtype, 'icy')) {
    return planet('#7fa7bd', '#eaf6ff', { atmosphere: true, atmosphereColor: '#cfeaff', contrast: 0.45 });
  }
  if (has(subtype, 'rocky') || type === 'Planet' || type === 'Moon') {
    return planet('#7a5a3f', '#b9967a', { contrast: 0.72 });
  }

  // Unknown planet/moon without a recognisable subtype.
  return type === 'Unknown' && subtype === '' ? neutral('none') : planet('#6f6f6f', '#a0a0a0', { contrast: 0.6 });
}

function planet(
  base: string,
  accent: string,
  extra?: Partial<Pick<BodyThumbnailParams, 'atmosphere' | 'atmosphereColor' | 'rings' | 'contrast'>>,
): BodyThumbnailParams {
  return {
    kind: 'planet', base, accent, gasGiant: false,
    rings: extra?.rings ?? false,
    atmosphere: extra?.atmosphere ?? false,
    atmosphereColor: extra?.atmosphereColor ?? accent,
    contrast: extra?.contrast ?? 0.6,
  };
}

function neutral(kind: BodyThumbnailParams['kind']): BodyThumbnailParams {
  return { kind, base: '#3a3a3a', accent: '#555555', gasGiant: false, rings: false, atmosphere: false, atmosphereColor: '#555555', contrast: 0.3 };
}

// Extract the Sudarsky class roman numeral with a word boundary so that
// 'class iii' does not also substring-match 'class ii' / 'class i'.
function gasGiantClass(subtype: string): string | null {
  const match = /\bclass\s+(iv|iii|ii|i|v)\b/.exec(subtype.toLowerCase());
  return match ? match[1] : null;
}

function gasGiantColors(subtype: string): [string, string] {
  if (has(subtype, 'water giant')) return ['#3a6f7a', '#bfe6ea'];
  if (has(subtype, 'helium')) return ['#b8a06a', '#efe0b8'];
  switch (gasGiantClass(subtype)) {
    case 'i': return ['#c9a06a', '#f0dcc0'];   // Sudarsky I: warm bands
    case 'ii': return ['#e8e8ea', '#ffffff'];  // II: ammonia cloud, pale
    case 'iii': return ['#9aa7b5', '#d6e0ea']; // III: clear, bluish
    case 'iv':
    case 'v': return ['#8a5540', '#c98f6a'];   // IV/V: hot, dark red
    default: return ['#c08a55', '#efd3a8'];    // generic gas giant
  }
}

function gasGiantHasRings(subtype: string): boolean {
  // Sudarsky class I/II giants (and water giants) most commonly carry rings.
  if (has(subtype, 'water giant')) return true;
  const cls = gasGiantClass(subtype);
  return cls === 'i' || cls === 'ii';
}
