import type {
  PlannerWarehouseEvidence,
  PlannerWarehouseEvidenceItem,
  ProvenanceCockpitResponse,
  WarehousePlannerEvidenceContract,
} from '@/types/api';


export function toWarehouseEvidenceFromProvenance(
  response: ProvenanceCockpitResponse | undefined,
): PlannerWarehouseEvidence | null {
  if (!response) return null;

  const items: PlannerWarehouseEvidenceItem[] = [];
  const { warehouse } = response.evidence_panels;

  if (warehouse.state === 'available') {
    items.push({
      label: 'report_only',
      source: 'warehouse_report_only',
      summary: 'Selected-system warehouse evidence is only available as provenance fallback review context.',
    });
  }

  if (warehouse.state === 'stale') {
    items.push({
      label: 'stale',
      source: 'warehouse_report_only',
      summary: `${warehouse.stale_records ?? 'Unknown'} warehouse records need freshness review.`,
    });
  }

  return {
    availability: warehouse.state === 'unknown' ? 'unavailable' : 'report_only',
    reportOnly: true,
    items,
    freshnessStatus:
      warehouse.state === 'stale'
        ? 'stale'
        : warehouse.state === 'available'
          ? 'not_evaluated'
          : 'unknown',
    evaluatedAt: null,
    manualReviewRequired: response.evidence_panels.planner.manual_review_required,
    sourceName: response.evidence_panels.source_run.source_name ?? null,
    runKey: response.provenance_summary.latest_source_run_key ?? null,
    sourcePosture: 'provenance_bridge',
    evidenceEnvelope: {
      status: warehouse.state === 'unknown' ? 'unknown' : 'available',
      sourceClasses: warehouse.state === 'unknown' ? ['unavailable'] : ['derived_report'],
      semantics: ['report_only_review_context', 'not_full_coverage'],
      reportOnly: true,
      selectedSystemOnly: true,
      plannerTruthSourceClass: 'canonical',
      claimsCanonicalTruth: false,
      claimsFullCoverage: false,
      summary: warehouse.state === 'unknown'
        ? 'Selected-system evidence remains unknown in this runtime. Source classes: no linked selected-system evidence.'
        : 'Selected-system evidence is available in this read-only planner envelope. Source classes: derived report evidence.',
    },
    boundedStaging: {
      status: 'not_evaluated',
      reportOnly: true,
      boundedStagingOnly: true,
    },
    warnings: response.warnings,
  };
}

export function toWarehouseEvidenceFromContract(
  response: WarehousePlannerEvidenceContract | undefined,
): PlannerWarehouseEvidence | null {
  if (!response) return null;

  const items: PlannerWarehouseEvidenceItem[] = response.evidence_summary.items.map((item) => ({
    label: item.label,
    source: item.source,
    summary: item.summary,
  }));
  const boundedStaging = response.bounded_staging ?? {
    status: 'not_evaluated' as const,
    report_only: true as const,
    bounded_staging_only: true as const,
    available_row_limits: [],
  };
  const evidenceEnvelope = response.evidence_envelope ?? {
    status: response.evidence_summary.availability === 'unavailable' ? 'unknown' as const : 'available' as const,
    source_classes: response.evidence_summary.items.length === 0 ? ['unavailable'] as const : ['derived_report'] as const,
    semantics: ['report_only_review_context', 'not_full_coverage'] as const,
    report_only: true as const,
    selected_system_only: true as const,
    planner_truth_source_class: 'canonical' as const,
    claims_canonical_truth: false as const,
    claims_full_coverage: false as const,
    summary: response.evidence_summary.availability === 'unavailable'
      ? 'Selected-system evidence remains unknown in this runtime. Source classes: no linked selected-system evidence.'
      : 'Selected-system evidence is available in this read-only planner envelope. Source classes: derived report evidence.',
  };

  return {
    availability: response.evidence_summary.availability,
    reportOnly: response.evidence_summary.report_only,
    items,
    freshnessStatus: response.freshness.status,
    evaluatedAt: response.freshness.evaluated_at ?? null,
    manualReviewRequired: response.evidence_summary.manual_review_required,
    sourceName: response.source_run.source_name ?? null,
    runKey: response.source_run.run_key ?? null,
    sourcePosture: 'dedicated_contract',
    evidenceEnvelope: {
      status: evidenceEnvelope.status,
      sourceClasses: [...evidenceEnvelope.source_classes],
      semantics: [...evidenceEnvelope.semantics],
      reportOnly: evidenceEnvelope.report_only,
      selectedSystemOnly: evidenceEnvelope.selected_system_only,
      plannerTruthSourceClass: evidenceEnvelope.planner_truth_source_class,
      claimsCanonicalTruth: evidenceEnvelope.claims_canonical_truth,
      claimsFullCoverage: evidenceEnvelope.claims_full_coverage,
      summary: evidenceEnvelope.summary,
    },
    boundedStaging: {
      status: boundedStaging.status,
      reportOnly: boundedStaging.report_only,
      boundedStagingOnly: boundedStaging.bounded_staging_only,
      sourceName: boundedStaging.source_name ?? null,
      sourceBatchLabel: boundedStaging.source_batch_label ?? null,
      sourceSha256: boundedStaging.source_sha256 ?? null,
      sourceRunKey: boundedStaging.source_run_key ?? null,
      bridgeKey: boundedStaging.bridge_key ?? null,
      rowLimit: boundedStaging.row_limit ?? null,
      availableRowLimits: boundedStaging.available_row_limits,
      matchedRowCount: boundedStaging.matched_row_count ?? null,
      latestSourceUpdatedAt: boundedStaging.latest_source_updated_at ?? null,
      summary: boundedStaging.summary ?? null,
    },
    warnings: response.warnings,
  };
}
