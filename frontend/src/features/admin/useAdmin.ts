import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { readSessionStorageItem, removeSessionStorageItem, writeSessionStorageItem } from '@/lib/browserStorage';
import type {
  AppStatus,
  CacheStats,
  EnrichmentStationStatus,
  EnrichmentWarehouseStatus,
  AdminDataStatus,
  AdminCronStatus,
  AdminOperationHistoryEntry,
  AdminOperationRunResponse,
  OperatorSafetyGateSummary,
  OperatorSourceRunSummary,
} from '@/types/api';

const TOKEN_KEY = 'ed_admin_token';

/**
 * Admin token + ops actions + a polling stats reader.
 *
 * The token lives in **sessionStorage** on purpose — admin tokens
 * shouldn't survive a tab close. localStorage would be a footgun on a
 * shared machine.
 */
export interface UseAdmin {
  token:     string;
  setToken:  (t: string) => void;
  forgetToken: () => void;
  hasToken:  boolean;

  status:      AppStatus | null;
  cache:       CacheStats | null;
  enrichmentStatus: EnrichmentStationStatus | null;
  warehouseStatus: EnrichmentWarehouseStatus | null;
  dataStatus: AdminDataStatus | null;
  cronStatus: AdminCronStatus | null;
  importSafetyGates: OperatorSafetyGateSummary | null;
  importSourceRuns: OperatorSourceRunSummary[];
  operationHistory: AdminOperationHistoryEntry[];
  metaLoading: boolean;
  metaError:   string | null;
  enrichmentLoading: boolean;
  enrichmentError: string | null;
  warehouseLoading: boolean;
  warehouseError: string | null;
  dataStatusLoading: boolean;
  dataStatusError: string | null;
  cronStatusLoading: boolean;
  cronStatusError: string | null;
  importDashboardLoading: boolean;
  importDashboardError: string | null;
  operationHistoryLoading: boolean;
  operationHistoryError: string | null;
  refresh:     () => Promise<void>;
  lastOperationResult: {
    what: string;
    status: string;
    exitCode: number | null;
    jobRunId: number;
    outputText: string;
  } | null;

  // Action state machine: idle → busy → ok | err
  actionState: { kind: 'idle' } | { kind: 'busy'; what: string }
              | { kind: 'ok'; what: string; message: string }
              | { kind: 'err'; what: string; message: string };
  clearCache:      () => Promise<void>;
  rebuildClusters: () => Promise<void>;
  rebuildRatings:  () => Promise<void>;
  runTelemetryHotLogSnapshot: () => Promise<void>;
  runDataInvariants: () => Promise<void>;
  resetActionState: () => void;
  clearLastOperationResult: () => void;
}

