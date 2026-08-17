/**
 * Spectral class -> normalized RGB [0-1] mapping for the Babylon real-star
 * layer's vertex colors.
 *
 * This is deliberately separate from `@/lib/starColor`'s `spectralStarColor`,
 * which returns a CSS hex string and is shared by the system-detail body
 * thumbnails (Canvas 2D) and the old Three.js map's viewportSystems.ts
 * (`THREE.Color.set(string)`). Reusing that function/name here would either
 * change its return type (breaking those consumers and their tests) or
 * require re-parsing a hex string back into floats on every star, so this
 * module owns its own float-RGB table per the MK spectral classification
 * used by the Babylon starsLayer.
 */

export interface SpectralRgb {
  r: number;
  g: number;
  b: number;
}

const SPECTRAL_RGB: Record<string, SpectralRgb> = {
  O: { r: 0.6, g: 0.8, b: 1.0 }, // blue
  B: { r: 0.7, g: 0.85, b: 1.0 }, // blue-white
  A: { r: 0.85, g: 0.9, b: 1.0 }, // white
  F: { r: 0.95, g: 0.95, b: 1.0 }, // yellow-white
  G: { r: 1.0, g: 1.0, b: 0.9 }, // yellow, Sol-like
  K: { r: 1.0, g: 0.8, b: 0.6 }, // orange
  M: { r: 1.0, g: 0.6, b: 0.4 }, // red
};

const DEFAULT_RGB: SpectralRgb = SPECTRAL_RGB.G;

/**
 * Resolve a spectral class string (e.g. "M2 V", "g") to a normalized RGB
 * triple. Unknown/missing classes default to G (Sol-like).
 */
export function spectralStarColor(spectralClass?: string | null): SpectralRgb {
  const first = (spectralClass ?? '').trim().charAt(0).toUpperCase();
  return SPECTRAL_RGB[first] ?? DEFAULT_RGB;
}
