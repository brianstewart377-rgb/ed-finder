import { writable, derived, type Readable } from 'svelte/store';
import { browser } from '$app/environment';
import {
  authLogout,
  claimOwner,
  frontierLoginUrl,
  getAuthSession,
} from '$lib/api/client';

export interface AuthUser {
  commander_name: string | null;
  is_owner: boolean;
}
export interface AuthState {
  loading: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  ownerClaimAvailable: boolean;
  error: string | null;
}
export interface AuthApi {
  session: typeof getAuthSession;
  logout: typeof authLogout;
  claimOwner: typeof claimOwner;
}

const empty: AuthState = {
  loading: false,
  authenticated: false,
  user: null,
  ownerClaimAvailable: false,
  error: null,
};

export function createAuthStore(
  api: AuthApi = { session: getAuthSession, logout: authLogout, claimOwner },
) {
  const state = writable<AuthState>({ ...empty, loading: browser });
  const accept = (session: Awaited<ReturnType<AuthApi['session']>>) =>
    state.set({
      loading: false,
      authenticated: session.authenticated,
      user: session.user
        ? {
            commander_name: session.user.commander_name ?? null,
            is_owner: session.user.is_owner,
          }
        : null,
      ownerClaimAvailable: session.owner_claim_available ?? false,
      error: null,
    });
  const fail = (error: unknown) =>
    state.set({
      ...empty,
      error: error instanceof Error ? error.message : String(error),
    });
  return {
    subscribe: state.subscribe,
    owner: derived(
      state,
      ($state) => $state.user?.is_owner === true,
    ) as Readable<boolean>,
    async bootstrap() {
      state.update((value) => ({ ...value, loading: true, error: null }));
      try {
        accept(await api.session());
      } catch (error) {
        fail(error);
      }
    },
    signIn() {
      if (!browser) return;
      const returnTo = `${location.pathname}${location.search}${location.hash}`;
      location.assign(frontierLoginUrl(returnTo));
    },
    async signOut() {
      state.update((value) => ({ ...value, error: null }));
      try {
        accept(await api.logout());
        if (browser && ['/admin', '/operator'].includes(location.pathname))
          location.replace('/');
      } catch (error) {
        fail(error);
        throw error;
      }
    },
    async claimOwner(token: string) {
      const trimmed = token.trim();
      if (!trimmed) throw new Error('Admin token is required');
      state.update((value) => ({ ...value, error: null }));
      try {
        accept(await api.claimOwner(trimmed));
      } catch (error) {
        // A rejected one-time owner claim does not invalidate the cookie-backed
        // Frontier session that was required to make the attempt.
        state.update((value) => ({
          ...value,
          error: error instanceof Error ? error.message : String(error),
        }));
        throw error;
      }
    },
  };
}

export const auth = createAuthStore();