export function useAdmin(): UseAdmin {
  const [token, setTokenState] = useState<string>(
    () => readSessionStorageItem(TOKEN_KEY) ?? '',
  );
  const [status,      setStatus]      = useState<AppStatus | null>(null);
  const [cache,       setCache]       = useState<CacheStats | null>(null);
  const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentStationStatus | null>(null);
  const [warehouseStatus, setWarehouseStatus] = useState<EnrichmentWarehouseStatus | null>(null);
  const [dataStatus, setDataStatus] = useState<AdminDataStatus | null>(null);
  const [cronStatus, setCronStatus] = useState<AdminCronStatus | null>(null);
  const [importSafetyGates, setImportSafetyGates] = useState<OperatorSafetyGateSummary | null>(null);
  const [importSourceRuns, setImportSourceRuns] = useState<OperatorSourceRunSummary[]>([]);
  const [operationHistory, setOperationHistory] = useState<AdminOperationHistoryEntry[]>([]);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError,   setMetaError]   = useState<string | null>(null);
  const [enrichmentLoading, setEnrichmentLoading] = useState(false);
  const [enrichmentError, setEnrichmentError] = useState<string | null>(null);
  const [warehouseLoading, setWarehouseLoading] = useState(false);
  const [warehouseError, setWarehouseError] = useState<string | null>(null);
  const [dataStatusLoading, setDataStatusLoading] = useState(false);
  const [dataStatusError, setDataStatusError] = useState<string | null>(null);
  const [cronStatusLoading, setCronStatusLoading] = useState(false);
  const [cronStatusError, setCronStatusError] = useState<string | null>(null);
  const [importDashboardLoading, setImportDashboardLoading] = useState(false);
  const [importDashboardError, setImportDashboardError] = useState<string | null>(null);
  const [operationHistoryLoading, setOperationHistoryLoading] = useState(false);
  const [operationHistoryError, setOperationHistoryError] = useState<string | null>(null);
  const [lastOperationResult, setLastOperationResult] = useState<UseAdmin['lastOperationResult']>(null);
  const [actionState, setActionState] = useState<UseAdmin['actionState']>({ kind: 'idle' });

  const setToken = useCallback((t: string) => {
    setTokenState(t);
    if (t) writeSessionStorageItem(TOKEN_KEY, t);
    else removeSessionStorageItem(TOKEN_KEY);
  }, []);

  const forgetToken = useCallback(() => setToken(''), [setToken]);

  const refresh = useCallback(async () => {
    setMetaLoading(true);
    setMetaError(null);
    try {
      const [s, c] = await Promise.all([api.status(), api.cacheStats()]);
      setStatus(s);
      setCache(c);
    } catch (e: unknown) {
      setMetaError(e instanceof Error ? e.message : String(e));
    } finally {
      setMetaLoading(false);
    }

    if (!token) {
      setEnrichmentStatus(null);
      setWarehouseStatus(null);
      setDataStatus(null);
      setCronStatus(null);
      setImportSafetyGates(null);
      setImportSourceRuns([]);
      setOperationHistory([]);
      setLastOperationResult(null);
      setEnrichmentError(null);
      setWarehouseError(null);
      setDataStatusError(null);
      setCronStatusError(null);
      setImportDashboardError(null);
      setOperationHistoryError(null);
      setEnrichmentLoading(false);
      setWarehouseLoading(false);
      setDataStatusLoading(false);
      setCronStatusLoading(false);
      setImportDashboardLoading(false);
      setOperationHistoryLoading(false);
      return;
    }
    setEnrichmentLoading(true);
    setEnrichmentError(null);
    try {
      setEnrichmentStatus(await api.enrichmentStationStatus(token));
    } catch (e: unknown) {
      setEnrichmentStatus(null);
      setEnrichmentError(e instanceof Error ? e.message : String(e));
    } finally {
      setEnrichmentLoading(false);
    }

    setWarehouseLoading(true);
    setWarehouseError(null);
    try {
      setWarehouseStatus(await api.enrichmentWarehouseStatus(token));
    } catch (e: unknown) {
      setWarehouseStatus(null);
      setWarehouseError(e instanceof Error ? e.message : String(e));
    } finally {
      setWarehouseLoading(false);
    }

    setDataStatusLoading(true);
    setDataStatusError(null);
    try {
      setDataStatus(await api.adminDataStatus(token));
    } catch (e: unknown) {
      setDataStatus(null);
      setDataStatusError(e instanceof Error ? e.message : String(e));
    } finally {
      setDataStatusLoading(false);
    }

    setCronStatusLoading(true);
    setCronStatusError(null);
    try {
      setCronStatus(await api.adminCronStatus(token));
    } catch (e: unknown) {
      setCronStatus(null);
      setCronStatusError(e instanceof Error ? e.message : String(e));
    } finally {
      setCronStatusLoading(false);
    }

    setImportDashboardLoading(true);
    setImportDashboardError(null);
    try {
      const [gates, runs] = await Promise.all([
        api.operatorSafetyGates(token),
        api.operatorSourceRuns(token, 12),
      ]);
      setImportSafetyGates(gates);
      setImportSourceRuns(runs);
    } catch (e: unknown) {
      setImportSafetyGates(null);
      setImportSourceRuns([]);
      setImportDashboardError(e instanceof Error ? e.message : String(e));
    } finally {
      setImportDashboardLoading(false);
    }

    setOperationHistoryLoading(true);
    setOperationHistoryError(null);
    try {
      const history = await api.adminOperationHistory(token, 6);
      setOperationHistory(history.operations);
    } catch (e: unknown) {
      setOperationHistory([]);
      setOperationHistoryError(e instanceof Error ? e.message : String(e));
    } finally {
      setOperationHistoryLoading(false);
    }
  }, [token]);

  // Initial fetch + 30s poll. We don't poll faster — these endpoints hit
  // the DB and there's no value in sub-second updates for ops dashboards.
  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => { void refresh(); }, 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const runAction = useCallback(async (
    what: string,
    fn:   () => Promise<{ message?: string; ok?: boolean; job_id?: string } & Partial<AdminOperationRunResponse>>,
  ) => {
    setActionState({ kind: 'busy', what });
    try {
      const out = await fn();
      if (typeof out.output_text === 'string' && typeof out.job_run_id === 'number') {
        setLastOperationResult({
          what,
          status: out.status ?? (out.ok ? 'completed' : 'failed'),
          exitCode: out.exit_code ?? null,
          jobRunId: out.job_run_id,
          outputText: out.output_text,
        });
      }
      setActionState({ kind: 'ok', what, message: out.message ?? 'Done.' });
      // Re-pull stats so the dashboard reflects the action.
      void refresh();
    } catch (e: unknown) {
      setActionState({
        kind:    'err',
        what,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [refresh]);

  return {
    token, setToken, forgetToken,
    hasToken: token.length > 0,
    status, cache, enrichmentStatus, warehouseStatus, dataStatus, cronStatus, importSafetyGates, importSourceRuns, operationHistory,
    metaLoading, metaError, enrichmentLoading, enrichmentError, warehouseLoading, warehouseError, dataStatusLoading, dataStatusError, cronStatusLoading, cronStatusError, importDashboardLoading, importDashboardError, operationHistoryLoading, operationHistoryError, refresh,
    lastOperationResult,
    actionState,
    clearCache:      () => runAction('clearCache',      () => api.cacheClear(token)),
    rebuildClusters: () => runAction('rebuildClusters', () => api.rebuildClusters(token)),
    rebuildRatings:  () => runAction('rebuildRatings',  () => api.rebuildRatings(token)),
    runTelemetryHotLogSnapshot: () => runAction(
      'telemetryHotLogSnapshot',
      () => api.adminRunOperation(token, 'telemetry_hot_log_snapshot'),
    ),
    runDataInvariants: () => runAction(
      'dataInvariants',
      () => api.adminRunOperation(token, 'data_invariants'),
    ),
    resetActionState: () => setActionState({ kind: 'idle' }),
    clearLastOperationResult: () => setLastOperationResult(null),
  };
}
