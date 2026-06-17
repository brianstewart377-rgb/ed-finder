import type {
  PlannerWarehouseEvidence,
  WarehouseEvidenceLabel,
  WarehousePlannerEvidenceFreshnessStatus,
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

const FRESHNESS_LABEL: Record<WarehousePlannerEvidenceFreshnessStatus, string> = {
  fresh: 'Fresh',
  stale: 'Stale',
  unknown: 'Unknown freshness',
};

const SOURCE_POSTURE_LABEL: Record<NonNullable<PlannerWarehouseEvidence['sourcePosture']>, string> = {
  dedicated_contract: 'Dedicated contract',
  provenance_bridge: 'Provenance fallback',
  unknown: 'Unknown source path',
};

export function WarehouseEvidenceCard({ evidence }: WarehouseEvidenceCardProps) {
  const isUnavailable =
    !evidence ||
    evidence.availability === 'unavailable' ||
    evidence.items.length === 0;
  const freshness = evidence?.freshnessStatus ?? 'unknown';
  const reviewStatus = evidence?.manualReviewRequired ? 'Manual review required' : 'Passive review only';
  const sourcePosture = evidence?.sourcePosture ?? 'unknown';
  const warnings = evidence?.warnings ?? [];

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

      <div data-testid="warehouse-evidence-metadata" className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-[10px] text-text-dim">
        <span
          data-testid={`warehouse-evidence-freshness-${freshness}`}
          className="px-1.5 py-0.5 rounded border border-border bg-bg4 uppercase tracking-wider"
        >
          {FRESHNESS_LABEL[freshness]}
        </span>
        <span
          data-testid={`warehouse-evidence-source-posture-${sourcePosture}`}
          className="px-1.5 py-0.5 rounded border border-border bg-bg4 uppercase tracking-wider"
        >
          {SOURCE_POSTURE_LABEL[sourcePosture]}
        </span>
        <span data-testid="warehouse-evidence-review-status" className="leading-snug">
          {reviewStatus}
        </span>
        {(evidence?.sourceName || evidence?.runKey) ? (
          <span data-testid="warehouse-evidence-source-run" className="leading-snug">
            Source run: {[evidence?.sourceName, evidence?.runKey].filter(Boolean).join(' · ')}
          </span>
        ) : null}
      </div>

      {isUnavailable ? (
        <div
          data-testid="warehouse-evidence-unavailable"
          className="flex items-center gap-2"
        >
          <SourceBadge source="unknown" />
          <span>No warehouse evidence artifact is available.</span>
        </div>
      ) : (
        <ul data-testid="warehouse-evidence-items" className="space-y-1.5">
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

      {warnings.length > 0 ? (
        <ul data-testid="warehouse-evidence-warnings" className="space-y-1 border-t border-border pt-2 text-[10px] text-text-dim">
          {warnings.slice(0, 2).map((warning, index) => (
            <li key={`${warning}-${index}`} data-testid="warehouse-evidence-warning">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
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
