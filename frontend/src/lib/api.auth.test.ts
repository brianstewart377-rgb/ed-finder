import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('Frontier auth API helpers', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('builds sign-in navigation through the configured API base', () => {
    expect(api.frontierLoginUrl('/?view=map#admin')).toBe(
      '/api/auth/frontier/login?return_to=%2F%3Fview%3Dmap%23admin',
    );
  });

  it('honors a non-default API base when starting sign-in', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://api.example.test/custom/');
    vi.resetModules();
    const { frontierLoginUrl } = await import('./api/auth');

    expect(frontierLoginUrl('/#admin')).toBe(
      'https://api.example.test/custom/auth/frontier/login?return_to=%2F%23admin',
    );
  });

  it('uses cookie credentials for session reads and logout', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      json: async () => ({ authenticated: false, user: null, owner_claim_available: false }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.authSession();
    await api.authLogout();

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(String(calls[0][0])).toBe('/api/auth/session');
    expect(calls[0][1]?.credentials).toBe('include');
    expect(String(calls[1][0])).toBe('/api/auth/logout');
    expect(calls[1][1]?.method).toBe('POST');
    expect(calls[1][1]?.credentials).toBe('include');
  });

  it('sends the one-time owner-link secret in the request body, never the URL', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      json: async () => ({
        authenticated: true,
        user: { commander_name: 'Owner Cmdr', is_owner: true },
        owner_claim_available: false,
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.claimOwner('existing-admin-secret');

    const [url, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toBe('/api/auth/owner/claim');
    expect(String(url)).not.toContain('existing-admin-secret');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ admin_token: 'existing-admin-secret' }));
  });
});
