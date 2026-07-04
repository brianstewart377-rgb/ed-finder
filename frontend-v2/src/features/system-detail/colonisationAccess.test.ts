import { describe, expect, it } from 'vitest';
import { calculateColonisationAccess } from './colonisationAccess';

describe('calculateColonisationAccess', () => {
  it('does not create a numeric bridge when claim reach is not verified', () => {
    expect(calculateColonisationAccess(74.2, null)).toEqual({
      kind: 'unavailable',
      distanceLy: 74.2,
      claimHopReachLy: null,
      intermediateClaims: null,
      totalNewClaims: null,
    });
  });

  it('reports direct reach without an intermediate claim', () => {
    const result = calculateColonisationAccess(20, 20);
    expect(result.kind).toBe('direct');
    expect(result.intermediateClaims).toBe(0);
    expect(result.totalNewClaims).toBe(1);
  });

  it('uses one intermediate claim at an exact two-hop multiple', () => {
    const result = calculateColonisationAccess(40, 20);
    expect(result.kind).toBe('estimate');
    expect(result.intermediateClaims).toBe(1);
    expect(result.totalNewClaims).toBe(2);
  });

  it('uses ceiling behaviour for a non-exact multiple', () => {
    const result = calculateColonisationAccess(41, 20);
    expect(result.kind).toBe('estimate');
    expect(result.intermediateClaims).toBe(2);
    expect(result.totalNewClaims).toBe(3);
  });
});
