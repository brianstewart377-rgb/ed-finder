import { useMemo, useState } from 'react';
import type {
  ComparisonStatus,
  PredictionObservationComparison,
} from '@/types/api';
import { ValidationComparisonCard } from './ValidationComparisonCard';
import {
  COMPARISON_STATUSES,
  EMPTY_COMPARISONS_COPY,
  comparisonStatusLabel,
} from './validationLabels';
import { filterComparisonsByStatus } from './validationUtils';

interface ValidationComparisonListProps {
  comparisons: PredictionObservationComparison[];
}

/**
 * Renders the comparison list with a status filter. The filter is
 * intentionally narrow (status only); severity filtering is left for a
 * later refinement. The empty state stays neutral so users do not read
 * "no rows" as a final verdict on the prediction.
 */
export function ValidationComparisonList({ comparisons }: ValidationComparisonListProps) {
  const [statusFilter, setStatusFilter] = useState<ComparisonStatus | ''>('');

  const visible = useMemo(
    () => filterComparisonsByStatus(comparisons, statusFilter || null),
    [comparisons, statusFilter],
  );

  return (
    <section
      aria-label="Validation Comparisons"
      data-testid="validation-comparison-list"
      className="space-y-3"
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Filter by status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ComparisonStatus | '')}
            className="mt-1 block w-full rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
            data-testid="validation-status-filter"
          >
            <option value="">All statuses</option>
            {COMPARISON_STATUSES.map((value) => (
              <option key={value} value={value}>{comparisonStatusLabel(value)}</option>
            ))}
          </select>
        </label>
        {statusFilter && (
          <button
            type="button"
            onClick={() => setStatusFilter('')}
            className="rounded-chunk-sm border border-border bg-bg2 px-3 py-1.5 text-[11px] text-silver hover:border-orange/40 hover:text-orange"
            data-testid="validation-clear-status-filter"
          >
            Clear filter
          </button>
        )}
        <p
          className="ml-auto text-[10px] uppercase tracking-[0.14em] text-silver-dk"
          data-testid="validation-comparison-count"
        >
          Showing <span className="text-silver">{visible.length}</span> of{' '}
          <span className="text-silver">{comparisons.length}</span> rows
        </p>
      </div>

      {comparisons.length === 0 ? (
        <p
          className="rounded border border-border/60 bg-bg3/30 px-3 py-3 text-[11px] text-silver-dk"
          data-testid="validation-comparison-empty"
        >
          {EMPTY_COMPARISONS_COPY}
        </p>
      ) : visible.length === 0 ? (
        <p
          className="rounded border border-border/60 bg-bg3/30 px-3 py-3 text-[11px] text-silver-dk"
          data-testid="validation-comparison-filter-empty"
        >
          No rows match this status filter. Clear the filter to see all comparisons.
        </p>
      ) : (
        <div className="space-y-2">
          {visible.map((comparison) => (
            <ValidationComparisonCard
              key={comparison.comparison_id}
              comparison={comparison}
            />
          ))}
        </div>
      )}
    </section>
  );
}
