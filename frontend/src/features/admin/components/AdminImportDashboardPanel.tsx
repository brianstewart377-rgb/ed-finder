import { useMemo, useState } from 'react';
import { formatTimestamp } from '@/lib/format';
import type { OperatorSafetyGateSummary, OperatorSourceRunSummary } from '@/types/api';
import { Stat } from './AdminMetrics';

export function AdminImportDashboardPanel({
  hasToken,
  loading,
  error,
  safetyGates,
  sourceRuns,
  onOpenOperator,
}: {
  hasToken: boolean;
  loading: boolean;
  error: string | null;
  safetyGates: OperatorSafetyGateSummary | null;
  sourceRuns: OperatorSourceRunSummary[];
  onOpenOperator?: (sourceRunKey?: string) => void;
}) {
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const availableSources = useMemo(
    () => Array.from(new Set(sourceRuns.map((run) => run.source_name?.trim()).filter((value): value is string => Boolean(value)))).sort(),
    [sourceRuns],
  );
  const visibleRuns = useMemo(
    () => sourceRuns.filter((run) => sourceFilter === 'all' || (run.source_name ?? '') === sourceFilter),
    [sourceFilter, sourceRuns],
  );
  const runningCount = sourceRuns.filter((run) => (run.status ?? '').toLowerCase() === 'running').length;
  const failedCount = sourceRuns.filter((run) => {
    const status = (run.status ?? '').toLowerCase();
    return status === 'failed' || status === 'error';
  }).length;
  const stagedRows = sourceRuns.reduce((sum, run) => sum + (run.rows_staged ?? 0), 0);
  const journalRuns = sourceRuns.filter((run) => (run.source_name ?? '').toLowerCase() === 'frontier_journal');
  const latestRun = sourceRuns[0] ?? null;

  if (!hasToken) {
    return (
      <div className="rounded-chunk-sm border border-border bg-bg3/30 p-4 text-sm text-silver-dk">
        Set an admin token to view import runs, safety posture, and recent ingest health.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-chunk-sm border border-border bg-bg3/30 p-4 text-sm text-silver-dk">
        Loading import dashboard...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-chunk-sm border border-red/45 bg-red/10 p-4 text-sm text-red">
        Failed to load import dashboard. {error}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="admin-import-dashboard">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Recent runs" value={String(sourceRuns.length)} />
        <Stat label="Running" value={String(runningCount)} highlight={runningCount > 0} />
        <Stat label="Failed" value={String(failedCount)} highlight={failedCount > 0} />
        <Stat label="Rows staged" value={stagedRows.toLocaleString()} />
        <Stat label="Journal runs" value={String(journalRuns.length)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.1fr_1.4fr]">
        <section className="rounded-chunk-sm border border-border bg-bg3/30 p-4">
          <div className="font-display text-orange text-xs uppercase tracking-[0.18em]">
            Safety posture
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-mono">
            <StatusPill
              label={safetyGates?.safe_to_proceed ? 'Safe to proceed' : 'Review blockers'}
              tone={safetyGates?.safe_to_proceed ? 'green' : 'orange'}
            />
            <StatusPill
              label={safetyGates?.no_running_source_runs ? 'No active runs' : 'Active run present'}
              tone={safetyGates?.no_running_source_runs ? 'green' : 'orange'}
            />
            <StatusPill
              label={safetyGates?.latest_artifacts_present ? 'Artifacts present' : 'Artifacts missing'}
              tone={safetyGates?.latest_artifacts_present ? 'green' : 'orange'}
            />
          </div>
          {safetyGates?.latest_source_run_key ? (
            <p className="mt-3 text-sm text-silver">
              Latest tracked run: <span className="font-mono text-silver-dk">{safetyGates.latest_source_run_key}</span>
            </p>
          ) : null}
          {safetyGates?.blockers?.length ? (
            <ul className="mt-3 space-y-1 text-sm text-orange">
              {safetyGates.blockers.map((blocker) => (
                <li key={blocker}>- {blocker}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-silver-dk">
              No current blockers reported by the read-only operator safety summary.
            </p>
          )}
        </section>

        <section className="rounded-chunk-sm border border-border bg-bg3/30 p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="font-display text-orange text-xs uppercase tracking-[0.18em]">
              Recent imports
            </div>
            <div className="flex items-center gap-2">
              {latestRun ? (
                <span className="text-[11px] font-mono text-silver-dk">
                  Latest: {latestRun.source_name ?? 'unknown source'}
                </span>
              ) : null}
              {onOpenOperator ? (
                <button
                  type="button"
                  onClick={() => onOpenOperator()}
                  className="btn-metal px-2 py-1 text-[11px]"
                  data-testid="admin-open-operator"
                >
                  Open Operator
                </button>
              ) : null}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="text-[11px] font-mono text-silver-dk" htmlFor="admin-import-source-filter">
              Source
            </label>
            <select
              id="admin-import-source-filter"
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
              className="rounded border border-border bg-bg2 px-2 py-1 text-[11px] text-silver"
              data-testid="admin-import-source-filter"
            >
              <option value="all">All sources</option>
              {availableSources.map((source) => (
                <option key={source} value={source}>{source}</option>
              ))}
            </select>
            <span className="text-[11px] font-mono text-silver-dk">
              Showing {visibleRuns.length} of {sourceRuns.length}
            </span>
          </div>
          {visibleRuns.length === 0 ? (
            <p className="mt-3 text-sm text-silver-dk">
              No source runs match the current filter.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {visibleRuns.slice(0, 8).map((run) => (
                <article
                  key={run.source_run_key}
                  className="rounded border border-border/80 bg-bg2/30 px-3 py-2"
                  data-testid={`admin-import-run-${run.source_run_key}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] text-silver">{run.source_name ?? 'unknown source'}</span>
                    <StatusPill label={run.status ?? 'unknown'} tone={toneForStatus(run.status)} />
                    {run.domain ? (
                      <span className="text-[11px] text-silver-dk">{run.domain}</span>
                    ) : null}
                  </div>
                  <div className="mt-1 text-sm text-silver-dk">
                    Read {formatCount(run.rows_read)} | Staged {formatCount(run.rows_staged)} | Skipped {formatCount(run.rows_skipped)}
                  </div>
                  <div className="mt-1 text-sm text-silver-dk">
                    Started {formatMaybeTimestamp(run.started_at)} | Finished {formatMaybeTimestamp(run.finished_at)}
                  </div>
                  {run.error_summary ? (
                    <div className="mt-1 text-sm text-orange">
                      {run.error_summary}
                    </div>
                  ) : null}
                  {onOpenOperator ? (
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={() => onOpenOperator(run.source_run_key)}
                        className="btn-metal px-2 py-1 text-[11px]"
                        data-testid={`admin-open-operator-${run.source_run_key}`}
                      >
                        Open in Operator detail
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function formatMaybeTimestamp(value: string | null | undefined): string {
  return formatTimestamp(value) ?? 'unknown';
}

function formatCount(value: number | null | undefined): string {
  return typeof value === 'number' ? value.toLocaleString() : '0';
}

function toneForStatus(status: string | null | undefined): 'green' | 'orange' | 'red' | 'silver' {
  const normalized = (status ?? '').trim().toLowerCase();
  if (normalized === 'succeeded' || normalized === 'completed') return 'green';
  if (normalized === 'running' || normalized === 'queued') return 'orange';
  if (normalized === 'failed' || normalized === 'error') return 'red';
  return 'silver';
}

function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: 'green' | 'orange' | 'red' | 'silver';
}) {
  const className = {
    green: 'border-green/35 bg-green/10 text-green',
    orange: 'border-orange/35 bg-orange/10 text-orange',
    red: 'border-red/35 bg-red/10 text-red',
    silver: 'border-border bg-bg3/40 text-silver-dk',
  }[tone];

  return (
    <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.14em] ${className}`}>
      {label}
    </span>
  );
}
