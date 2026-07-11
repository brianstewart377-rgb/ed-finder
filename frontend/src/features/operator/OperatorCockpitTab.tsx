import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { UseAdmin } from '@/features/admin/useAdmin';
import { readSelectedOperatorSourceRun, writeSelectedOperatorSourceRun } from './operatorSelection';
import type {
  OperatorDiagnosticRowSummary,
  OperatorSafetyGateSummary,
  OperatorSourceRunDetail,
  OperatorSourceRunSummary,
} from '@/types/api';
import { DiagnosticRowsPanel, SafetyGatesPanel, SourceRunDetailPanel, SourceRunsTable } from './operatorCockpitPanels';

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
  const [pendingSourceRunKey, setPendingSourceRunKey] = useState<string | null>(() => readSelectedOperatorSourceRun());
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
    writeSelectedOperatorSourceRun(sourceRunKey);
    setPendingSourceRunKey(null);
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

  useEffect(() => {
    if (!pendingSourceRunKey || !admin.token || loadState !== 'ok') return;
    const matchingRun = sourceRuns.find((run) => run.source_run_key === pendingSourceRunKey);
    if (!matchingRun) return;
    void selectSourceRun(matchingRun.source_run_key);
    writeSelectedOperatorSourceRun(null);
    setPendingSourceRunKey(null);
  }, [admin.token, loadState, pendingSourceRunKey, selectSourceRun, sourceRuns]);

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
