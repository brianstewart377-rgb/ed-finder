import type { PredictionObservationComparison } from '@/types/api';
import {
  OBSERVED_ONLY_COPY,
  PREDICTED_ONLY_COPY,
  comparisonSeverityLabel,
  comparisonStatusLabel,
} from './validationLabels';
import {
  validationMismatchCategory,
  validationMismatchCategoryClassName,
  validationMismatchCategoryCopy,
} from './validationReviewCategoryUtils';
import { formatComparisonValue } from './validationUtils';

interface ValidationComparisonCardProps {
  comparison: PredictionObservationComparison;
}

/**
 * Renders a single comparison row.
 *
 * Conservative wording rules (enforced by tests):
 *   * "contradicted" → labelled **Needs review**, never "wrong".
 *   * "predicted_only" → "Predicted, but no matching observation has
 *     been recorded yet."
 *   * "observed_only" → "Observed evidence exists, but the current
 *     prediction has no matching item."
 */
export function ValidationComparisonCard({ comparison }: ValidationComparisonCardProps) {
  const statusLabel = comparisonStatusLabel(comparison.status);
  const severityLabel = comparisonSeverityLabel(comparison.severity);
  const conservativeNote = conservativeStatusNote(comparison.status);
  const mismatchCategory = validationMismatchCategory(comparison);
  const mismatchCategoryCopy = validationMismatchCategoryCopy(mismatchCategory);

  return (
    <article
      data-testid="validation-comparison-card"
      data-status={comparison.status}
      className="rounded border border-border/60 bg-bg2/40 p-3 font-mono text-[11px] text-silver-dk"
    >
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className="rounded border border-cyan/30 bg-cyan/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-cyan"
          data-testid="validation-card-status"
        >
          {statusLabel}
        </span>
        <span
          className="rounded border border-border bg-bg3 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-silver-dk"
          data-testid="validation-card-severity"
        >
          Severity: <span className="text-silver">{severityLabel}</span>
        </span>
        <span
          className={[
            'rounded border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]',
            validationMismatchCategoryClassName(mismatchCategory),
          ].join(' ')}
          data-testid="validation-card-review-category"
        >
          {mismatchCategoryCopy.label}
        </span>
        <span className="text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Confidence:{' '}
          <span className="text-silver" data-testid="validation-card-confidence">
            {comparison.confidence}
          </span>
        </span>
      </header>

      <div className="grid gap-1 sm:grid-cols-[auto_1fr] sm:items-baseline sm:gap-x-3">
        <span className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">Area</span>
        <span className="text-silver" data-testid="validation-card-area">{comparison.area}</span>

        <span className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">Subject</span>
        <span className="text-silver" data-testid="validation-card-subject">
          <span data-testid="validation-card-subject-type">{comparison.subject_type}</span>
          {comparison.subject_id ? (
            <>
              {' · '}
              <span data-testid="validation-card-subject-id">{comparison.subject_id}</span>
            </>
          ) : null}
        </span>

        <span className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">Predicted</span>
        <span className="text-silver" data-testid="validation-card-predicted-value">
          {formatComparisonValue(comparison.predicted_value)}
        </span>

        <span className="text-[10px] uppercase tracking-[0.12em] text-silver-dk">Observed</span>
        <span className="text-silver" data-testid="validation-card-observed-value">
          {formatComparisonValue(comparison.observed_value)}
        </span>
      </div>

      <p
        className="mt-2 text-[11px] text-silver leading-snug"
        data-testid="validation-card-review-category-note"
      >
        {mismatchCategoryCopy.description}
      </p>

      {conservativeNote && (
        <p
          className="mt-2 text-[11px] text-silver-dk leading-snug"
          data-testid="validation-card-conservative-note"
        >
          {conservativeNote}
        </p>
      )}

      {comparison.reason && (
        <p
          className="mt-2 text-[11px] text-silver-dk leading-snug"
          data-testid="validation-card-reason"
        >
          {comparison.reason}
        </p>
      )}

      {comparison.recommended_action && (
        <p
          className="mt-1 rounded border border-orange/25 bg-orange/5 px-2 py-1 text-[11px] text-orange leading-snug"
          data-testid="validation-card-recommended-action"
        >
          Recommended action: {comparison.recommended_action}
        </p>
      )}

      <ValidationEvidenceList comparisonId={comparison.comparison_id} evidence={comparison.evidence} />
    </article>
  );
}

function conservativeStatusNote(status: string): string | null {
  if (status === 'predicted_only') return PREDICTED_ONLY_COPY;
  if (status === 'observed_only') return OBSERVED_ONLY_COPY;
  return null;
}

function ValidationEvidenceList({
  comparisonId,
  evidence,
}: {
  comparisonId: string;
  evidence: PredictionObservationComparison['evidence'];
}) {
  const count = evidence?.length ?? 0;
  return (
    <details
      className="mt-2 rounded border border-border/40 bg-bg3/30 px-2 py-1"
      data-testid="validation-card-evidence"
    >
      <summary
        className="cursor-pointer text-[10px] uppercase tracking-[0.14em] text-silver-dk"
        data-testid="validation-card-evidence-summary"
      >
        Evidence{' '}
        <span className="text-silver" data-testid="validation-card-evidence-count">
          ({count})
        </span>
      </summary>
      {count === 0 ? (
        <p
          className="mt-1 text-[11px] text-silver-dk"
          data-testid="validation-card-evidence-empty"
        >
          No observed evidence linked to this comparison.
        </p>
      ) : (
        <ul className="mt-1 space-y-1">
          {evidence.map((match) => (
            <li
              key={`${comparisonId}-${match.observation_id}`}
              data-testid="validation-card-evidence-item"
              className="rounded border border-border/40 bg-bg2/40 px-2 py-1"
            >
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] uppercase tracking-[0.12em] text-silver-dk">
                <span>
                  Obs:{' '}
                  <span className="text-silver" data-testid="validation-evidence-observation-id">
                    {match.observation_id}
                  </span>
                </span>
                <span>
                  Type:{' '}
                  <span className="text-silver" data-testid="validation-evidence-fact-type">
                    {match.fact_type}
                  </span>
                </span>
                <span>
                  Status:{' '}
                  <span className="text-silver" data-testid="validation-evidence-status">
                    {match.status}
                  </span>
                </span>
                <span>
                  Confidence:{' '}
                  <span className="text-silver" data-testid="validation-evidence-confidence">
                    {match.confidence}
                  </span>
                </span>
              </div>
              {(match.observed_value !== undefined && match.observed_value !== null) && (
                <div className="mt-0.5 text-[11px] text-silver-dk">
                  Observed value:{' '}
                  <span className="text-silver" data-testid="validation-evidence-observed-value">
                    {formatComparisonValue(match.observed_value)}
                  </span>
                </div>
              )}
              {(match.expected_value !== undefined && match.expected_value !== null) && (
                <div className="mt-0.5 text-[11px] text-silver-dk">
                  Expected value:{' '}
                  <span className="text-silver" data-testid="validation-evidence-expected-value">
                    {formatComparisonValue(match.expected_value)}
                  </span>
                </div>
              )}
              {match.notes && (
                <div
                  className="mt-0.5 text-[11px] text-silver-dk leading-snug"
                  data-testid="validation-evidence-notes"
                >
                  Notes: {match.notes}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
