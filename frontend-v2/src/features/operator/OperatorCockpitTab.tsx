import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { UseAdmin } from '@/features/admin/useAdmin';
import type {
  OperatorArtifactSummary,
  OperatorBridgeSummary,
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
  OperatorStagingImpactSummary,
} from '@/types/api';

const RECENT_LIMIT = 25;

type LoadState = 'idle' | 'loading' | 'ok' | 'err';

export interface OperatorCockpitTabProps {
  admin: Pick<UseAdmin, 'token' | 'setToken' | 'forgetToken' | 'hasToken'>;
}

export function OperatorCockpitTab({ admin }: OperatorCockpitTabProps) {
  const [tokenDraft, setTokenDraft] = useState(admin.token);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [safetyGates, setSafetyGates] = useState<OperatorSafetyGateSummary | null>(null);
  const [sourceRuns, setSourceRuns] = useState<OperatorSourceRunSummary[]>([]);
  const [diagnosticRows, setDiagnosticRows] = useState<OperatorDiagnosticRowSummary[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<OperatorSourceRunDetail | null>(null);
  const [detailState, setDetailState] = useState<LoadState>('idle');
  const [detailError, setDetailError] = useState<string | null>(null);
  const cockpitRequestSeq = useRef(0);
  const detailRequestSeq = useRef(0);

  useEffect(() => {
    setTokenDraft(admin.token);
  }, [admin.token]);

  const loadCockpit = useCallback(async () => {
    const requestSeq = cockpitRequestSeq.current + 1;
    cockpitRequestSeq.current = requestSeq;
    detailRequestSeq.current += 1;
    setSelectedKey(null);
    setDetail(null);
    setDetailState('idle');
    setDetailError(null);

    if (!admin.token) {
      setLoadState('idle');
      setSafetyGates(null);
      setSourceRuns([]);
      setDiagnosticRows([]);
      setSelectedKey(null);
      setDetail(null);
      setDetailState('idle');
      setError(null);
      return;
    }

    setLoadState('loading');
    setError(null);
    try {
      const [gates, runs, diagnostics] = await Promise.all([
        api.operatorSafetyGates(admin.token),
        api.operatorSourceRuns(admin.token, RECENT_LIMIT),
        api.operatorDiagnosticRows(admin.token, { limit: RECENT_LIMIT }),
      ]);
      if (requestSeq !== cockpitRequestSeq.current) return;
      setSafetyGates(gates);
      setSourceRuns(runs);
      setDiagnosticRows(diagnostics);
      setLoadState('ok');
    } catch (caught: unknown) {
      if (requestSeq !== cockpitRequestSeq.current) return;
      setSafetyGates(null);
      setSourceRuns([]);
      setDiagnosticRows([]);
      setLoadState('err');
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [admin.token]);

  useEffect(() => {
    void loadCockpit();
  }, [loadCockpit]);

  const selectSourceRun = useCallback(async (sourceRunKey: string) => {
    if (!admin.token) return;
    cockpitRequestSeq.current += 1;
    const requestSeq = detailRequestSeq.current + 1;
    detailRequestSeq.current = requestSeq;
    setSelectedKey(sourceRunKey);
    setDetail(null);
    setDiagnosticRows([]);
    setDetailState('loading');
    setDetailError(null);
    try {
      const [nextDetail, nextDiagnostics] = await Promise.all([
        api.operatorSourceRunDetail(admin.token, sourceRunKey),
        api.operatorDiagnosticRows(admin.token, { sourceRunKey, limit: RECENT_LIMIT }),
      ]);
      if (requestSeq !== detailRequestSeq.current) return;
      setDetail(nextDetail);
      setDiagnosticRows(nextDiagnostics);
      setDetailState('ok');
    } catch (caught: unknown) {
      if (requestSeq !== detailRequestSeq.current) return;
      setDetail(null);
      setDetailState('err');
      setDetailError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [admin.token]);

  return (
    <section data-testid="operator-cockpit" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <div>
          <h2 className="font-display text-orange tracking-[0.14em] text-lg">Operator cockpit</h2>
          <p className="font-mono text-xs text-silver-dk">
            read-only warehouse instruments before throttle
          </p>
        </div>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void loadCockpit()}
          disabled={!admin.hasToken || loadState === 'loading'}
          data-testid="operator-refresh"
          className="btn-metal text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Refresh cockpit
        </button>
      </header>

      <section className="panel p-5 space-y-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          Admin access
        </h3>
        <p className="text-[11px] text-silver-dk leading-snug">
          This page is read-only. It uses Stage 19AP operator visibility endpoints and does not run imports,
          enable scheduler/timers, write canonical tables, or run canonical apply.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={tokenDraft}
            onChange={(event) => setTokenDraft(event.target.value)}
            placeholder="X-Admin-Token"
            data-testid="operator-token-input"
            className="flex-1 min-w-[220px]"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => admin.setToken(tokenDraft.trim())}
            data-testid="operator-token-save"
            className="btn-primary text-[11px] py-1.5 px-3"
          >
            Save token
          </button>
          {admin.hasToken && (
            <button
              type="button"
              onClick={() => admin.forgetToken()}
              data-testid="operator-token-forget"
              className="btn-metal text-[11px] py-1.5 px-3"
            >
              Forget token
            </button>
          )}
          <span className={admin.hasToken ? 'font-mono text-[10px] text-green' : 'font-mono text-[10px] text-silver-dk'}>
            {admin.hasToken ? 'Token set' : 'No token'}
          </span>
        </div>
      </section>

      {loadState === 'loading' && (
        <div className="text-text-dim font-mono text-sm py-8 text-center">
          Loading cockpit...
        </div>
      )}

      {loadState === 'err' && (
        <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
          <div className="font-bold mb-1">Failed to load operator cockpit.</div>
          {error && <div className="text-xs">{error}</div>}
        </div>
      )}

      {!admin.hasToken && (
        <div className="panel p-5 text-[11px] text-silver-dk font-mono">
          Set an admin token to load the read-only operator cockpit.
        </div>
      )}

      {admin.hasToken && (
        <>
          <SafetyGatesPanel safetyGates={safetyGates} loading={loadState === 'loading'} />
          <SourceRunsTable
            sourceRuns={sourceRuns}
            selectedKey={selectedKey}
            loading={loadState === 'loading'}
            onSelect={(sourceRunKey) => void selectSourceRun(sourceRunKey)}
          />
          <SourceRunDetailPanel
            selectedKey={selectedKey}
            detail={detail}
            detailState={detailState}
            detailError={detailError}
          />
          <DiagnosticRowsPanel rows={diagnosticRows} selectedKey={selectedKey} />
        </>
      )}
    </section>
  );
}

function SafetyGatesPanel({
  safetyGates,
  loading,
}: {
  safetyGates: OperatorSafetyGateSummary | null;
  loading: boolean;
}) {
  const safe = safetyGates?.safe_to_proceed === true;
  const statusClass = !safetyGates
    ? 'border-border bg-bg3/40 text-silver-dk'
    : safe
      ? 'border-green/50 bg-green/10 text-green'
      : 'border-red/50 bg-red/10 text-red';
  const statusLabel = !safetyGates
    ? 'Safety gates pending'
    : safe
      ? 'Safe to proceed'
      : 'Not safe to proceed';

  return (
    <section className="panel p-5 space-y-4" data-testid="operator-safety-gates">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          1. Safety gates
        </h3>
        <span
          className={[
            'rounded-chunk-sm border px-2 py-1 font-mono text-[11px]',
            statusClass,
          ].join(' ')}
        >
          {statusLabel}
        </span>
        {loading && <span className="font-mono text-[10px] text-orange-lt">refreshing...</span>}
      </div>

      <p className="text-[11px] leading-snug text-silver-dk">
        Scheduler/timers remain assumed disabled. Canonical apply remains assumed disabled.
        Diagnostic rows are not canonical candidates. The 25-row pilot should not proceed if safety gates are red.
      </p>

      {safetyGates ? (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs">
            <Flag label="No running runs" value={safetyGates.no_running_source_runs} />
            <Flag label="Artifacts present" value={safetyGates.latest_artifacts_present} />
            <Flag label="Bridge FK verified" value={safetyGates.bridge_fk_path_verified} />
            <Flag label="Diagnostics isolated" value={safetyGates.diagnostic_rows_isolated} />
            <Flag label="No unrecovered failures" value={safetyGates.no_failed_unrecovered_source_runs} />
            <Flag label="Scheduler disabled" value={safetyGates.scheduler_assumed_disabled} />
            <Flag label="Canonical apply disabled" value={safetyGates.canonical_apply_assumed_disabled} />
            <Stat label="Latest source run" value={safetyGates.latest_source_run_key ?? '-'} />
          </div>
          <WarningList title="Blockers" items={safetyGates.blockers} empty="No blockers reported." danger />
          <WarningList title="Notes" items={safetyGates.notes} empty="No operator notes reported." />
        </>
      ) : (
        <p className="text-[11px] text-silver-dk font-mono">
          Safety gate status has not loaded yet.
        </p>
      )}
    </section>
  );
}

function SourceRunsTable({
  sourceRuns,
  selectedKey,
  loading,
  onSelect,
}: {
  sourceRuns: OperatorSourceRunSummary[];
  selectedKey: string | null;
  loading: boolean;
  onSelect: (sourceRunKey: string) => void;
}) {
  return (
    <section className="panel p-5 space-y-3" data-testid="operator-source-runs">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          2. Recent source runs
        </h3>
        {loading && <span className="font-mono text-[10px] text-orange-lt">refreshing...</span>}
      </div>
      {sourceRuns.length === 0 ? (
        <p className="text-[11px] text-silver-dk font-mono">No source runs found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] text-left font-mono text-[11px]">
            <thead className="text-silver-dk uppercase tracking-[0.12em]">
              <tr>
                <th className="py-2 pr-3">Source run key</th>
                <th className="py-2 pr-3">Source / category / domain / scope</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Started / finished</th>
                <th className="py-2 pr-3">Rows</th>
                <th className="py-2 pr-3">Artifact / hash</th>
                <th className="py-2 pr-3">Bridge</th>
                <th className="py-2 pr-3">Trigger</th>
                <th className="py-2 pr-3">Git</th>
              </tr>
            </thead>
            <tbody>
              {sourceRuns.map((run) => (
                <tr
                  key={run.source_run_key}
                  className={[
                    'border-t border-border/60 align-top',
                    selectedKey === run.source_run_key ? 'bg-orange/10' : '',
                  ].join(' ')}
                >
                  <td className="py-2 pr-3">
                    <button
                      type="button"
                      onClick={() => onSelect(run.source_run_key)}
                      className="text-left text-orange-lt underline decoration-orange/40 underline-offset-2 hover:text-orange"
                    >
                      {run.source_run_key}
                    </button>
                  </td>
                  <td className="py-2 pr-3 text-silver">
                    {joinDefined([run.source_name, run.source_category, run.domain, run.import_scope])}
                  </td>
                  <td className="py-2 pr-3 text-silver">{run.status ?? '-'}</td>
                  <td className="py-2 pr-3 text-silver-dk">
                    {formatDate(run.started_at)} / {formatDate(run.finished_at)}
                  </td>
                  <td className="py-2 pr-3 text-silver">
                    {run.rows_read.toLocaleString()} read / {run.rows_staged.toLocaleString()} staged /
                    {' '}{run.rows_rejected.toLocaleString()} rejected / {run.rows_skipped.toLocaleString()} skipped
                  </td>
                  <td className="py-2 pr-3 text-silver-dk">
                    {formatBool(run.artifact_present)} / {formatBool(run.artifact_hash_present)}
                  </td>
                  <td className="py-2 pr-3 text-silver-dk">{formatBool(run.bridge_present)}</td>
                  <td className="py-2 pr-3 text-silver-dk">{run.trigger_context ?? '-'}</td>
                  <td className="py-2 pr-3 text-silver-dk">{shortSha(run.git_commit_sha)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SourceRunDetailPanel({
  selectedKey,
  detail,
  detailState,
  detailError,
}: {
  selectedKey: string | null;
  detail: OperatorSourceRunDetail | null;
  detailState: LoadState;
  detailError: string | null;
}) {
  return (
    <section className="panel p-5 space-y-3" data-testid="operator-source-run-detail">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        3. Selected source run detail
      </h3>
      {!selectedKey && (
        <p className="text-[11px] text-silver-dk font-mono">
          Select a source run to load detail.
        </p>
      )}
      {selectedKey && detailState === 'loading' && (
        <p className="text-[11px] text-silver-dk font-mono">
          Loading detail for {selectedKey}...
        </p>
      )}
      {selectedKey && detailState === 'err' && (
        <div className="panel-thin border-red/50 p-2 font-mono text-xs text-red" style={{ background: 'rgba(248,113,113,0.10)' }}>
          <div>Detail unavailable.</div>
          {detailError && <div>{detailError}</div>}
        </div>
      )}
      {detail && detailState === 'ok' && (
        <div className="space-y-3">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs">
            <Stat label="Source URI" value={detail.source_uri_redacted ?? '-'} />
            <Stat label="Importer" value={joinDefined([detail.importer_name, detail.importer_version])} />
            <Stat label="Input hash" value={shortHash(detail.source_input_sha256)} />
            <Stat label="Manifest hash" value={shortHash(detail.source_manifest_sha256)} />
          </div>
          <div className="grid lg:grid-cols-3 gap-3">
            <ArtifactSummaryPanel artifact={detail.artifact_summary} />
            <BridgeSummaryPanel bridge={detail.bridge_summary} />
            <StagingImpactPanel impact={detail.staging_impact_summary} />
          </div>
          <WarningList title="Validation warnings" items={detail.validation_warnings} empty="No validation warnings reported." danger />
          <WarningList title="Operator notes" items={detail.operator_notes} empty="No operator notes reported." />
        </div>
      )}
    </section>
  );
}

function ArtifactSummaryPanel({ artifact }: { artifact: OperatorArtifactSummary }) {
  return (
    <div className="panel-thin p-3 space-y-2">
      <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
        Artifact summary
      </div>
      <MetricList rows={[
        ['Path', artifact.artifact_path_redacted ?? '-'],
        ['Record', formatBool(artifact.artifact_record_present)],
        ['File exists', formatNullableBool(artifact.file_exists)],
        ['File hash', shortHash(artifact.artifact_sha256)],
        ['Integrity hash', shortHash(artifact.artifact_integrity_sha256)],
        ['Schema', artifact.schema_version ?? '-'],
        ['Rows', `${artifact.rows_read.toLocaleString()} read / ${artifact.rows_staged.toLocaleString()} staged`],
        ['Status', artifact.status ?? '-'],
        ['Validation', artifact.validation_note],
      ]} />
    </div>
  );
}

function BridgeSummaryPanel({ bridge }: { bridge: OperatorBridgeSummary }) {
  return (
    <div className="panel-thin p-3 space-y-2">
      <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
        Bridge summary
      </div>
      <MetricList rows={[
        ['Present', formatBool(bridge.bridge_present)],
        ['Bridge key', bridge.bridge_key],
        ['Legacy id', bridge.legacy_source_run_id == null ? '-' : String(bridge.legacy_source_run_id)],
        ['Adapter', joinDefined([bridge.adapter_name, bridge.adapter_version])],
        ['Target FK', bridge.target_staging_fk],
        ['Dry run', formatNullableBool(bridge.dry_run)],
        ['Metadata bridge', formatBool(bridge.metadata_has_compatibility_bridge)],
        ['Source_runs FK blocked', formatBool(bridge.staging_policy_blocks_source_runs_id)],
      ]} />
    </div>
  );
}

function StagingImpactPanel({ impact }: { impact: OperatorStagingImpactSummary | null }) {
  if (!impact) {
    return (
      <div className="panel-thin p-3 space-y-2">
        <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
          Staging impact summary
        </div>
        <p className="text-[11px] text-silver-dk font-mono">No bridge-backed staging impact available.</p>
      </div>
    );
  }

  return (
    <div className="panel-thin p-3 space-y-2">
      <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
        Staging impact summary
      </div>
      <MetricList rows={[
        ['Table', impact.staging_table],
        ['Legacy id', String(impact.legacy_source_run_id)],
        ['Rows total', impact.rows_total.toLocaleString()],
        ['Diagnostic only', impact.rows_diagnostic_only.toLocaleString()],
        ['Canonical blocked', impact.rows_canonical_write_blocked.toLocaleString()],
        ['Stage markers', impact.rows_with_stage_markers.toLocaleString()],
        ['Legacy FK rows', impact.rows_using_legacy_bridge_id.toLocaleString()],
        ['Source_runs FK rows', impact.rows_using_source_runs_id.toLocaleString()],
      ]} />
      <WarningList title="Staging warnings" items={impact.warnings} empty="No staging warnings reported." danger />
    </div>
  );
}

function DiagnosticRowsPanel({
  rows,
  selectedKey,
}: {
  rows: OperatorDiagnosticRowSummary[];
  selectedKey: string | null;
}) {
  return (
    <section className="panel p-5 space-y-3" data-testid="operator-diagnostic-rows">
      <div>
        <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
          4. Diagnostic rows
        </h3>
        <p className="text-[11px] text-silver-dk">
          {selectedKey
            ? `Diagnostic staging rows scoped to ${selectedKey}.`
            : 'Latest diagnostic staging rows.'}
          {' '}These rows are not canonical candidates.
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="text-[11px] text-silver-dk font-mono">No diagnostic rows found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left font-mono text-[11px]">
            <thead className="text-silver-dk uppercase tracking-[0.12em]">
              <tr>
                <th className="py-2 pr-3">Row id</th>
                <th className="py-2 pr-3">Legacy source run id</th>
                <th className="py-2 pr-3">Station / system / type</th>
                <th className="py-2 pr-3">Source class / confidence</th>
                <th className="py-2 pr-3">Marker keys</th>
                <th className="py-2 pr-3">canonical_write_allowed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.row_id} className="border-t border-border/60 align-top">
                  <td className="py-2 pr-3 text-silver">{row.row_id}</td>
                  <td className="py-2 pr-3 text-silver-dk">{row.legacy_source_run_id ?? '-'}</td>
                  <td className="py-2 pr-3 text-silver">
                    {joinDefined([row.station_name, row.system_name, row.station_type])}
                  </td>
                  <td className="py-2 pr-3 text-silver-dk">
                    {joinDefined([row.source_class, row.confidence])}
                  </td>
                  <td className="py-2 pr-3 text-silver-dk">{row.marker_keys.join(', ') || '-'}</td>
                  <td className="py-2 pr-3 text-silver-dk">{formatNullableBool(row.canonical_write_allowed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MetricList({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="space-y-1 font-mono text-[11px]">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[130px_1fr] gap-2">
          <dt className="text-silver-dk">{label}</dt>
          <dd className="text-silver break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function WarningList({
  title,
  items,
  empty,
  danger = false,
}: {
  title: string;
  items: string[];
  empty: string;
  danger?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="font-display text-orange text-[11px] uppercase tracking-[0.16em]">
        {title}
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] text-silver-dk font-mono">{empty}</p>
      ) : (
        <ul className={danger ? 'space-y-1 text-[11px] text-red font-mono' : 'space-y-1 text-[11px] text-silver-dk font-mono'}>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-chunk-sm p-2.5 border border-border bg-bg3/40">
      <div className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</div>
      <div className="tabular-nums font-bold mt-0.5 text-silver break-words">
        {value}
      </div>
    </div>
  );
}

function Flag({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="rounded-chunk-sm p-2.5 border border-border bg-bg3/40 flex items-center justify-between gap-2">
      <span className="text-silver-dk uppercase tracking-[0.16em] text-[10px]">{label}</span>
      <span className={value ? 'text-green' : 'text-red'}>{value ? 'yes' : 'no'}</span>
    </div>
  );
}

function joinDefined(values: Array<string | null | undefined>): string {
  const parts = values.filter((value): value is string => Boolean(value));
  return parts.length === 0 ? '-' : parts.join(' / ');
}

function formatDate(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatBool(value: boolean): string {
  return value ? 'yes' : 'no';
}

function formatNullableBool(value: boolean | null): string {
  if (value === null) return '-';
  return formatBool(value);
}

function shortSha(value: string | null): string {
  if (!value) return '-';
  return value.slice(0, 8);
}

function shortHash(value: string | null): string {
  if (!value) return '-';
  return value.length > 16 ? value.slice(0, 16) : value;
}
