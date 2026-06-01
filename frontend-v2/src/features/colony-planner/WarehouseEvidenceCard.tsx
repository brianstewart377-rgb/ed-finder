import type {
  PlannerWarehouseEvidence,
  WarehouseEvidenceLabel,
  WarehouseEvidenceSource,
} from '@/types/api';

/**
 * Stage 18H — Warehouse-to-Planner Evidence Bridge (read-only).
 *
 * A compact, presentation-only card that surfaces carefully selected warehouse
 * / report-only evidence context inside the Colony Planner. It is EVIDENCE,
 * NOT TRUTH.
 *
 * Hard boundaries (see
 * `docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md`):
 *   - Read-only. No callbacks, no controls, no fetch, no mutation of planner
 *     state, Build Plans, roles, observed evidence, validation, scoring,
 *     Simulation Preview, optimiser output, or canonical data.
 *   - The planner always runs on canonical data; warehouse evidence is
 *     report-only and source-labelled.
 *   - When no evidence summary is supplied (the default today, because the
 *     Stage 18G artifact is admin-gated and aggregate-only with no per-system
 *     linkage), the card shows a safe unavailable/unknown state. Missing
 *     evidence stays unknown — it never means false / no evidence.
 */
export interface WarehouseEvidenceCardProps {
  /**
   * Optional read-only evidence summary. Omitted / `null` renders the safe
   * unavailable (unknown) state.
   */
  evidence?: PlannerWarehouseEvidence | null;
}

const SOURCE_LABEL: Record<WarehouseEvidenceSource, string> = {
  canonical:             'Canonical',
  observed:              'Observed',
  warehouse_report_only: 'Warehouse report-only',
  unknown:               'Unknown',
};

const FINDING_LABEL: Record<WarehouseEvidenceLabel, string> = {
  report_only:  'Report-only',
  needs_review: 'Needs review',
  verify:       'Verify',
  unresolved:   'Unresolved',
  stale:        'Stale',
  blocked:      'Blocked',
  unknown:      'Unknown',
};

export function WarehouseEvidenceCard({ evidence }: WarehouseEvidenceCardProps) {
  const isUnavailable =
    !evidence ||
    evidence.availability === 'unavailable' ||
    evidence.items.length === 0;

  return (
    <aside
      data-testid="planner-warehouse-evidence"
      aria-label="Warehouse evidence (report-only)"
      className="panel-thin p-3 font-mono text-[11px] text-silver-dk space-y-2"
    >
      <div className="flex items-center gap-2">
        <span className="font-display tracking-[0.14em] text-orange-lt text-xs">
          Warehouse evidence
        </span>
        <span
          data-testid="warehouse-evidence-report-only-tag"
          className="px-1.5 py-0.5 rounded border border-border bg-bg4 text-[9px] uppercase tracking-wider text-text-dim"
        >
          Report-only
        </span>
      </div>

      <p
        data-testid="warehouse-evidence-source-boundary"
        className="leading-snug text-text-dim"
      >
        Planner is using canonical data; warehouse evidence is report-only.
      </p>

      {isUnavailable ? (
        <div
          data-testid="warehouse-evidence-unavailable"
          className="flex items-center gap-2 border-t border-border pt-2"
        >
          <SourceBadge source="unknown" />
          <span>No warehouse evidence artifact is available.</span>
        </div>
      ) : (
        <ul data-testid="warehouse-evidence-items" className="space-y-1.5 border-t border-border pt-2">
          {evidence!.items.map((item, i) => (
            <li
              key={`${item.label}-${item.source}-${i}`}
              data-testid="warehouse-evidence-item"
              className="flex flex-wrap items-center gap-1.5"
            >
              <FindingBadge label={item.label} />
              <SourceBadge source={item.source} />
              <span className="leading-snug text-text">{item.summary}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function SourceBadge({ source }: { source: WarehouseEvidenceSource }) {
  return (
    <span
      data-testid={`warehouse-evidence-source-${source}`}
      className="px-1.5 py-0.5 rounded border border-border bg-bg4 text-[9px] uppercase tracking-wider text-silver-dk"
    >
      {SOURCE_LABEL[source]}
    </span>
  );
}

function FindingBadge({ label }: { label: WarehouseEvidenceLabel }) {
  return (
    <span
      data-testid={`warehouse-evidence-label-${label}`}
      className="px-1.5 py-0.5 rounded border border-border bg-bg4 text-[9px] uppercase tracking-wider text-orange-lt"
    >
      {FINDING_LABEL[label]}
    </span>
  );
}
