import { get } from 'svelte/store';
import { describe, expect, it, vi } from 'vitest';
import { createAuthStore } from './auth';

const guest = {
  authenticated: false,
  user: null,
  owner_claim_available: false,
};

describe('auth store', () => {
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
    const store = createAuthStore(api);
    await store.claimOwner(' secret ');
    expect(api.claimOwner).toHaveBeenCalledWith('secret');
    expect(get(store.owner)).toBe(true);
  });

  it('fails closed when session bootstrap fails', async () => {
    const api = {
      session: vi.fn().mockRejectedValue(new Error('offline')),
      logout: vi.fn(),
      claimOwner: vi.fn(),
    };
    const store = createAuthStore(api);
    await store.bootstrap();
    expect(get(store)).toMatchObject({
      authenticated: false,
      user: null,
      error: 'offline',
    });
  });
});
