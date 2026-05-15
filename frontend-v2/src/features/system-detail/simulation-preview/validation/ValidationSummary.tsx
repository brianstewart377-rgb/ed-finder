import type { PredictionObservationComparisonSummary } from '@/types/api';
import {
  comparisonStatusLabel,
  confidenceImpactLabel,
  overallStatusLabel,
} from './validationLabels';

interface ValidationSummaryProps {
  summary: PredictionObservationComparisonSummary;
}

/**
 * Renders the Stage 6C top-level summary (overall status, confidence
 * impact, per-bucket counts, and the human-readable summary string).
 *
 * Wording is conservative on purpose: the summary describes what the
 * engine measured; it never asserts that the prediction is correct or
 * incorrect. "Contradicted" rows are referred to with the user-facing
 * label "Needs review" via `comparisonStatusLabel`.
 */
export function ValidationSummary({ summary }: ValidationSummaryProps) {
  return (
    <div
      data-testid="validation-summary"
      className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-[11px] text-silver-dk"
    >
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <div>
          <span className="uppercase tracking-[0.14em] text-silver-dk">Overall</span>
          <span
            className="ml-2 text-silver"
            data-testid="validation-summary-overall-status"
          >
            {overallStatusLabel(summary.status)}
          </span>
        </div>
        <div>
          <span className="uppercase tracking-[0.14em] text-silver-dk">Confidence impact</span>
          <span
            className="ml-2 text-silver"
            data-testid="validation-summary-confidence-impact"
          >
            {confidenceImpactLabel(summary.confidence_impact)}
          </span>
        </div>
      </div>

      <p
        className="mt-2 text-[11px] text-silver-dk leading-snug"
        data-testid="validation-summary-text"
      >
        {summary.summary}
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 lg:grid-cols-5">
        <SummaryStat label="Observed facts" value={summary.observed_facts_count} testid="validation-summary-observed-facts" />
        <SummaryStat label="Compared" value={summary.compared_predictions_count} testid="validation-summary-compared" />
        <SummaryStat label={comparisonStatusLabel('confirmed')} value={summary.confirmed_count} testid="validation-summary-confirmed" />
        <SummaryStat label={comparisonStatusLabel('contradicted')} value={summary.contradicted_count} testid="validation-summary-contradicted" />
        <SummaryStat label={comparisonStatusLabel('observed_only')} value={summary.observed_only_count} testid="validation-summary-observed-only" />
        <SummaryStat label={comparisonStatusLabel('predicted_only')} value={summary.predicted_only_count} testid="validation-summary-predicted-only" />
        <SummaryStat label={comparisonStatusLabel('unknown')} value={summary.unknown_count} testid="validation-summary-unknown" />
        <SummaryStat label={comparisonStatusLabel('unverified')} value={summary.unverified_count} testid="validation-summary-unverified" />
      </dl>
    </div>
  );
}

function SummaryStat({ label, value, testid }: { label: string; value: number; testid: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">{label}</dt>
      <dd className="text-silver" data-testid={testid}>{value}</dd>
    </div>
  );
}
