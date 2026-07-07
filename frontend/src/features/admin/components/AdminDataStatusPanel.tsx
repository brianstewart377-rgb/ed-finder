import type { AdminDataStatus } from '@/types/api';
import { Flag, Stat } from './AdminMetrics';
import { formatUnknown } from './adminFormat';

export function AdminDataStatusPanel({
  hasToken,
  status,
  loading,
  error,
}: {
  hasToken: boolean;
  status: AdminDataStatus | null;
  loading: boolean;
  error: string | null;
}) {
  if (!hasToken) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        Set an admin token to view read-only data status.
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
        {loading ? 'Loading data status...' : 'Data status has not loaded yet.'}
      </p>
    );
  }

  const stations = status.station_counts;
  const identities = status.identity_counts;
  const safety = status.safety_summary;
  const policy = status.policy_summary;

  return (
    <div className="space-y-3">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
        <Stat label="Total stations" value={formatUnknown(stations.total_station_rows)} />
        <Stat label="Unknown stations" value={formatUnknown(stations.unknown_station_rows)} highlight={stations.unknown_station_rows > 0} />
        <Stat label="Coriolis stations" value={formatUnknown(stations.coriolis_station_rows)} />
        <Stat label="Dodec stations" value={formatUnknown(stations.dodec_station_rows)} />
        <Stat label="Typed source rows" value={formatUnknown(stations.rows_with_station_type_source)} />
        <Stat label="Identity rows" value={formatUnknown(identities.total_identity_rows)} />
        <Stat label="Confirmed identities" value={formatUnknown(identities.confirmed_identity_rows)} />
        <Stat label="Identity conflicts" value={formatUnknown(identities.rows_with_conflict_reason)} highlight={identities.rows_with_conflict_reason > 0} />
        <Flag label="DB read-only" value={safety.db_read_only_confirmed} />
        <Flag label="Dodec supported" value={policy.dodec_supported} />
        <Flag label="Fleet carriers deferred" value={policy.fleet_carriers_remain_unknown} />
        <Flag label="Depot deferred" value={policy.construction_depots_remain_unknown} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <div className="panel-thin p-3 space-y-2">
          <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
            Remaining Unknown source evidence
          </div>
          {status.unknown_station_source_counts.length === 0 ? (
            <p className="text-[11px] text-green font-mono">No confirmed source station types remain Unknown.</p>
          ) : (
            <div className="space-y-1 font-mono text-[11px]">
              {status.unknown_station_source_counts.map((row) => (
                <div key={row.source_station_type ?? 'NULL'} className="flex justify-between gap-3">
                  <span className="text-silver-dk">{row.source_station_type ?? 'NULL'}</span>
                  <span className="text-silver tabular-nums">{row.rows.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel-thin p-3 space-y-2">
          <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
            Safety summary
          </div>
          <div className="grid sm:grid-cols-2 gap-2 font-mono text-[11px]">
            <Flag label="No DB writes" value={!safety.db_writes_performed} />
            <Flag label="No migrations" value={!safety.migrations_performed} />
            <Flag label="No type writes" value={!safety.station_type_writes_performed} />
            <Flag label="No canonical apply" value={!safety.canonical_apply_performed} />
          </div>
        </div>
      </div>

      {status.recent_station_type_updates.length > 0 && (
        <div className="panel-thin p-3 space-y-2">
          <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
            Recent station-type updates
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="text-silver-dk uppercase tracking-[0.12em]">
                <tr>
                  <th className="py-1 pr-3">Station</th>
                  <th className="py-1 pr-3">Type</th>
                  <th className="py-1 pr-3">Source</th>
                  <th className="py-1 pr-3">Updated</th>
                </tr>
              </thead>
              <tbody>
                {status.recent_station_type_updates.slice(0, 8).map((row) => (
                  <tr key={row.canonical_station_id} className="border-t border-border/60">
                    <td className="py-1 pr-3 text-silver">{row.canonical_station_name}</td>
                    <td className="py-1 pr-3 text-orange-lt">{row.station_type}</td>
                    <td className="py-1 pr-3 text-silver-dk">{row.station_type_source ?? '—'}</td>
                    <td className="py-1 pr-3 text-silver-dk">{row.station_type_updated_at ? new Date(row.station_type_updated_at).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-[10px] leading-snug text-silver-dk font-mono">
        Read-only DB status from <code className="text-orange-lt">/api/admin/data-status</code>.
        {loading && <span className="text-orange-lt ml-2">refreshing...</span>}
      </p>
    </div>
  );
}
