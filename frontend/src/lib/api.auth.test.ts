import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('V3 Frontier auth API helpers', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('builds sign-in navigation through the V3 API contract', () => {
    expect(api.frontierLoginUrl('/?view=map#admin')).toBe(
      '/api/v1/auth/frontier/login?return_to=%2F%3Fview%3Dmap%23admin',
    );
  });

  it('uses cookie credentials for session reads and logout', async () => {
    const fetchMock = vi.fn(async (): Promise<Response> => ({
      ok: true,
      json: async () => ({ authenticated: false, user: null, owner_claim_available: false }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.authSession();
    await api.authLogout();

    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(String(calls[0][0])).toBe('/api/v1/auth/session');
    expect(calls[0][1]?.credentials).toBe('include');
    expect(String(calls[1][0])).toBe('/api/v1/auth/logout');
    expect(calls[1][1]?.method).toBe('POST');
    expect(calls[1][1]?.credentials).toBe('include');
  });

  it('sends the one-time owner secret in the body, never the URL', async () => {
    const fetchMock = vi.fn(async (): Promise<Response> => ({
      ok: true,
      json: async () => ({
        authenticated: true,
        user: {
          account_id: '4ff3ff94-5815-42f0-a89d-66cd87b79155',
          commander_name: null,
          is_owner: true,
        },
        owner_claim_available: false,
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.claimOwner('existing-admin-secret');

    const [url, init] = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toBe('/api/v1/auth/owner/claim');
    expect(String(url)).not.toContain('existing-admin-secret');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ admin_token: 'existing-admin-secret' }));
  });
});

