import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { comparePredictionToObservations } from '@/lib/api';
import type {
  PredictionObservationCompareResponse,
  SimulateBuildResponse,
} from '@/types/api';
import { describeApiError } from '../observations/observationUtils';
import { ValidationComparisonList } from './ValidationComparisonList';
import { ValidationSummary } from './ValidationSummary';
import {
  ADVISORY_COPY,
  NO_PREVIEW_COPY,
  STALE_PREVIEW_COPY,
} from './validationLabels';
import { previewResultFingerprint } from './validationUtils';

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
 *   * No preview result → empty/instructional state. No compare call.
 *   * Preview result present → compare against persisted observed
 *     evidence using Mode A (`observed_facts` omitted). The query key
 *     includes the preview fingerprint so a fresh preview triggers a
 *     fresh comparison.
 *   * Stale preview → render a warning. The compare query still uses
 *     the *current* preview result; the user is informed to re-run
 *     Preview themselves. We never auto-run Simulation Preview here.
 *   * Refresh button → manual refetch of the compare query.
 */
export function ValidationPanel({
  systemId64,
  targetArchetype,
  previewResult,
  isPreviewResultStale = false,
}: ValidationPanelProps) {
  const predictionFingerprint = useMemo(
    () => previewResultFingerprint(previewResult),
    [previewResult],
  );

  // Stable query key — compares are tied to (system, archetype,
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
    // Cast through `unknown` because `SimulateBuildResponse` is a known
    // backend response shape but the compare endpoint accepts any JSON
    // object as `prediction`.
    queryFn: () =>
      comparePredictionToObservations({
        system_id64: systemId64,
        target_archetype: targetArchetype ?? null,
        prediction: previewResult as unknown as Record<string, unknown>,
      }),
    staleTime: 30 * 1000,
    retry: 1,
  });

  function refreshValidation() {
    if (!previewResult) return;
    // Force a fresh comparison fetch for the current preview
    // fingerprint. `refetch()` is sufficient — invalidating across
    // (system, *, *) keys would also force every cached comparison to
    // refetch, which is wasteful when only the active one matters here.
    // The Observed Evidence panel separately invalidates the
    // `observation-compare` namespace on create/update/delete so
    // evidence-driven changes still propagate.
    void compareQuery.refetch();
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
            onClick={refreshValidation}
            disabled={!previewResult || compareQuery.isFetching}
            className="rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] text-cyan hover:bg-cyan/20 disabled:cursor-not-allowed disabled:opacity-40"
            data-testid="validation-refresh-button"
          >
            {compareQuery.isFetching ? 'Refreshing…' : 'Refresh validation'}
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
