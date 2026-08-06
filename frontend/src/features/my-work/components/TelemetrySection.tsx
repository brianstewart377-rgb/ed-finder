import { formatTimestamp } from '../myWorkWorkspaceUtils';
import { useJournalTelemetrySummary } from '../useJournalTelemetrySummary';

export function TelemetrySection({
  syncKey,
  isLoading,
  error,
  telemetry,
  onInspectSystem,
}: {
  syncKey: string;
  isLoading: boolean;
  error: string | null;
  telemetry: ReturnType<typeof useJournalTelemetrySummary>['data'] | null;
  onInspectSystem: (id64: number) => void;
}) {
  return (
    <section className="space-y-4" data-testid="my-work-telemetry">
      <div className="premium-subpanel border-cyan/30 bg-cyan/8 px-3 py-2 text-sm text-silver">
        My Work telemetry is sync-key scoped and read-only. It shows what your imported journal data observed; it does not claim canonical truth or live commander identity.
      </div>
      <div className="rounded border border-border/60 bg-bg2/35 px-3 py-2 font-mono text-[11px] text-silver-dk">
        Telemetry scope: <span className="text-cyan">{syncKey}</span>
      </div>
      {isLoading ? (
        <div className="premium-subpanel px-4 py-8 text-sm text-silver-dk">
          Loading telemetry summary...
        </div>
      ) : null}
      {error ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red">
          {error}
        </div>
      ) : null}
      {!isLoading && !error && telemetry ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Imports" value={telemetry.runs_count} detail={telemetry.last_imported_at ? `Last import ${formatTimestamp(telemetry.last_imported_at)}` : 'No imports yet'} />
            <MetricCard label="Observed systems" value={telemetry.systems_observed} detail="Distinct systems seen in your staged journal telemetry" />
            <MetricCard label="Body observations" value={telemetry.body_observation_count} detail="Scan and signal events captured from your journal imports" />
            <MetricCard label="Docked events" value={telemetry.docked_observation_count} detail="Station visit observations captured from your journal imports" />
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div className="premium-subpanel space-y-3 p-4">
              <div>
                <h2 className="font-display text-base tracking-[0.1em] text-text">Recently observed systems</h2>
                <p className="mt-1 text-sm text-silver-dk">
                  Recent systems found in your imported journal history. This is your personal reference and does not alter shared system data.
                </p>
              </div>
              {telemetry.recent_systems.length === 0 ? (
                <p className="text-sm text-silver-dk">No journal systems yet. Import journal files above to start building your personal history.</p>
              ) : (
                <ul className="space-y-2">
                  {telemetry.recent_systems.map((system) => (
                    <li key={system.system_id64} className="premium-toolbar flex flex-wrap items-center justify-between gap-3 rounded-2xl px-3 py-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-display text-sm tracking-[0.08em] text-text">{system.system_name}</div>
                        <div className="mt-1 text-sm text-silver-dk">
                          {system.event_count} event{system.event_count === 1 ? '' : 's'} · {system.event_types.join(', ')} · Last observed {formatTimestamp(system.last_observed_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => onInspectSystem(system.system_id64)}
                        className="btn-metal text-[11px] font-mono"
                      >
                        Inspect system
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-4">
              <div className="premium-subpanel space-y-3 p-4">
                <div>
                  <h2 className="font-display text-base tracking-[0.1em] text-text">Recent import runs</h2>
                  <p className="mt-1 text-sm text-silver-dk">
                    Bounded receipts for your recent sync-key journal imports.
                  </p>
                </div>
                {telemetry.recent_runs.length === 0 ? (
                  <p className="text-sm text-silver-dk">No recent runs yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {telemetry.recent_runs.map((run) => (
                      <li key={run.run_key} className="rounded border border-border/40 bg-bg1/35 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">{run.status}</span>
                          <span className="font-mono text-[11px] text-silver-dk">{run.run_key}</span>
                        </div>
                        <p className="mt-2 text-sm text-silver">
                          Staged {run.observations_staged} · Duplicates {run.duplicates_skipped}
                        </p>
                        <p className="mt-1 text-sm text-silver-dk">
                          {formatCompactEventCounts(run.event_counts)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="premium-subpanel space-y-3 p-4">
                <h2 className="font-display text-base tracking-[0.1em] text-text">Event mix</h2>
                <p className="text-sm text-silver-dk">
                  {formatCompactEventCounts(telemetry.event_counts)}
                </p>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="premium-subpanel p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mt-1 text-2xl text-text">{value.toLocaleString()}</div>
      <div className="mt-2 text-sm text-silver-dk">{detail}</div>
    </div>
  );
}

function formatCompactEventCounts(eventCounts: Record<string, number>): string {
  const entries = Object.entries(eventCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return 'No observed events recorded yet.';
  return entries.map(([eventType, count]) => `${eventType} ${count}`).join(' · ');
}
