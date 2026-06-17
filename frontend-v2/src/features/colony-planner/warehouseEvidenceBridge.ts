import type {
  PlannerWarehouseEvidence,
  PlannerWarehouseEvidenceItem,
  ProvenanceCockpitResponse,
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
  };
}
