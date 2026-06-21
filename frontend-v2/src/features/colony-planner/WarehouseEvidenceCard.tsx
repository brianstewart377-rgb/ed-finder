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
import { EvidencePostureSummary } from '@/components/EvidencePostureSummary';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { evidenceEnvelopeStatusLabel, evidencePostureContent } from '@/lib/evidenceLanguage';

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
  available: 'Bounded staging evidence',
  unavailable: 'Bounded staging unavailable',
  not_evaluated: 'Bounded staging not evaluated in this runtime',
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
  bounded_staging: 'Bounded staging evidence',
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
  const posture = evidencePostureContent(evidenceEnvelope.status, {
    freshnessStatus: freshness,
    manualReviewRequired: evidence?.manualReviewRequired,
    boundedStagingStatus: boundedStaging.status,
  });
  const boundedStagingLimit = boundedStaging.rowLimit != null
    ? `Limited to approved Stage 19BB row-cap evidence (limit ${boundedStaging.rowLimit}).`
    : 'Limited to approved Stage 19BB row-cap evidence.';
  const sourcePostureLabel = SOURCE_POSTURE_LABEL[sourcePosture];

  return (
    <aside
      data-testid="planner-warehouse-evidence"
      aria-label="Planner evidence (report-only)"
      className="rounded-chunk-lg border border-border bg-bg2 p-4 font-mono text-[11px] text-silver-dk shadow-[0_16px_40px_-28px_rgba(0,0,0,0.75)] space-y-4"
    >
      <EvidencePostureSummary
        title="Planner evidence"
        statusLabel={posture.badgeLabel}
        statusTone={posture.badgeTone}
        summary={posture.summary}
        nextAction={posture.nextAction}
        plannerBoundary={posture.plannerBoundary}
        caution={posture.caution}
        testIdPrefix="warehouse-evidence"
        highlights={(
          <>
            {evidenceEnvelope.reportOnly ? (
              <SemanticStatusBadge
                label="Report-only review context"
                tone="report_only"
                testId="warehouse-evidence-report-only-tag"
              />
            ) : null}
            {evidenceEnvelope.selectedSystemOnly ? (
              <SemanticStatusBadge
                label="Selected-system only"
                tone="observed"
              />
            ) : null}
            {evidenceEnvelope.claimsCanonicalTruth === false ? (
              <SemanticStatusBadge
                label="Planner truth stays canonical"
                tone="canonical"
              />
            ) : null}
            {evidenceEnvelope.claimsFullCoverage === false ? (
              <SemanticStatusBadge
                label="Bounded or incomplete coverage"
                tone="caution"
              />
            ) : null}
            <SemanticStatusBadge
              label={sourcePostureLabel}
              tone={sourcePosture === 'dedicated_contract' ? 'canonical' : sourcePosture === 'provenance_bridge' ? 'caution' : 'unknown'}
              testId={`warehouse-evidence-source-posture-${sourcePosture}`}
            />
          </>
        )}
        disclosureLabel="technical evidence detail"
        disclosureContent={(
          <>
            <section className="space-y-2">
              <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver">
                Technical posture
              </h3>
              <div
                data-testid="warehouse-evidence-metadata"
                className="flex flex-wrap items-center gap-2"
              >
                <SemanticStatusBadge
                  label={FRESHNESS_LABEL[freshness]}
                  tone={freshness === 'fresh' ? 'available' : freshness === 'stale' ? 'stale' : freshness === 'not_evaluated' ? 'not_evaluated' : 'unknown'}
                  testId={`warehouse-evidence-freshness-${freshness}`}
                />
                <SemanticStatusBadge
                  label={EVIDENCE_STATUS_LABEL[evidenceEnvelope.status]}
                  tone={posture.badgeTone}
                  testId={`warehouse-evidence-envelope-status-${evidenceEnvelope.status}`}
                />
                <SemanticStatusBadge
                  label={reviewStatus}
                  tone={evidence?.manualReviewRequired ? 'needs_review' : 'canonical'}
                  testId="warehouse-evidence-review-status"
                />
                <SemanticStatusBadge
                  label={BOUNDED_STAGING_LABEL[boundedStaging.status]}
                  tone={boundedStaging.status === 'available' ? 'available' : boundedStaging.status === 'unavailable' ? 'unavailable' : 'not_evaluated'}
                  testId={`warehouse-evidence-bounded-staging-${boundedStaging.status}`}
                />
              </div>
              {(evidence?.sourceName || evidence?.runKey) ? (
                <p data-testid="warehouse-evidence-source-run">
                  Source run: {[evidence?.sourceName, evidence?.runKey].filter(Boolean).join(' · ')}
                </p>
              ) : null}
            </section>

            <section
              data-testid="warehouse-evidence-envelope-summary"
              className="space-y-2"
            >
              <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver">
                Envelope truth boundary
              </h3>
              <p>{evidenceEnvelope.summary}</p>
              <p data-testid="warehouse-evidence-status-detail">
                {statusDetailCopy(evidenceEnvelope.status, boundedStaging.status)}
              </p>
              <p data-testid="warehouse-evidence-source-classes">
                Source classes: {evidenceEnvelope.sourceClasses.map((value) => SOURCE_CLASS_LABEL[value]).join(' · ')}
              </p>
              <div
                data-testid="warehouse-evidence-source-class-list"
                className="flex flex-wrap items-center gap-2"
              >
                {evidenceEnvelope.sourceClasses.map((value) => (
                  <SemanticStatusBadge
                    key={value}
                    label={SOURCE_CLASS_LABEL[value]}
                    tone={value === 'canonical' ? 'canonical' : value === 'observed_facts' ? 'observed' : value === 'unavailable' ? 'unavailable' : 'report_only'}
                  />
                ))}
              </div>
              <p data-testid="warehouse-evidence-semantics">
                Semantics: {evidenceEnvelope.semantics.map((value) => SEMANTIC_LABEL[value]).join(' · ')}
              </p>
              <div
                data-testid="warehouse-evidence-semantic-list"
                className="flex flex-wrap items-center gap-2"
              >
                {evidenceEnvelope.semantics.map((value) => (
                  <SemanticStatusBadge
                    key={value}
                    label={SEMANTIC_LABEL[value]}
                    tone={value === 'canonical_truth' ? 'canonical' : value === 'observed_report' ? 'observed' : value === 'not_full_coverage' ? 'caution' : 'report_only'}
                  />
                ))}
              </div>
            </section>

            <section
              data-testid="warehouse-evidence-bounded-staging-summary"
              className="space-y-2"
            >
              <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver">
                Bounded staging detail
              </h3>
              {boundedStaging.summary ? (
                <p>{boundedStaging.summary}</p>
              ) : null}
              <p>
                Stage 19BB provenance:{' '}
                {[
                  boundedStaging.sourceBatchLabel,
                  boundedStaging.sourceRunKey,
                  boundedStaging.rowLimit != null ? `limit ${boundedStaging.rowLimit}` : null,
                  boundedStaging.matchedRowCount != null ? `${boundedStaging.matchedRowCount} matched row(s)` : null,
                ].filter(Boolean).join(' · ') || 'not evaluated'}
              </p>
              {boundedStaging.status === 'available' ? (
                <div
                  data-testid="warehouse-evidence-bounded-staging-guidance"
                  className="space-y-1"
                >
                  <p>Bounded staging evidence</p>
                  <p>Report-only review context</p>
                  <p>Not canonical truth</p>
                  <p>Not full EDSM coverage</p>
                  <p>{boundedStagingLimit}</p>
                </div>
              ) : null}
            </section>
          </>
        )}
      />

      {isUnavailable ? (
        <div
          data-testid="warehouse-evidence-unavailable"
          className="rounded-chunk-lg border border-border bg-bg3/30 p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <SourceBadge source="unknown" />
            <SemanticStatusBadge
              label={evidenceEnvelopeStatusLabel(evidenceEnvelope.status)}
              tone={posture.badgeTone}
            />
          </div>
          <p className="mt-2 leading-relaxed text-silver">
            {unavailableCopy(evidenceEnvelope.status, boundedStaging.status)}
          </p>
        </div>
      ) : (
        <section className="space-y-2">
          <h3 className="font-display text-sm tracking-[0.12em] text-orange-lt">
            Current report-only findings
          </h3>
          <ul data-testid="warehouse-evidence-items" className="space-y-2">
          {evidence!.items.map((item, i) => (
            <li
              key={`${item.label}-${item.source}-${i}`}
              data-testid="warehouse-evidence-item"
              className="rounded-chunk-lg border border-border bg-bg3/30 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <FindingBadge label={item.label} />
                <SourceBadge source={item.source} />
              </div>
              <p className="mt-2 leading-relaxed text-silver">{item.summary}</p>
            </li>
          ))}
          </ul>
        </section>
      )}

      {warnings.length > 0 ? (
        <ul
          data-testid="warehouse-evidence-warnings"
          className="space-y-2 rounded-chunk-lg border border-gold/35 bg-gold/10 p-3 text-[11px] text-gold"
        >
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

function statusDetailCopy(
  status: WarehouseEvidenceEnvelopeStatus,
  _boundedStagingStatus: WarehouseBoundedStagingStatus,
) {
  if (status === 'available') {
    return 'Available. Selected-system evidence is present as read-only review context only.';
  }
  if (status === 'unknown') {
    return 'Unknown. Selected-system evidence has not been established.';
  }
  if (status === 'unavailable') {
    return 'Unavailable. No approved bounded staging evidence is linked to this selected system.';
  }
  if (status === 'not_evaluated') {
    return 'Not evaluated in this runtime. The staging boundary was not safely queryable for this request.';
  }
  return 'Unknown. Selected-system evidence has not been established.';
}

function unavailableCopy(
  status: WarehouseEvidenceEnvelopeStatus,
  _boundedStagingStatus: WarehouseBoundedStagingStatus,
) {
  if (status === 'available') {
    return 'Available. Selected-system evidence is present as read-only review context only.';
  }
  if (status === 'unknown') {
    return 'Unknown. Selected-system evidence has not been established.';
  }
  if (status === 'unavailable') {
    return 'Unavailable. No approved bounded staging evidence is linked to this selected system.';
  }
  if (status === 'not_evaluated') {
    return 'Not evaluated in this runtime. The staging boundary was not safely queryable for this request.';
  }
  return 'Unknown. Selected-system evidence has not been established.';
}

function SourceBadge({ source }: { source: WarehouseEvidenceSource }) {
  return (
    <SemanticStatusBadge
      testId={`warehouse-evidence-source-${source}`}
      label={SOURCE_LABEL[source]}
      tone={source === 'canonical' ? 'canonical' : source === 'observed' ? 'observed' : source === 'warehouse_report_only' ? 'report_only' : 'unknown'}
    />
  );
}

function FindingBadge({ label }: { label: WarehouseEvidenceLabel }) {
  return (
    <SemanticStatusBadge
      testId={`warehouse-evidence-label-${label}`}
      label={FINDING_LABEL[label]}
      tone={findingTone(label)}
    />
  );
}

function findingTone(label: WarehouseEvidenceLabel) {
  if (label === 'needs_review' || label === 'verify') return 'needs_review';
  if (label === 'stale') return 'stale';
  if (label === 'blocked') return 'blocked';
  if (label === 'unknown' || label === 'unresolved') return 'unknown';
  return 'report_only';
}
