import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ADMIN_TOKEN_SESSION_KEY,
  LEGACY_ADMIN_ENDPOINTS,
  apiRequest,
  claimOwner,
  getAuthSession,
  getHealth,
} from './client';

const response = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { 'content-type': 'application/json', ...init.headers },
  });

describe('typed V3 API facade', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('loads typed bootstrap resources through the shared credentialed transport', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({ status: 'ok', database: 'connected' }))
      .mockResolvedValueOnce(response({ authenticated: false, user: null }));
    const signal = new AbortController().signal;

    await expect(getHealth(signal)).resolves.toMatchObject({ status: 'ok' });
    await expect(getAuthSession(signal)).resolves.toMatchObject({
      authenticated: false,
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/health',
      expect.objectContaining({
        credentials: 'include',
        signal,
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/auth/session',
      expect.objectContaining({
        credentials: 'include',
        signal,
      }),
    );
  });

  it('keeps the one-time owner secret in the body and off reusable headers', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'session-admin');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response({
        authenticated: true,
        user: { commander_name: 'CMDR', is_owner: true },
      }),
    );

    await claimOwner('one-time-owner-secret');
    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has('X-Admin-Token')).toBe(false);
    expect(init?.body).toBe(
      JSON.stringify({ admin_token: 'one-time-owner-secret' }),
    );
  });

  it('re-exports the single shared transport inventory rather than duplicating it', () => {
    expect(LEGACY_ADMIN_ENDPOINTS).toHaveLength(28);
    expect(apiRequest).toBeTypeOf('function');
  });
});
