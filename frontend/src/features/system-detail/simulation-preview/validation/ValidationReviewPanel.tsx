import type { ValidationReviewResponse } from '@/types/api';
import {
  comparisonSeverityLabel,
  confidenceImpactLabel,
  REVIEW_ADVISORY_COPY,
  reviewAreaLabel,
  reviewStatusLabel,
} from './validationLabels';

interface ValidationReviewPanelProps {
  review: ValidationReviewResponse;
}

export function ValidationReviewPanel({ review }: ValidationReviewPanelProps) {
  const summary = review.summary;
  const primaryAreas = summary.primary_review_areas.length > 0
    ? summary.primary_review_areas.map(reviewAreaLabel).join(', ')
    : 'None';

  return (
    <section
      data-testid="validation-review-panel"
      aria-label="Review guidance"
      className="rounded border border-cyan/30 bg-cyan/5 px-3 py-3 font-mono text-[11px] text-silver-dk"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[11px] font-bold uppercase tracking-[0.16em] text-cyan">
          Review guidance
        </h4>
        <span
          data-testid="validation-review-status"
          className="rounded border border-cyan/30 bg-bg2/60 px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan"
        >
          {reviewStatusLabel(summary.overall_review_status)}
        </span>
      </div>

      <p
        role="note"
        data-testid="validation-review-advisory-copy"
        className="mb-2 rounded border border-border/60 bg-bg3/30 px-2 py-1 text-[10px] text-silver-dk"
      >
        {REVIEW_ADVISORY_COPY}
      </p>

      <p
        data-testid="validation-review-summary-text"
        className="text-[11px] leading-snug text-silver"
      >
        {summary.summary}
      </p>

      <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
        <ReviewStat label="Evidence strength" value={summary.evidence_strength} testid="validation-review-evidence-strength" />
        <ReviewStat label="Highest severity" value={comparisonSeverityLabel(summary.highest_severity)} testid="validation-review-highest-severity" />
        <ReviewStat label="Confidence impact" value={confidenceImpactLabel(summary.confidence_impact)} testid="validation-review-confidence-impact" />
        <ReviewStat label="Primary areas" value={primaryAreas} testid="validation-review-primary-areas" />
      </dl>

      {review.signals.length > 0 && (
        <ul
          data-testid="validation-review-signals"
          className="mt-3 space-y-2"
        >
          {review.signals.map((signal) => (
            <li
              key={signal.signal_id}
              data-testid="validation-review-signal"
              className="rounded border border-border/60 bg-bg3/30 px-3 py-2"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="text-[11px] font-bold text-silver">{signal.title}</div>
                <div className="flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.12em]">
                  <span className="text-cyan">{reviewAreaLabel(signal.area)}</span>
                  <span className="text-silver-dk">{reviewStatusLabel(signal.status)}</span>
                </div>
              </div>
              <p className="mt-1 text-[11px] leading-snug text-silver-dk">{signal.message}</p>
              {signal.recommended_action && (
                <p className="mt-1 text-[11px] leading-snug text-silver">
                  {signal.recommended_action}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReviewStat({ label, value, testid }: { label: string; value: string | number; testid: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">{label}</dt>
      <dd className="text-right text-silver" data-testid={testid}>{value}</dd>
    </div>
  );
}
