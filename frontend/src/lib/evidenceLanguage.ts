import type {
  PlannerWarehouseEvidence,
  WarehouseBoundedStagingStatus,
  WarehouseEvidenceEnvelopeStatus,
} from '@/types/api';
import type { SemanticStatusTone } from '@/components/SemanticStatusBadge';

export interface EvidencePostureContent {
  badgeLabel: string;
  badgeTone: SemanticStatusTone;
  summary: string;
  nextAction: string;
  plannerBoundary: string;
  caution?: string;
}

export function evidenceEnvelopeStatusLabel(status: WarehouseEvidenceEnvelopeStatus): string {
  if (status === 'available') return 'Available';
  if (status === 'unavailable') return 'Unavailable';
  if (status === 'not_evaluated') return 'Not evaluated';
  return 'Unknown';
}

export function evidencePostureContent(
  status: WarehouseEvidenceEnvelopeStatus,
  options?: {
    freshnessStatus?: PlannerWarehouseEvidence['freshnessStatus'];
    manualReviewRequired?: boolean;
    boundedStagingStatus?: WarehouseBoundedStagingStatus;
  },
): EvidencePostureContent {
  const caution = evidenceCautionText(options);

  if (status === 'available') {
    return {
      badgeLabel: 'Available',
      badgeTone: 'available',
      summary: 'Selected-system evidence is available as review context. Your plan still uses canonical planner data.',
      nextAction: 'Review the evidence detail before changing plan assumptions.',
      plannerBoundary: 'Planner truth remains canonical and separate from this report-only evidence.',
      caution,
    };
  }

  if (status === 'unavailable') {
    return {
      badgeLabel: 'Unavailable',
      badgeTone: 'unavailable',
      summary: 'No approved selected-system evidence is linked here. Continue planning with canonical data.',
      nextAction: 'Keep planning with canonical data or inspect another system for more context.',
      plannerBoundary: 'Planner truth remains canonical because no approved selected-system evidence is linked here.',
      caution,
    };
  }

  if (status === 'not_evaluated') {
    return {
      badgeLabel: 'Not evaluated',
      badgeTone: 'not_evaluated',
      summary: 'Evidence was not safely evaluated in this runtime. Continue with canonical planner data; no staging conclusion is available.',
      nextAction: 'Continue planning with canonical data and review the technical detail if runtime posture matters.',
      plannerBoundary: 'Planner truth remains canonical while the evidence boundary stays unevaluated.',
      caution,
    };
  }

  return {
    badgeLabel: 'Unknown',
    badgeTone: 'unknown',
    summary: 'Selected-system evidence has not been established. Continue with canonical planner data.',
    nextAction: 'Plan with canonical data and open the technical detail if you need provenance posture.',
    plannerBoundary: 'Planner truth remains canonical because selected-system evidence has not been established.',
    caution,
  };
}

function evidenceCautionText(options?: {
  freshnessStatus?: PlannerWarehouseEvidence['freshnessStatus'];
  manualReviewRequired?: boolean;
  boundedStagingStatus?: WarehouseBoundedStagingStatus;
}): string | undefined {
  if (options?.manualReviewRequired) {
    return 'Manual review remains required before treating this evidence as more than planning context.';
  }
  if (options?.freshnessStatus === 'stale') {
    return 'Evidence freshness is stale, so treat it as cautionary review context only.';
  }
  if (options?.boundedStagingStatus === 'available') {
    return 'Coverage remains bounded staging only, so it is not full system coverage or canonical truth.';
  }
  if (options?.boundedStagingStatus === 'unavailable') {
    return 'No approved bounded staging evidence is linked for this system in the current envelope.';
  }
  return undefined;
}
