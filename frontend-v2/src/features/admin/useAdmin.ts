import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AppStatus, CacheStats } from '@/types/api';

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
  metaLoading: boolean;
  metaError:   string | null;
  refresh:     () => Promise<void>;

  // Action state machine: idle → busy → ok | err
  actionState: { kind: 'idle' } | { kind: 'busy'; what: string }
              | { kind: 'ok'; what: string; message: string }
              | { kind: 'err'; what: string; message: string };
  clearCache:      () => Promise<void>;
  rebuildClusters: () => Promise<void>;
  resetActionState: () => void;
}

export function useAdmin(): UseAdmin {
  const [token, setTokenState] = useState<string>(
    () => sessionStorage.getItem(TOKEN_KEY) ?? ''
  );
  const [status,      setStatus]      = useState<AppStatus | null>(null);
  const [cache,       setCache]       = useState<CacheStats | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError,   setMetaError]   = useState<string | null>(null);
  const [actionState, setActionState] = useState<UseAdmin['actionState']>({ kind: 'idle' });

  const setToken = useCallback((t: string) => {
    setTokenState(t);
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else   sessionStorage.removeItem(TOKEN_KEY);
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
  }, []);

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
    status, cache, metaLoading, metaError, refresh,
    actionState,
    clearCache:      () => runAction('clearCache',      () => api.cacheClear(token)),
    rebuildClusters: () => runAction('rebuildClusters', () => api.rebuildClusters(token)),
    resetActionState: () => setActionState({ kind: 'idle' }),
  };
}
