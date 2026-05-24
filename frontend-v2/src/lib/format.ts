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
export function formatPopulation(pop: number): string {
  if (!pop || pop <= 0) return 'Uninhabited';
  if (pop >= 1_000_000_000) return `${(pop / 1e9).toFixed(1)}B`;
  if (pop >= 1_000_000)     return `${(pop / 1e6).toFixed(1)}M`;
  if (pop >= 1_000)         return `${(pop / 1e3).toFixed(1)}K`;
  return String(pop);
}

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
