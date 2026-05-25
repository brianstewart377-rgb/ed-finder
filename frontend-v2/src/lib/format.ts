/**
 * Pure-data formatters used by the result card. No DOM, no React — easy to
 * unit test and reuse from any UI layer (current vanilla JS app, this React
 * app, future mobile app, anything).
 */

/** Bucketise a system score into Elite-style rating tiers. */
export function ratingTier(score: number | null | undefined): {
  label: 'EXCELLENT' | 'GOOD' | 'OK' | 'POOR' | 'N/A';
  className: string;
  fillColor: string;
} {
  if (score == null || Number.isNaN(score)) {
    return { label: 'N/A', className: 'rating-na', fillColor: '#666' };
  }
  if (score >= 80) return { label: 'EXCELLENT', className: 'rating-excellent', fillColor: '#3ddc84' };
  if (score >= 60) return { label: 'GOOD',      className: 'rating-good',      fillColor: '#facc15' };
  if (score >= 40) return { label: 'OK',        className: 'rating-ok',        fillColor: '#ff6a00' };
  return                  { label: 'POOR',      className: 'rating-poor',      fillColor: '#ef4444' };
}

/** Compact human-readable population (12.3M, 800K, 250). */
export function formatPopulation(pop: number | null | undefined): string {
  if (pop == null || Number.isNaN(pop)) return 'Unknown';
  if (pop <= 0) return 'Uninhabited';
  if (pop >= 1_000_000_000) return `${(pop / 1e9).toFixed(1)}B`;
  if (pop >= 1_000_000)     return `${(pop / 1e6).toFixed(1)}M`;
  if (pop >= 1_000)         return `${(pop / 1e3).toFixed(1)}K`;
  return String(pop);
}

const SOL_ID64 = 10477373803;

/** Confidence number → displayable summary. Null = field absent. */
export function formatConfidence(c: number | null | undefined):
  | { tier: 'High' | 'Medium' | 'Low'; pct: number; symbol: '●' | '◐' | '○' }
  | null {
  if (c == null || Number.isNaN(c)) return null;
  const pct = Math.round(c * 100);
  if (pct >= 75) return { tier: 'High',   pct, symbol: '●' };
  if (pct >= 50) return { tier: 'Medium', pct, symbol: '◐' };
  return            { tier: 'Low',     pct, symbol: '○' };
}

/**
 * Format a distance value for display. Returns `null` when the distance
 * is unknown/unavailable so callers can render `—` or a fallback label.
 *
 * Rules:
 *  - null / undefined / NaN → null (unknown)
 *  - 0.00 is only considered valid when `allowZero` is true (same-system
 *    reference). Otherwise treated as unknown (backend may emit 0.0 for
 *    galaxy-wide searches where no reference is set).
 */
export function formatDistance(
  d: number | null | undefined,
  opts?: { allowZero?: boolean },
): string | null {
  if (d == null || !Number.isFinite(d)) return null;
  if (d === 0 && !opts?.allowZero) return null;
  return `${d.toFixed(2)} LY`;
}

export function hasKnownCoords(
  c: { x?: number | null; y?: number | null; z?: number | null; id64?: number | string | null } | null | undefined,
  id64?: number | string | null,
): c is { x: number; y: number; z: number } {
  if (!c || c.x == null || c.y == null || c.z == null) return false;
  if (!Number.isFinite(c.x) || !Number.isFinite(c.y) || !Number.isFinite(c.z)) return false;
  const systemId = id64 ?? c.id64;
  const numericId = systemId == null ? null : Number(systemId);
  if (c.x === 0 && c.y === 0 && c.z === 0 && numericId !== SOL_ID64) return false;
  return true;
}

/** Format coordinates for display. Unknown means not trusted, not zero. */
export function formatCoords(
  c: { x?: number | null; y?: number | null; z?: number | null; id64?: number | string | null } | null | undefined,
  id64?: number | string | null,
): string {
  if (!hasKnownCoords(c, id64)) return 'Unknown';
  return `${c.x.toFixed(2)}, ${c.y.toFixed(2)}, ${c.z.toFixed(2)}`;
}

export function distanceFromSol(
  c: { x?: number | null; y?: number | null; z?: number | null; id64?: number | string | null } | null | undefined,
  id64?: number | string | null,
): number | null {
  if (!hasKnownCoords(c, id64)) return null;
  return Math.hypot(c.x, c.y, c.z);
}

/** Multi-signal "is this system colonised" check.
 * Spansh's `is_colonised` flag is unreliable for old systems, so we OR a
 * few correlated signals together — same logic the vanilla app uses. */
export function isInhabited(sys: {
  is_colonised?:        boolean | null;
  is_being_colonised?:  boolean | null;
  population?:          number | null;
}): boolean {
  return !!(sys.is_colonised || sys.is_being_colonised || (sys.population ?? 0) > 0);
}

export function formatPopulationForSystem(sys: {
  is_colonised?:        boolean | null;
  is_being_colonised?:  boolean | null;
  population?:          number | null;
}): string {
  if (sys.population == null || Number.isNaN(sys.population)) return 'Unknown';
  const pop = sys.population;
  if (pop > 0) return formatPopulation(pop);
  return isInhabited(sys) ? 'Population unknown' : 'Uninhabited';
}

export function systemStatusLabel(sys: {
  is_colonised?:        boolean | null;
  is_being_colonised?:  boolean | null;
  population?:          number | null;
}): 'Colonised' | 'Colonising' | 'Available' {
  if (sys.is_colonised || (sys.population ?? 0) > 0) return 'Colonised';
  if (sys.is_being_colonised) return 'Colonising';
  return 'Available';
}
