import type { UseAdmin } from '../useAdmin';
import { ActionCard } from './AdminActionCard';
import { ActionToast } from './AdminToasts';

export function AdminActionsPanel({ admin }: { admin: UseAdmin }) {
  return (
    <section className="panel p-5 space-y-3">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        8. Actions & operations
      </h3>

      <ActionToast state={admin.actionState} onDismiss={admin.resetActionState} />

      <div className="grid sm:grid-cols-3 gap-3">
        <ActionCard
          title="Rebuild ratings"
          blurb="Recompute every system's per-economy scores. Cheap on preview (~40 systems), background pipeline in prod."
          confirmText="Rebuild ratings now?"
          disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
          busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'rebuildRatings'}
          onClick={admin.rebuildRatings}
          testid="admin-rebuild-ratings"
        />
        <ActionCard
          title="Rebuild clusters"
          blurb="Re-run the dirty-anchor cluster builder in the background. Rate-limited to 1/minute."
          confirmText="Trigger a cluster rebuild now?"
          disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
          busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'rebuildClusters'}
          onClick={admin.rebuildClusters}
          testid="admin-rebuild-clusters"
        />
        <ActionCard
          title="Clear cache"
          blurb="Flush Redis + expired api_cache rows. Cheap; safe to retry."
          confirmText="Flush all cached responses?"
          disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
          busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'clearCache'}
          onClick={admin.clearCache}
          testid="admin-clear-cache"
        />
      </div>

      <div className="pt-2">
        <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em] mb-3">
          Approved read-only operations
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <ActionCard
            title="Telemetry hot-log snapshot"
            blurb="Run the retention posture snapshot against the configured database. Read-only. Useful for checking telemetry growth pressure."
            confirmText="Run the telemetry hot-log snapshot now?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'telemetryHotLogSnapshot'}
            onClick={admin.runTelemetryHotLogSnapshot}
            testid="admin-telemetry-hot-log-snapshot"
          />
          <ActionCard
            title="Data invariants"
            blurb="Run the production-safe trust and lifecycle invariant checks. Read-only. Useful for quick health validation from the UI."
            confirmText="Run the production-safe data invariants check now?"
            disabled={!admin.hasToken || admin.actionState.kind === 'busy'}
            busy={admin.actionState.kind === 'busy' && admin.actionState.what === 'dataInvariants'}
            onClick={admin.runDataInvariants}
            testid="admin-data-invariants"
          />
        </div>
      </div>

      {admin.hasToken && admin.lastOperationResult ? (
        <div className="panel-thin p-3 space-y-2" data-testid="admin-operation-output">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
              Latest operation output
            </span>
            <span className="font-mono text-[10px] text-silver-dk">
              {admin.lastOperationResult.what} · {admin.lastOperationResult.status} · job #{admin.lastOperationResult.jobRunId}
            </span>
            {typeof admin.lastOperationResult.exitCode === 'number' ? (
              <span className="font-mono text-[10px] text-silver-dk">
                exit {admin.lastOperationResult.exitCode}
              </span>
            ) : null}
            <button
              type="button"
              onClick={admin.clearLastOperationResult}
              className="ml-auto text-[10px] font-mono text-silver-dk hover:text-silver"
            >
              Dismiss
            </button>
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded border border-border/60 bg-bg2/20 p-3 font-mono text-[11px] text-silver">
            {admin.lastOperationResult.outputText}
          </pre>
        </div>
      ) : null}

      <div className="panel-thin p-3 space-y-3" data-testid="admin-operation-history">
        <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
          Recent persisted operation history
        </div>

        {!admin.hasToken ? (
          <p className="text-[10px] text-silver-dk font-mono">
            Set an admin token to view persisted operation history and captured script output.
          </p>
        ) : admin.operationHistoryLoading ? (
          <p className="text-[11px] text-silver-dk font-mono">Loading operation history…</p>
        ) : admin.operationHistoryError ? (
          <p className="text-[11px] text-red font-mono">{admin.operationHistoryError}</p>
        ) : admin.operationHistory.length === 0 ? (
          <p className="text-[11px] text-silver-dk font-mono">No persisted admin operation runs recorded yet.</p>
        ) : (
          <div className="space-y-3">
            {admin.operationHistory.map((entry) => (
              <div
                key={entry.job_run_id}
                className="rounded border border-border/60 bg-bg2/15 p-3 space-y-2"
                data-testid={`admin-operation-history-${entry.job_run_id}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-orange text-[11px] tracking-[0.14em]">
                    {entry.operation_key ?? entry.job_key}
                  </span>
                  <span className="font-mono text-[10px] text-silver-dk">
                    job #{entry.job_run_id} · {entry.status}
                  </span>
                  {typeof entry.exit_code === 'number' ? (
                    <span className="font-mono text-[10px] text-silver-dk">exit {entry.exit_code}</span>
                  ) : null}
                  {entry.script_name ? (
                    <span className="font-mono text-[10px] text-silver-dk">{entry.script_name}</span>
                  ) : null}
                </div>
                <div className="font-mono text-[10px] text-silver-dk">
                  started {entry.started_at ?? 'unknown'}{entry.finished_at ? ` · finished ${entry.finished_at}` : ''}
                </div>
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded border border-border/60 bg-bg2/20 p-3 font-mono text-[11px] text-silver">
                  {entry.output_text ?? entry.error_text ?? '(no output captured)'}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {!admin.hasToken && (
        <p className="text-[10px] text-silver-dk font-mono">
          Set a token in section 1 to enable actions. Preview default token: <code className="text-orange-lt">local-dev-admin-token</code>
        </p>
      )}
    </section>
  );
}
