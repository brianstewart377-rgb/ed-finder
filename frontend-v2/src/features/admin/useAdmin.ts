import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AppStatus, CacheStats, EnrichmentStationStatus, EnrichmentWarehouseStatus, AdminDataStatus } from '@/types/api';

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
  metaLoading: boolean;
  metaError:   string | null;
  enrichmentLoading: boolean;
  enrichmentError: string | null;
  warehouseLoading: boolean;
  warehouseError: string | null;
  dataStatusLoading: boolean;
  dataStatusError: string | null;
  refresh:     () => Promise<void>;

  // Action state machine: idle → busy → ok | err
  actionState: { kind: 'idle' } | { kind: 'busy'; what: string }
              | { kind: 'ok'; what: string; message: string }
              | { kind: 'err'; what: string; message: string };
  clearCache:      () => Promise<void>;
  rebuildClusters: () => Promise<void>;
  rebuildRatings:  () => Promise<void>;
  resetActionState: () => void;
}

export function useAdmin(options: { enabled?: boolean } = {}): UseAdmin {
  const enabled = options.enabled ?? true;
  const [token, setTokenState] = useState<string>(
    () => sessionStorage.getItem(TOKEN_KEY) ?? ''
  );
  const [status,      setStatus]      = useState<AppStatus | null>(null);
  const [cache,       setCache]       = useState<CacheStats | null>(null);
  const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentStationStatus | null>(null);
  const [warehouseStatus, setWarehouseStatus] = useState<EnrichmentWarehouseStatus | null>(null);
  const [dataStatus, setDataStatus] = useState<AdminDataStatus | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError,   setMetaError]   = useState<string | null>(null);
  const [enrichmentLoading, setEnrichmentLoading] = useState(false);
  const [enrichmentError, setEnrichmentError] = useState<string | null>(null);
  const [warehouseLoading, setWarehouseLoading] = useState(false);
  const [warehouseError, setWarehouseError] = useState<string | null>(null);
  const [dataStatusLoading, setDataStatusLoading] = useState(false);
  const [dataStatusError, setDataStatusError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<UseAdmin['actionState']>({ kind: 'idle' });

  const setToken = useCallback((t: string) => {
    setTokenState(t);
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else   sessionStorage.removeItem(TOKEN_KEY);
  }, []);

  const forgetToken = useCallback(() => setToken(''), [setToken]);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setStatus(null);
      setCache(null);
      setEnrichmentStatus(null);
      setWarehouseStatus(null);
      setDataStatus(null);
      setMetaLoading(false);
      setEnrichmentLoading(false);
      setWarehouseLoading(false);
      setDataStatusLoading(false);
      setMetaError(null);
      setEnrichmentError(null);
      setWarehouseError(null);
      setDataStatusError(null);
      return;
    }
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
      setEnrichmentError(null);
      setWarehouseError(null);
      setDataStatusError(null);
      setEnrichmentLoading(false);
      setWarehouseLoading(false);
      setDataStatusLoading(false);
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
  }, [enabled, token]);

  // Initial fetch + 30s poll. We don't poll faster — these endpoints hit
  // the DB and there's no value in sub-second updates for ops dashboards.
  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => { void refresh(); }, 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const runAction = useCallback(async (
    what: string,
    fn:   () => Promise<{ message?: string; ok?: boolean; job_id?: string }>,
  ) => {
    setActionState({ kind: 'busy', what });
    try {
      const out = await fn();
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
    status, cache, enrichmentStatus, warehouseStatus, dataStatus,
    metaLoading, metaError, enrichmentLoading, enrichmentError, warehouseLoading, warehouseError, dataStatusLoading, dataStatusError, refresh,
    actionState,
    clearCache:      () => runAction('clearCache',      () => api.cacheClear(token)),
    rebuildClusters: () => runAction('rebuildClusters', () => api.rebuildClusters(token)),
    rebuildRatings:  () => runAction('rebuildRatings',  () => api.rebuildRatings(token)),
    resetActionState: () => setActionState({ kind: 'idle' }),
  };
}
