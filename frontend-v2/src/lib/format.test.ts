import { describe, expect, it } from 'vitest';
import {
  formatDistance,
  formatConfidence,
  ratingTier,
  formatCoords,
  formatPopulation,
  formatPopulationForSystem,
  systemStatusLabel,
} from './format';

describe('formatDistance', () => {
  it('returns null for null distance', () => {
    expect(formatDistance(null)).toBeNull();
  });

  it('returns null for undefined distance', () => {
    expect(formatDistance(undefined)).toBeNull();
  });

  it('returns null for NaN distance', () => {
    expect(formatDistance(NaN)).toBeNull();
  });

  it('returns null for Infinity distance', () => {
    expect(formatDistance(Infinity)).toBeNull();
  });

  it('returns null for zero distance by default (fake zero from galaxy-wide search)', () => {
    expect(formatDistance(0)).toBeNull();
  });

  it('returns 0.00 LY when allowZero is true (same-system reference)', () => {
    expect(formatDistance(0, { allowZero: true })).toBe('0.00 LY');
  });

  it('formats valid positive distance', () => {
    expect(formatDistance(12.34)).toBe('12.34 LY');
  });

  it('formats small positive distance', () => {
    expect(formatDistance(0.01)).toBe('0.01 LY');
  });

  it('formats large distance', () => {
    expect(formatDistance(65279.123)).toBe('65279.12 LY');
  });
});

describe('formatConfidence', () => {
  it('returns null for null', () => {
    expect(formatConfidence(null)).toBeNull();
  });

  it('returns High for >= 0.75', () => {
    const c = formatConfidence(0.85);
    expect(c?.tier).toBe('High');
    expect(c?.pct).toBe(85);
  });

  it('returns Medium for >= 0.50', () => {
    const c = formatConfidence(0.6);
    expect(c?.tier).toBe('Medium');
  });

  it('returns Low for < 0.50', () => {
    const c = formatConfidence(0.3);
    expect(c?.tier).toBe('Low');
  });
});

describe('formatCoords', () => {
  it('returns Unknown for null coordinates', () => {
    expect(formatCoords({ x: null, y: 1, z: 2 }, 123)).toBe('Unknown');
  });

  it('treats non-Sol 0,0,0 as unknown', () => {
    expect(formatCoords({ x: 0, y: 0, z: 0 }, 123)).toBe('Unknown');
  });

  it('allows Sol at 0,0,0', () => {
    expect(formatCoords({ x: 0, y: 0, z: 0 }, 10477373803)).toBe('0.00, 0.00, 0.00');
  });
});

describe('system population/status display', () => {
  it('renders unknown population as Unknown', () => {
    expect(formatPopulation(null)).toBe('Unknown');
    expect(formatPopulationForSystem({ population: null })).toBe('Unknown');
  });

  it('does not call a colonised zero-population system uninhabited', () => {
    const sys = { is_colonised: true, population: 0 };
    expect(systemStatusLabel(sys)).toBe('Colonised');
    expect(formatPopulationForSystem(sys)).toBe('Population unknown');
  });
});

describe('ratingTier', () => {
  it('returns N/A for null score', () => {
    expect(ratingTier(null).label).toBe('N/A');
  });

  it('returns EXCELLENT for >= 80', () => {
    expect(ratingTier(85).label).toBe('EXCELLENT');
  });

  it('returns GOOD for >= 60', () => {
    expect(ratingTier(65).label).toBe('GOOD');
  });

  it('returns OK for >= 40', () => {
    expect(ratingTier(45).label).toBe('OK');
  });

  it('returns POOR for < 40', () => {
    expect(ratingTier(20).label).toBe('POOR');
  });
});
