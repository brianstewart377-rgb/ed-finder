import { formatTimestamp } from '@/lib/format';
import type { AdminCronJobState, AdminCronStatus } from '@/types/api';
import { Flag, Stat } from './AdminMetrics';

export function AdminCronStatusPanel({
  hasToken,
  status,
  loading,
  error,
}: {
  hasToken: boolean;
  status: AdminCronStatus | null;
  loading: boolean;
  error: string | null;
}) {
  if (!hasToken) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        Set an admin token to view scheduler and cron recency.
      </p>
    );
  }

  if (error) {
    return (
      <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
        {error}
      </div>
    );
  }

  if (!status) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        {loading ? 'Loading scheduler status...' : 'Scheduler status has not loaded yet.'}
      </p>
    );
  }

  const scheduled = status.scheduled_source_runs;
  const backlog = status.ratings_backlog;

  return (
    <div className="space-y-3" data-testid="admin-cron-status">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
        <Stat
          label="Last nightly"
          value={status.last_nightly_update === 'never' ? 'never' : formatMaybeTimestamp(status.last_nightly_update)}
          highlight={status.last_nightly_update === 'never'}
        />
        <Stat label="Scheduled runs (24h)" value={scheduled.runs_last_24h.toLocaleString()} />
        <Stat label="Scheduled failures (24h)" value={scheduled.failed_runs_last_24h.toLocaleString()} highlight={scheduled.failed_runs_last_24h > 0} />
        <Stat label="Dirty ratings backlog" value={backlog.dirty_systems.toLocaleString()} highlight={backlog.dirty_systems > 0} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <div className="panel-thin p-3 space-y-2">
          <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
            Durable admin jobs
          </div>
          <JobSummary label="Cluster rebuild" job={status.jobs.cluster_rebuild} />
          <JobSummary label="Ratings rebuild" job={status.jobs.ratings_rebuild} />
          <div className="grid sm:grid-cols-2 gap-2 pt-2 font-mono text-[11px]">
            <Flag label="Nightly recorded" value={status.last_nightly_update !== 'never'} />
            <Flag label="No dirty backlog" value={backlog.dirty_systems === 0} />
          </div>
        </div>

        <div className="panel-thin p-3 space-y-2">
          <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
            Scheduled source-run recency
          </div>
          <div className="font-mono text-[11px] text-silver-dk space-y-1">
            <div>Latest start: <span className="text-silver">{formatMaybeTimestamp(scheduled.latest_started_at)}</span></div>
            <div>Latest finish: <span className="text-silver">{formatMaybeTimestamp(scheduled.latest_finished_at)}</span></div>
            <div>Oldest dirty system update: <span className="text-silver">{formatMaybeTimestamp(backlog.oldest_dirty_updated_at)}</span></div>
            <div>Newest dirty system update: <span className="text-silver">{formatMaybeTimestamp(backlog.newest_dirty_updated_at)}</span></div>
          </div>
        </div>
      </div>

      <div className="panel-thin p-3 space-y-2">
        <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
          Recent scheduled sources
        </div>
        {scheduled.recent_sources.length === 0 ? (
          <p className="text-[11px] text-silver-dk font-mono">
            No scheduled source runs are recorded yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="text-silver-dk uppercase tracking-[0.12em]">
                <tr>
                  <th className="py-1 pr-3">Source</th>
                  <th className="py-1 pr-3">Status</th>
                  <th className="py-1 pr-3">Trigger</th>
                  <th className="py-1 pr-3">Started</th>
                  <th className="py-1 pr-3">Finished</th>
                  <th className="py-1 pr-3">Rows</th>
                </tr>
              </thead>
              <tbody>
                {scheduled.recent_sources.map((row, index) => (
                  <tr key={`${row.source_name ?? 'unknown'}-${row.domain ?? 'none'}-${index}`} className="border-t border-border/60">
                    <td className="py-1 pr-3 text-silver">{row.source_name ?? 'unknown source'}{row.domain ? ` (${row.domain})` : ''}</td>
                    <td className="py-1 pr-3 text-silver-dk">{row.status ?? 'unknown'}</td>
                    <td className="py-1 pr-3 text-silver-dk">{row.trigger_context ?? 'unknown'}</td>
                    <td className="py-1 pr-3 text-silver-dk">{formatMaybeTimestamp(row.started_at)}</td>
                    <td className="py-1 pr-3 text-silver-dk">{formatMaybeTimestamp(row.finished_at)}</td>
                    <td className="py-1 pr-3 text-silver-dk">{row.rows_read.toLocaleString()} read | {row.rows_staged.toLocaleString()} staged</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-[10px] leading-snug text-silver-dk font-mono">
        Read-only scheduler summary from <code className="text-orange-lt">/api/admin/cron-status</code>.
        {loading && <span className="text-orange-lt ml-2">refreshing...</span>}
      </p>
    </div>
  );
}

function JobSummary({
  label,
  job,
}: {
  label: string;
  job: AdminCronJobState | null;
}) {
  if (!job) {
    return (
      <div className="font-mono text-[11px] text-silver-dk">
        {label}: no persisted job history available yet.
      </div>
    );
  }

  return (
    <div className="rounded border border-border/60 bg-bg2/20 px-3 py-2 font-mono text-[11px] space-y-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-silver">{label}</span>
        <span className="text-orange-lt uppercase tracking-[0.12em]">{job.status}</span>
      </div>
      <div className="text-silver-dk">Started {formatMaybeTimestamp(job.start_time)}</div>
      <div className="text-silver-dk">Finished {formatMaybeTimestamp(job.end_time)}</div>
      {typeof job.dirty_before === 'number' ? (
        <div className="text-silver-dk">Dirty before: {job.dirty_before.toLocaleString()}</div>
      ) : null}
      {typeof job.cleared === 'number' ? (
        <div className="text-silver-dk">Cleared: {job.cleared.toLocaleString()}</div>
      ) : null}
      {job.error ? (
        <div className="text-red">{job.error}</div>
      ) : null}
    </div>
  );
}

function formatMaybeTimestamp(value: string | null | undefined): string {
  if (!value) return 'unknown';
  return formatTimestamp(value) ?? value;
}
