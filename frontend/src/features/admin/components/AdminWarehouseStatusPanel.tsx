import type { EnrichmentWarehouseStatus } from '@/types/api';
import { Stat } from './AdminMetrics';
import { formatAge, formatBool, formatDistribution, formatUnknown } from './adminFormat';

export function AdminWarehouseStatusPanel({
  hasToken,
  status,
  loading,
  error,
}: {
  hasToken: boolean;
  status: EnrichmentWarehouseStatus | null;
  loading: boolean;
  error: string | null;
}) {
  if (!hasToken) {
    return (
      <p className="text-[11px] text-silver-dk font-mono">
        Set an admin token to view read-only warehouse status.
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
        {loading ? 'Loading warehouse status...' : 'Warehouse status has not loaded yet.'}
      </p>
    );
  }

  if (!status.available) {
    return (
      <div className="space-y-2">
        <div className="panel-thin border-gold/45 p-3 font-mono text-xs text-gold" style={{ background: 'rgba(250,204,21,0.08)' }}>
          {status.message}
        </div>
        <p className="text-[10px] leading-snug text-silver-dk font-mono">
          The API reads a configured warehouse JSON artifact. It does not generate reports, invoke Docker, call live APIs, or query the warehouse from this page.
        </p>
      </div>
    );
  }

  const health = status.evidence_health;
  const safety = status.canonical_safety;
  const coverage = status.source_coverage;
  const run = status.latest_reconciliation_run;
  const snapshot = status.latest_snapshot_load;

  return (
    <div className="space-y-3">
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
        <Stat label="Warehouse status" value={status.state} highlight={status.state === 'unsafe' || status.state === 'blocked'} />
        <Stat label="Canonical untouched" value={formatBool(safety?.canonical_tables_untouched)} highlight={safety?.canonical_tables_untouched === false} />
        <Stat label="Canonical writes" value={formatUnknown(safety?.canonical_writes_planned)} highlight={(safety?.canonical_writes_planned ?? 0) > 0} />
        <Stat label="Report mode" value={safety?.report_only === true ? 'report-only' : formatBool(safety?.report_only)} highlight={safety?.report_only === false} />
        <Stat label="Station evidence systems" value={formatUnknown(coverage?.systems_with_station_evidence)} />
        <Stat label="Missing station evidence" value={formatUnknown(coverage?.systems_missing_station_evidence)} highlight={(coverage?.systems_missing_station_evidence ?? 0) > 0} />
        <Stat label="Trusted ring bodies" value={formatUnknown(coverage?.trusted_ring_evidence_bodies)} />
        <Stat label="Unknown ring bodies" value={formatUnknown(coverage?.unknown_ring_evidence_bodies)} highlight={(coverage?.unknown_ring_evidence_bodies ?? 0) > 0} />
        <Stat label="Unresolved stations" value={formatUnknown(health?.unresolved_stations)} highlight={(health?.unresolved_stations ?? 0) > 0} />
        <Stat label="Blocked conflicts" value={formatUnknown(health?.blocked_conflicts)} highlight={(health?.blocked_conflicts ?? 0) > 0} />
        <Stat label="Risky conflicts" value={formatUnknown(health?.risky_conflicts)} highlight={(health?.risky_conflicts ?? 0) > 0} />
        <Stat label="Stale/undated sources" value={formatUnknown(health?.stale_or_undated_source_records)} highlight={(health?.stale_or_undated_source_records ?? 0) > 0} />
        <Stat label="Skipped/malformed rows" value={formatUnknown(health?.malformed_or_skipped_rows)} highlight={(health?.malformed_or_skipped_rows ?? 0) > 0} />
        <Stat label="Duplicate records" value={formatUnknown(health?.duplicate_source_records)} highlight={(health?.duplicate_source_records ?? 0) > 0} />
        <Stat label="Identity conflicts" value={formatUnknown(health?.source_identity_conflicts)} highlight={(health?.source_identity_conflicts ?? 0) > 0} />
        <Stat label="Needs evidence systems" value={formatUnknown(health?.high_value_systems_needing_better_evidence)} highlight={(health?.high_value_systems_needing_better_evidence ?? 0) > 0} />
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs font-mono">
        <Stat label="Warehouse artifact" value={status.artifact?.file_name ?? 'hidden'} />
        <Stat label="Artifact age" value={formatAge(status.artifact?.age_seconds)} />
        <Stat label="Report schema" value={run?.schema_version ?? '—'} />
        <Stat label="Coverage schema" value={run?.coverage_schema_version ?? '—'} />
        <Stat label="Source run" value={snapshot?.source_run_key ?? '—'} />
        <Stat label="Source file" value={snapshot?.source_file_key ?? '—'} />
        <Stat label="Source" value={snapshot?.source ?? '—'} />
        <Stat label="Source files" value={formatUnknown(snapshot?.source_files_considered)} />
        <Stat label="Source types" value={formatDistribution(snapshot?.source_type_distribution)} />
        <Stat label="Source formats" value={formatDistribution(snapshot?.source_format_distribution)} />
        <Stat label="Station rows" value={formatUnknown(run?.staged_station_rows_considered)} />
        <Stat label="Body/ring rows" value={`${formatUnknown(run?.staged_body_rows_considered)} / ${formatUnknown(run?.staged_ring_rows_considered)}`} />
      </div>

      {(status.warnings.length > 0 || status.errors.length > 0) && (
        <div className="panel-thin border-gold/45 p-3 font-mono text-[11px] leading-snug text-gold" style={{ background: 'rgba(250,204,21,0.08)' }}>
          {[...status.errors, ...status.warnings].slice(0, 4).map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}

      <p className="text-[10px] leading-snug text-silver-dk font-mono">
        Read-only warehouse status from sanitized JSON. Missing values stay unavailable, and full filesystem paths are hidden.
        {loading && <span className="text-orange-lt ml-2">refreshing...</span>}
      </p>
    </div>
  );
}
