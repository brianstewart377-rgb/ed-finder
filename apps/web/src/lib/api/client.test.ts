import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  apiRequest,
  autocompleteSystems,
  claimOwner,
  getAuthIdentities,
  getAuthSession,
  getHealth,
  getSystem,
  searchExploreSystems,
  startFrontierLink,
  unlinkAuthIdentity,
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
    const sessionRequest = fetchMock.mock.calls[1]?.[0] as string;
    const sessionInit = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(healthRequest).toBeInstanceOf(Request);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    expect(healthRequest.url).toContain('/api/health');
    expect(healthRequest.credentials).toBe('include');
    expect(sessionRequest).toContain('/api/v1/auth/session');
    expect(sessionInit.credentials).toBe('include');
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

  it('uses typed generated Explore operations and normalizes every result id64', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          '{"results":[{"id64":9007199254740993,"name":"Far Reach","x":1,"y":2,"z":3}]}',
          { headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          '{"results":[{"id64":18446744073709551615,"name":"Edge","coords":{"x":4,"y":5,"z":6}}],"count":1}',
          { headers: { 'content-type': 'application/json' } },
        ),
      );

    await expect(autocompleteSystems('Far')).resolves.toMatchObject({
      results: [{ id64: '9007199254740993', name: 'Far Reach' }],
    });
    await expect(
      searchExploreSystems({ galaxy_wide: true, size: 24 }),
    ).resolves.toMatchObject({
      results: [{ id64: '18446744073709551615', name: 'Edge' }],
    });

    const autocompleteRequest = fetchMock.mock.calls[0]?.[0] as Request;
    const searchRequest = fetchMock.mock.calls[1]?.[0] as Request;
    expect(autocompleteRequest.url).toContain(
      '/api/local/autocomplete?q=Far&limit=10',
    );
    expect(searchRequest.url).toContain('/api/local/search');
    expect(await searchRequest.clone().json()).toEqual({
      galaxy_wide: true,
      size: 24,
    });
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

  it('keeps identity management on the credentialed same-origin facade', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse([
          {
            external_identity_id: 'identity-1',
            provider: 'frontier',
            linked_at: '2026-09-09T12:00:00Z',
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse({ authorization_url: 'https://auth.frontierstore.net/auth?state=one' }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ authenticated: true, user: null }),
      );

    await expect(getAuthIdentities()).resolves.toEqual([
      {
        external_identity_id: 'identity-1',
        provider: 'frontier',
        linked_at: '2026-09-09T12:00:00Z',
      },
    ]);
    await expect(startFrontierLink('/')).resolves.toContain(
      'auth.frontierstore.net',
    );
    await expect(unlinkAuthIdentity('identity-1')).resolves.toMatchObject({
      authenticated: true,
    });

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/api/v1/auth/identities',
    );
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
      '/api/v1/auth/frontier/link?return_to=%2F',
    );
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe('POST');
    expect((fetchMock.mock.calls[2]?.[1] as RequestInit).method).toBe('DELETE');
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
    const request = fetchMock.mock.calls[0]?.[0] as string;
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    // /api/v1/auth/owner/claim is not an admin-classified route: the reusable
    // session token must not be attached, and the one-time secret rides only
    // in the body.
    expect(new Headers(init.headers).has('X-Admin-Token')).toBe(false);
    expect(init.body).toBe(
      JSON.stringify({ admin_token: 'one-time-owner-secret' }),
    );
    expect(request).toContain('/api/v1/auth/owner/claim');
  });

  it('re-exports the single shared transport inventory rather than duplicating it', () => {
    expect(LEGACY_ADMIN_ENDPOINTS).toHaveLength(28);
    expect(apiRequest).toBeTypeOf('function');
  });
});
