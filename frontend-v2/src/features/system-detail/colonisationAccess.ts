export type ColonisationAccessKind = 'unavailable' | 'direct' | 'estimate';

export interface ColonisationAccessEstimate {
  kind: ColonisationAccessKind;
  distanceLy: number | null;
  claimHopReachLy: number | null;
  intermediateClaims: number | null;
  totalNewClaims: number | null;
}

/**
 * No current mechanics/evidence record in this repository verifies the maximum
 * colonisation claim hop. Keep this null until a reviewed evidence-backed value
 * is introduced; callers must render the unavailable state rather than guess.
 */
export const VERIFIED_CLAIM_HOP_REACH_LY: number | null = null;

export function calculateColonisationAccess(
  distanceLy: number | null | undefined,
  claimHopReachLy: number | null | undefined = VERIFIED_CLAIM_HOP_REACH_LY,
): ColonisationAccessEstimate {
  const safeDistance = Number.isFinite(distanceLy) && Number(distanceLy) >= 0
    ? Number(distanceLy)
    : null;
  const safeReach = Number.isFinite(claimHopReachLy) && Number(claimHopReachLy) > 0
    ? Number(claimHopReachLy)
    : null;

  if (safeDistance == null || safeReach == null) {
    return {
      kind: 'unavailable',
      distanceLy: safeDistance,
      claimHopReachLy: safeReach,
      intermediateClaims: null,
      totalNewClaims: null,
    };
  }

  const intermediateClaims = Math.max(0, Math.ceil(safeDistance / safeReach) - 1);
  return {
    kind: intermediateClaims === 0 ? 'direct' : 'estimate',
    distanceLy: safeDistance,
    claimHopReachLy: safeReach,
    intermediateClaims,
    totalNewClaims: intermediateClaims + 1,
  };
}
