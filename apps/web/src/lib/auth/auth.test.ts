import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ADMIN_TOKEN_SESSION_KEY, apiRequest } from '$lib/api/client';
import { adminToken } from '$lib/persistence/stores';
import { createAuthStore } from './auth';

const guest = {
  authenticated: false,
  user: null,
  owner_claim_available: false,
};

function createTokenStore(initial = '') {
  let value = initial;
  return {
    store: {
      set: vi.fn((token: string) => {
        value = token;
        return true;
      }),
      clear: vi.fn(() => {
        value = '';
        return true;
      }),
    },
    value: () => value,
  };
}

describe('auth store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    adminToken.clear();
  });

  it('bootstraps cookie-backed session state', async () => {
    const api = {
      session: vi.fn().mockResolvedValue(guest),
      logout: vi.fn(),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api);
    await store.bootstrap();
    expect(get(store)).toMatchObject({
      loading: false,
      authenticated: false,
      error: null,
    });
  });

  it('derives owner state and claims with a trimmed one-time token', async () => {
    const owner = {
      authenticated: true,
      user: { commander_name: 'Owner', is_owner: true },
      owner_claim_available: false,
    };
    const api = {
      session: vi.fn(),
      logout: vi.fn(),
      claimOwner: vi.fn().mockResolvedValue(owner),
    };
    const tokenStore = createTokenStore();
    const store = createAuthStore(api, tokenStore.store);
    await store.claimOwner(' secret ');
    expect(api.claimOwner).toHaveBeenCalledWith('secret');
    expect(tokenStore.store.set).toHaveBeenCalledWith('secret');
    expect(tokenStore.value()).toBe('secret');
    expect(get(store.owner)).toBe(true);
  });

  it('bridges a successful claim to later bounded mutation requests', async () => {
    const owner = {
      authenticated: true,
      user: { commander_name: 'Owner', is_owner: true },
      owner_claim_available: false,
    };
    const api = {
      session: vi.fn(),
      logout: vi.fn(),
      claimOwner: vi.fn().mockResolvedValue(owner),
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    const store = createAuthStore(api, adminToken);

    await store.claimOwner('  bridge-token  ');
    await apiRequest('/observations/facts/observation-1', {
      method: 'PATCH',
      body: JSON.stringify({ status: 'confirmed' }),
    });

    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBe(
      'bridge-token',
    );
    expect(localStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
    expect(
      new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-Admin-Token'),
    ).toBe('bridge-token');
  });

  it('reports when a successful claim cannot persist the credential', async () => {
    const owner = {
      authenticated: true,
      user: { commander_name: 'Owner', is_owner: true },
      owner_claim_available: false,
    };
    const api = {
      session: vi.fn(),
      logout: vi.fn(),
      claimOwner: vi.fn().mockResolvedValue(owner),
    };
    const tokenStore = createTokenStore();
    tokenStore.store.set.mockReturnValue(false);
    const store = createAuthStore(api, tokenStore.store);

    await expect(store.claimOwner(' session-token ')).rejects.toThrow(
      'could not be stored',
    );

    expect(api.claimOwner).toHaveBeenCalledWith('session-token');
    expect(tokenStore.store.set).toHaveBeenCalledWith('session-token');
    expect(get(store)).toMatchObject({
      authenticated: true,
      user: { is_owner: true },
      error: expect.stringContaining('could not be stored'),
    });
  });

  it('does not replace a prior token when the owner claim fails', async () => {
    adminToken.set('prior-token');
    const setToken = vi.spyOn(adminToken, 'set');
    const clearToken = vi.spyOn(adminToken, 'clear');
    const signedInNonOwner = {
      authenticated: true,
      user: { commander_name: 'Commander', is_owner: false },
      owner_claim_available: true,
    };
    const api = {
      session: vi.fn().mockResolvedValue(signedInNonOwner),
      logout: vi.fn(),
      claimOwner: vi.fn().mockRejectedValue(new Error('Invalid admin token')),
    };
    const store = createAuthStore(api, adminToken);
    await store.bootstrap();

    await expect(store.claimOwner(' replacement ')).rejects.toThrow(
      'Invalid admin token',
    );

    expect(setToken).not.toHaveBeenCalled();
    expect(clearToken).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBe('prior-token');
    expect(localStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
    expect(get(store)).toMatchObject({
      authenticated: true,
      user: { commander_name: 'Commander', is_owner: false },
      ownerClaimAvailable: true,
      error: 'Invalid admin token',
    });
  });

  it('clears the session token on explicit sign-out', async () => {
    adminToken.set('session-token');
    const clearToken = vi.spyOn(adminToken, 'clear');
    const api = {
      session: vi.fn(),
      logout: vi.fn().mockResolvedValue(guest),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api, adminToken);

    await store.signOut();

    expect(clearToken).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
    expect(localStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBeNull();
  });

  it('keeps the explicit token clear when logout is unavailable', async () => {
    const tokenStore = createTokenStore('session-token');
    const api = {
      session: vi.fn(),
      logout: vi.fn().mockRejectedValue(new Error('offline')),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api, tokenStore.store);

    await expect(store.signOut()).rejects.toThrow('offline');

    expect(tokenStore.store.clear).toHaveBeenCalledOnce();
    expect(tokenStore.value()).toBe('');
  });

  it('still logs out and reports when the session token cannot be cleared', async () => {
    const tokenStore = createTokenStore('session-token');
    tokenStore.store.clear.mockReturnValue(false);
    const api = {
      session: vi.fn(),
      logout: vi.fn().mockResolvedValue(guest),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api, tokenStore.store);

    await expect(store.signOut()).rejects.toThrow('could not be cleared');

    expect(api.logout).toHaveBeenCalledOnce();
    expect(tokenStore.value()).toBe('session-token');
  });

  it('fails closed when session bootstrap fails', async () => {
    adminToken.set('prior-token');
    const clearToken = vi.spyOn(adminToken, 'clear');
    const api = {
      session: vi.fn().mockRejectedValue(new Error('offline')),
      logout: vi.fn(),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api, adminToken);
    await store.bootstrap();
    expect(get(store)).toMatchObject({
      authenticated: false,
      user: null,
      error: 'offline',
    });
    expect(clearToken).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)).toBe('prior-token');
  });
});
