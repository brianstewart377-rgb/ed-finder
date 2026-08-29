import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AuthSession, AuthUser } from '@/lib/api/auth';

const EMPTY_SESSION: AuthSession = {
  authenticated: false,
  user: null,
  owner_claim_available: false,
};

export interface UseAuth {
  loading: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  ownerClaimAvailable: boolean;
  error: string | null;
  signIn: () => void;
  signOut: () => Promise<void>;
  claimOwner: (adminToken: string) => Promise<void>;
  refresh: () => Promise<void>;
}
export function useAuth(): UseAuth {
  const [session, setSession] = useState<AuthSession>(EMPTY_SESSION);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSession(await api.authSession());
    } catch (caught: unknown) {
      setSession(EMPTY_SESSION);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signIn = useCallback(() => {
    const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    window.location.assign(api.frontierLoginUrl(returnTo));
  }, []);

  const signOut = useCallback(async () => {
    setError(null);
    try {
      setSession(await api.authLogout());
      if (window.location.hash === '#admin' || window.location.hash === '#operator') {
        window.location.hash = '#finder';
      }
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  const claimOwner = useCallback(async (adminToken: string) => {
    setError(null);
    try {
      setSession(await api.claimOwner(adminToken));
    } catch (caught: unknown) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      throw caught;
    }
  }, []);

  return {
    loading,
    authenticated: session.authenticated,
    user: session.user,
    ownerClaimAvailable: session.owner_claim_available,
    error,
    signIn,
    signOut,
    claimOwner,
    refresh,
  };
}
