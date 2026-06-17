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

  if (warehouse.state === 'stale') {
    items.push({
      label: 'stale',
      source: 'warehouse_report_only',
      summary: `${warehouse.stale_records ?? 'Unknown'} warehouse records need freshness review.`,
    });
  }

  items.push({
    label: 'report_only',
    source: 'warehouse_report_only',
    summary: `Canonical writes planned: ${warehouse.canonical_writes_planned}.`,
  });

  if (response.guardrails.db_writes_authorized === false) {
    items.push({
      label: 'blocked',
      source: 'warehouse_report_only',
      summary: 'DB writes remain unauthorized in this checkpoint.',
    });
  }

  return {
    availability: warehouse.state === 'unknown' ? 'unavailable' : 'report_only',
    reportOnly: true,
    items,
    freshnessStatus: warehouse.state === 'stale' ? 'stale' : warehouse.state === 'unknown' ? 'unknown' : 'fresh',
    evaluatedAt: null,
    manualReviewRequired: response.evidence_panels.planner.manual_review_required,
    sourceName: response.evidence_panels.source_run.source_name ?? null,
    runKey: response.provenance_summary.latest_source_run_key ?? null,
    sourcePosture: 'provenance_bridge',
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
    warnings: response.warnings,
  };
}
