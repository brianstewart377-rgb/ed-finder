import { useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { comparePredictionToObservations, reviewPredictionValidation } from '@/lib/api';
import type {
  PredictionObservationCompareResponse,
  SimulateBuildResponse,
  ValidationReviewResponse,
} from '@/types/api';
import { describeApiError } from '../observations/observationUtils';
import { ValidationComparisonList } from './ValidationComparisonList';
import { ValidationReviewPanel } from './ValidationReviewPanel';
import { ValidationSummary } from './ValidationSummary';
import {
  ADVISORY_COPY,
  NO_PREVIEW_COPY,
  STALE_PREVIEW_COPY,
  VALIDATION_REVIEW_REMINDERS,
} from '@ed-finder/planner-core/validation/validationLabels';
import { previewResultFingerprint, validationInputProjection } from '@ed-finder/planner-core/validation/validationUtils';

interface ValidationPanelProps {
  systemId64: number;
  targetArchetype: string | null;
  previewResult: SimulateBuildResponse | null;
  isPreviewResultStale?: boolean;
}

/**
 * Stage 6D Validation panel.
 *
 * Renders the Stage 6C `/api/observations/compare` response inside the
 * Colony Planner. The panel is intentionally passive:
 *
 *   * It never calls `simulateBuild` or `fetchOptimiserCandidates`.
 *   * It never mutates persisted observed evidence.
 *   * It does not alter Simulation Preview scoring, optimiser ranking,
 *     candidate generation, or in-game state.
 *
 * Behaviour summary:
 *   * No preview result -> empty/instructional state. No compare call.
 *   * Preview result present -> compare against persisted observed
 *     evidence using Mode A (`observed_facts` omitted). The query key
 *     includes the preview fingerprint so a fresh preview triggers a
 *     fresh comparison.
 *   * Stale preview -> render a warning. The compare query still uses
 *     the *current* preview result; the user is informed to re-run
 *     Preview themselves. We never auto-run Simulation Preview here.
 *   * Review waits for compare and receives its pre-computed result, so
 *     the backend does not run the comparison engine twice.
 *   * Refresh button -> refetch compare, then review that fresh result.
 */
export function ValidationPanel({
  systemId64,
  targetArchetype,
  previewResult,
  isPreviewResultStale = false,
}: ValidationPanelProps) {
  const queryClient = useQueryClient();
  const validationPrediction = useMemo(
    () => previewResult ? validationInputProjection(previewResult) : null,
    [previewResult],
  );
  const predictionFingerprint = useMemo(
    () => previewResultFingerprint(previewResult),
    [previewResult],
  );

  // Stable query key: compares are tied to (system, archetype,
  // preview-fingerprint). React Query caches per key, so the same
  // preview reuses the cached compare response on remount.
  const queryKey = useMemo(
    () => [
      'observation-compare',
      systemId64,
      targetArchetype ?? null,
      predictionFingerprint,
    ],
    [systemId64, targetArchetype, predictionFingerprint],
  );

  const enabled = previewResult !== null;

  const compareQuery = useQuery<PredictionObservationCompareResponse, Error>({
    queryKey,
    enabled,
    // Cache identity and request input deliberately share this projection.
    queryFn: () =>
      comparePredictionToObservations({
        system_id64: systemId64,
        target_archetype: targetArchetype ?? null,
        prediction: validationPrediction!,
      }),
    staleTime: 30 * 1000,
    retry: 1,
  });

  const comparisonFingerprint = useMemo(
    () => compareQuery.data ? JSON.stringify(compareQuery.data) : null,
    [compareQuery.data],
  );

  const reviewQueryKey = useMemo(
    () => [
      'observation-review',
      systemId64,
      targetArchetype ?? null,
      predictionFingerprint,
      comparisonFingerprint,
    ],
    [systemId64, targetArchetype, predictionFingerprint, comparisonFingerprint],
  );

  const reviewQuery = useQuery<ValidationReviewResponse, Error>({
    queryKey: reviewQueryKey,
    enabled: enabled && compareQuery.isSuccess && compareQuery.data !== undefined,
    queryFn: () => {
      const comparisonResult = queryClient.getQueryData<PredictionObservationCompareResponse>(queryKey);
      if (!comparisonResult) {
        throw new Error('Comparison result is unavailable for validation review.');
      }
      return reviewPredictionValidation({
        system_id64: systemId64,
        target_archetype: targetArchetype ?? null,
        comparison_result: comparisonResult,
      });
    },
    staleTime: 30 * 1000,
    retry: 1,
  });

  const isRefreshingValidation = compareQuery.isFetching || reviewQuery.isFetching;

  async function refreshValidation() {
    if (!previewResult) return;
    // Review is deliberately sequenced after compare. Its queryFn reads
    // the newly cached comparison result, avoiding a second comparison
    // pass on the review endpoint and avoiding review of stale evidence.
    const refreshedComparison = await compareQuery.refetch();
    if (
      refreshedComparison.data
      && JSON.stringify(refreshedComparison.data) === comparisonFingerprint
    ) {
      // A byte-identical comparison keeps the same review cache key, so
      // explicitly refresh that existing entry. Changed comparisons get
      // a new key and automatically start their own review query.
      await reviewQuery.refetch();
    }
  }

  return (
    <section
      aria-label="Validation"
      data-testid="validation-panel"
      className="rounded-chunk-lg border border-cyan/20 bg-bg1/55 p-4"
    >
      <header className="mb-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-cyan text-sm font-bold tracking-[0.18em] uppercase">
            Validation
          </h3>
          <button
            type="button"
            onClick={() => void refreshValidation()}
            disabled={!previewResult || isRefreshingValidation}
            className="rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:opacity-40"
            data-testid="validation-refresh-button"
          >
            {isRefreshingValidation ? 'Refreshing...' : 'Refresh validation'}
          </button>
        </div>
        <p
          className="mt-1 rounded border border-cyan/30 bg-cyan/5 px-2 py-1 text-[10px] text-cyan font-mono leading-snug"
          role="note"
          aria-label="Validation advisory notice"
          data-testid="validation-advisory-copy"
        >
          {ADVISORY_COPY}
        </p>
        <ul
          className="mt-2 grid gap-1 rounded border border-border/60 bg-bg3/30 px-3 py-2 font-mono text-[10px] leading-snug text-silver-dk sm:grid-cols-2"
          data-testid="validation-review-reminders"
        >
          {VALIDATION_REVIEW_REMINDERS.map((reminder) => (
            <li key={reminder}>{reminder}</li>
          ))}
        </ul>
      </header>

      {isPreviewResultStale && previewResult && (
        <div
          role="alert"
          data-testid="validation-stale-warning"
          className="mb-3 rounded border border-orange/40 bg-orange/10 px-3 py-2 font-mono text-[11px] text-orange leading-snug"
        >
          {STALE_PREVIEW_COPY}
        </div>
      )}

      {!previewResult && (
        <div
          data-testid="validation-no-preview"
          className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-[11px] text-silver-dk leading-snug"
        >
          {NO_PREVIEW_COPY}
        </div>
      )}

      {previewResult && compareQuery.isLoading && (
        <div
          data-testid="validation-loading"
          className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-[11px] text-silver-dk"
        >
          Comparing prediction with observed evidence&hellip;
        </div>
      )}

      {previewResult && compareQuery.isError && (
        <div
          role="alert"
          data-testid="validation-error"
          className="rounded border border-red/40 bg-red/10 px-3 py-2 font-mono text-[11px] text-red"
        >
          <div>Validation failed to load: {describeApiError(compareQuery.error)}</div>
          <button
            type="button"
            onClick={() => void compareQuery.refetch()}
            className="mt-2 rounded-chunk-sm border border-red/50 bg-red/15 px-3 py-1 text-[11px] font-bold text-red hover:bg-red/25"
            data-testid="validation-retry-button"
          >
            Retry
          </button>
        </div>
      )}

      {previewResult && compareQuery.isSuccess && compareQuery.data && (
        <div className="space-y-3">
          <ValidationSummary summary={compareQuery.data.summary} />
          {reviewQuery.isLoading && (
            <div
              data-testid="validation-review-loading"
              className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-[11px] text-silver-dk"
            >
              Building review guidance&hellip;
            </div>
          )}
          {reviewQuery.isError && (
            <div
              role="alert"
              data-testid="validation-review-error"
              className="rounded border border-orange/40 bg-orange/10 px-3 py-2 font-mono text-[11px] text-orange"
            >
              Review guidance failed to load: {describeApiError(reviewQuery.error)}
            </div>
          )}
          {reviewQuery.isSuccess && reviewQuery.data && (
            <ValidationReviewPanel review={reviewQuery.data} />
          )}
          {(compareQuery.data.warnings?.length ?? 0) > 0 && (
            <ul
              data-testid="validation-warnings"
              className="rounded border border-orange/30 bg-orange/5 px-3 py-2 font-mono text-[11px] text-orange"
            >
              {compareQuery.data.warnings.map((warning, idx) => (
                <li key={`warning-${idx}`}>{warning}</li>
              ))}
            </ul>
          )}
          {(compareQuery.data.assumptions?.length ?? 0) > 0 && (
            <ul
              data-testid="validation-assumptions"
              className="rounded border border-border/60 bg-bg3/30 px-3 py-2 font-mono text-[11px] text-silver-dk"
            >
              {compareQuery.data.assumptions.map((assumption, idx) => (
                <li key={`assumption-${idx}`}>{assumption}</li>
              ))}
            </ul>
          )}
          <ValidationComparisonList comparisons={compareQuery.data.comparisons} />
        </div>
      )}
    </section>
  );
}
