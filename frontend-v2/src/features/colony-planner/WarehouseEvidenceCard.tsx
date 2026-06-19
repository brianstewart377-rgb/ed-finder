import type {
  PlannerWarehouseBoundedStaging,
  PlannerWarehouseEvidence,
  WarehouseEvidenceEnvelopeStatus,
  WarehouseEvidenceLabel,
  WarehouseEvidenceSemantic,
  WarehouseEvidenceSourceClass,
  WarehouseBoundedStagingStatus,
  WarehousePlannerEvidenceFreshnessStatus,
  WarehouseEvidenceSource,
} from '@/types/api';

/**
 * Stage 18H — Warehouse-to-Planner Evidence Bridge (read-only).
 *
 * A compact, presentation-only card that surfaces carefully selected
 * source-labelled planner evidence context inside the Colony Planner. It is
 * EVIDENCE, NOT TRUTH.
 *
 * Hard boundaries (see
 * `docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md`):
 *   - Read-only. No callbacks, no controls, no fetch, no mutation of planner
 *     state, Build Plans, roles, observed evidence, validation, scoring,
 *     Simulation Preview, optimiser output, or canonical data.
 *   - The planner always runs on canonical data; this evidence panel is
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
  not_evaluated: 'Not evaluated',
};

const SOURCE_POSTURE_LABEL: Record<NonNullable<PlannerWarehouseEvidence['sourcePosture']>, string> = {
  dedicated_contract: 'Dedicated contract',
  provenance_bridge: 'Provenance fallback',
  unknown: 'Unknown source path',
};

const BOUNDED_STAGING_LABEL: Record<WarehouseBoundedStagingStatus, string> = {
  available: 'Bounded staging available',
  unavailable: 'Bounded staging unavailable',
  not_evaluated: 'Bounded staging not evaluated',
};

const EVIDENCE_STATUS_LABEL: Record<WarehouseEvidenceEnvelopeStatus, string> = {
  available: 'Evidence available',
  unavailable: 'Evidence unavailable',
  not_evaluated: 'Evidence not evaluated',
  unknown: 'Evidence unknown',
};

const SOURCE_CLASS_LABEL: Record<WarehouseEvidenceSourceClass, string> = {
  canonical: 'Canonical evidence',
  observed_facts: 'Observed facts',
  bounded_staging: 'Bounded staging',
  derived_report: 'Derived report',
  unavailable: 'Unavailable',
};

const SEMANTIC_LABEL: Record<WarehouseEvidenceSemantic, string> = {
  canonical_truth: 'Canonical truth remains separate',
  observed_report: 'Observed report',
  bounded_staging_evidence: 'Bounded staging evidence',
  report_only_review_context: 'Report-only review context',
  not_full_coverage: 'Not full EDSM coverage',
};

export function WarehouseEvidenceCard({ evidence }: WarehouseEvidenceCardProps) {
  const isUnavailable =
    !evidence ||
    evidence.availability === 'unavailable' ||
    evidence.items.length === 0;
  const freshness = evidence?.freshnessStatus ?? 'unknown';
  const reviewStatus = evidence?.manualReviewRequired ? 'Manual review required' : 'Passive review only';
  const sourcePosture = evidence?.sourcePosture ?? 'unknown';
  const evidenceEnvelope = evidence?.evidenceEnvelope ?? {
    status: 'unknown' as const,
    sourceClasses: ['unavailable'] as const,
    semantics: ['report_only_review_context', 'not_full_coverage'] as const,
    reportOnly: true as const,
    selectedSystemOnly: true as const,
    plannerTruthSourceClass: 'canonical' as const,
    claimsCanonicalTruth: false as const,
    claimsFullCoverage: false as const,
    summary: 'Selected-system evidence remains unknown in this runtime. Source classes: no linked selected-system evidence.',
  };
  const boundedStaging: PlannerWarehouseBoundedStaging = evidence?.boundedStaging ?? {
    status: 'not_evaluated',
    reportOnly: true,
    boundedStagingOnly: true,
  };
  const warnings = evidence?.warnings ?? [];

  return (
    <aside
      data-testid="planner-warehouse-evidence"
      aria-label="Planner evidence (report-only)"
      className="panel-thin p-3 font-mono text-[11px] text-silver-dk space-y-2"
    >
      <div className="flex items-center gap-2">
        <span className="font-display tracking-[0.14em] text-orange-lt text-xs">
          Planner evidence
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
        Planner is using canonical data; this evidence panel is report-only.
      </p>

      <div data-testid="warehouse-evidence-metadata" className="flex flex-wrap items-center gap-2 border-t border-border pt-2 text-[10px] text-text-dim">
        <span
          data-testid={`warehouse-evidence-freshness-${freshness}`}
          className="px-1.5 py-0.5 rounded border border-border bg-bg4 uppercase tracking-wider"
        >
          {FRESHNESS_LABEL[freshness]}
        </span>
        <span
          data-testid={`warehouse-evidence-envelope-status-${evidenceEnvelope.status}`}
          className="px-1.5 py-0.5 rounded border border-border bg-bg4 uppercase tracking-wider"
        >
          {EVIDENCE_STATUS_LABEL[evidenceEnvelope.status]}
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
        {boundedStaging ? (
          <span
            data-testid={`warehouse-evidence-bounded-staging-${boundedStaging.status}`}
            className="leading-snug"
          >
            {BOUNDED_STAGING_LABEL[boundedStaging.status]}
          </span>
        ) : null}
      </div>

      {boundedStaging ? (
        <div
          data-testid="warehouse-evidence-bounded-staging-summary"
          className="border-t border-border pt-2 text-[10px] text-text-dim space-y-1"
        >
          {boundedStaging.summary ? (
            <p className="leading-snug">{boundedStaging.summary}</p>
          ) : null}
          <p className="leading-snug">
            Stage 19BB provenance:{' '}
            {[
              boundedStaging.sourceBatchLabel,
              boundedStaging.sourceRunKey,
              boundedStaging.rowLimit != null ? `limit ${boundedStaging.rowLimit}` : null,
              boundedStaging.matchedRowCount != null ? `${boundedStaging.matchedRowCount} matched row(s)` : null,
            ].filter(Boolean).join(' · ') || 'not evaluated'}
          </p>
        </div>
      ) : null}

      <div
        data-testid="warehouse-evidence-envelope-summary"
        className="border-t border-border pt-2 text-[10px] text-text-dim space-y-1"
      >
        <p className="leading-snug">{evidenceEnvelope.summary}</p>
        <p data-testid="warehouse-evidence-source-classes" className="leading-snug">
          Source classes: {evidenceEnvelope.sourceClasses.map((value) => SOURCE_CLASS_LABEL[value]).join(' · ')}
        </p>
        <p data-testid="warehouse-evidence-semantics" className="leading-snug">
          Semantics: {evidenceEnvelope.semantics.map((value) => SEMANTIC_LABEL[value]).join(' · ')}
        </p>
      </div>

      {isUnavailable ? (
        <div
          data-testid="warehouse-evidence-unavailable"
          className="flex items-center gap-2"
        >
          <SourceBadge source="unknown" />
          <span>No per-system planner evidence is available.</span>
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
