import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  apiRequest,
  claimOwner,
  getAuthSession,
  getHealth,
  getSystem,
} from './client';
// Allowed only in a .test. file: exercise the generated client configuration
// (interceptors) the facade installs, on a route the facade does not wrap.
import { statusApiStatusGet } from './generated/sdk.gen';

const jsonResponse = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { 'content-type': 'application/json', ...init.headers },
  });

describe('typed V3 API facade over the generated Hey API SDK', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('delegates ordinary bootstrap operations to the generated SDK over the credentialed same-origin transport', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse({ status: 'ok', database: 'connected' }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ authenticated: false, user: null }),
      );

    await expect(getHealth()).resolves.toMatchObject({ status: 'ok' });
    await expect(getAuthSession()).resolves.toMatchObject({
      authenticated: false,
    });

    // The generated client-fetch transport dispatches a single Request object,
    // not a (url, init) pair — proving the facade delegates to the generated
    // operation rather than hand-rolling the fetch.
    const healthRequest = fetchMock.mock.calls[0]?.[0] as Request;
    const sessionRequest = fetchMock.mock.calls[1]?.[0] as Request;
    expect(healthRequest).toBeInstanceOf(Request);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    expect(healthRequest.url).toContain('/api/health');
    expect(healthRequest.credentials).toBe('include');
    expect(sessionRequest.url).toContain('/api/auth/session');
    expect(sessionRequest.credentials).toBe('include');
  });

  it('preserves oversized id64 identifiers losslessly through the application facade', async () => {
    // 18446744073709551615 (uint64 max) is far beyond Number.MAX_SAFE_INTEGER.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"system":{"id64":18446744073709551615,"name":"Deep"}}', {
        headers: { 'content-type': 'application/json' },
      }),
    );

    const system = await getSystem('18446744073709551615' as never);
    expect(system.id64).toBe('18446744073709551615');
  });

  it('raises a structured ApiError carrying status and path on a non-2xx response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'unavailable' }, { status: 503 }),
    );

    const error = await getHealth().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).path).toContain('/api/health');
  });

  it('injects the bounded session admin token only for require_admin routes', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'session-admin');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ ok: true }));

    // /api/status is in the require_admin inventory.
    await statusApiStatusGet({ throwOnError: true });
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.headers.get('X-Admin-Token')).toBe('session-admin');
  });

  it('keeps the one-time owner secret in the body and off reusable headers', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'session-admin');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        authenticated: true,
        user: { commander_name: 'CMDR', is_owner: true },
      }),
    );

    await claimOwner('one-time-owner-secret');
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    // /api/auth/owner/claim is not an admin-classified route: the reusable
    // session token must not be attached, and the one-time secret rides only
    // in the body.
    expect(request.headers.has('X-Admin-Token')).toBe(false);
    expect(await request.clone().text()).toBe(
      JSON.stringify({ admin_token: 'one-time-owner-secret' }),
    );
  });

  it('re-exports the single shared transport inventory rather than duplicating it', () => {
    expect(LEGACY_ADMIN_ENDPOINTS).toHaveLength(28);
    expect(apiRequest).toBeTypeOf('function');
  });
});
