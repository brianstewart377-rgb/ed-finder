import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
  claimOwner,
  getAuthSession,
  getHealth,
  pullProfileSync,
  pushProfileSync,
} from './client';

const jsonResponse = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { 'content-type': 'application/json', ...init.headers },
  });

const concretePath = (template: string) =>
  template.replace(/\{[^{}]+\}/g, 'test-value');

describe('bootstrap API client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('loads health through the credentialed lossless facade with cancellation', async () => {
    const health = {
      status: 'ok',
      database: 'connected',
      version: 'test',
      build_sha: 'abc',
    };
    const controller = new AbortController();
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(health));

    await expect(getHealth(controller.signal)).resolves.toEqual(health);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({
        credentials: 'include',
        signal: controller.signal,
      }),
    );
    expect(
      new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Accept'),
    ).toBe('application/json');
  });

  it('preserves status, path, and lossless body metadata for session failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        '{"detail":"Session unavailable","system_id64":18446744073709551615}',
        {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'content-type': 'application/json' },
        },
      ),
    );

    await expect(getAuthSession()).rejects.toMatchObject({
      status: 503,
      path: '/api/auth/session',
      body: {
        detail: 'Session unavailable',
        system_id64: '18446744073709551615',
      },
      message: 'Session unavailable',
    });
  });

  it('preserves JSON, text, and empty health failure bodies', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    fetchMock.mockResolvedValueOnce(
      new Response(
        '{"detail":"No health","system_id64":18446744073709551615}',
        {
          status: 403,
          headers: { 'content-type': 'application/json' },
        },
      ),
    );
    await expect(getHealth()).rejects.toMatchObject({
      status: 403,
      path: '/api/health',
      body: { detail: 'No health', system_id64: '18446744073709551615' },
      message: 'No health',
    });

    fetchMock.mockResolvedValueOnce(
      new Response('gateway down', { status: 502 }),
    );
    await expect(getHealth()).rejects.toMatchObject({
      status: 502,
      path: '/api/health',
      body: 'gateway down',
      message: 'gateway down',
    });

    fetchMock.mockResolvedValueOnce(
      new Response(null, { status: 503, statusText: 'Unavailable' }),
    );
    await expect(getHealth()).rejects.toMatchObject({
      status: 503,
      path: '/api/health',
      body: '',
      message: 'Unavailable',
    });
  });

  it('normalises network failures while preserving their cause', async () => {
    const network = new Error('socket closed');
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(network);

    const failure = await getHealth().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      status: 0,
      path: '/api/health',
      body: '',
      message: 'Network request failed on /api/health',
      cause: network,
    });
  });

  it('deduplicates /api and rejects cross-origin base URLs', () => {
    expect(canonicalApiPath('/health')).toBe('/api/health');
    expect(canonicalApiPath('/api/health')).toBe('/api/health');
    expect(() => canonicalApiPath('https://example.test/api/health')).toThrow(
      'same-origin',
    );
  });

  it('matches the exact method-specific legacy require_admin inventory', () => {
    expect(LEGACY_ADMIN_ENDPOINTS).toHaveLength(28);
    for (const endpoint of LEGACY_ADMIN_ENDPOINTS) {
      expect(
        adminEndpointClass(
          `${concretePath(endpoint.path)}?ignored=yes`,
          endpoint.method,
        ),
      ).toBe(endpoint.endpointClass);
    }

    expect(adminEndpointClass('/api/admin/not-an-endpoint')).toBeNull();
    expect(adminEndpointClass('/api/operator/not-an-endpoint')).toBeNull();
    expect(adminEndpointClass('/api/cache/stats', 'POST')).toBeNull();
    expect(adminEndpointClass('/api/evidence/records', 'GET')).toBeNull();
    expect(adminEndpointClass('/api/observations/facts/id', 'POST')).toBeNull();
    expect(adminEndpointClass('/api/static/app.js')).toBeNull();
  });

  it('injects only the bounded session token on allowlisted routes', async () => {
    sessionStorage.setItem('ed_admin_token', ' token-123 ');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => jsonResponse({}));

    for (const endpoint of LEGACY_ADMIN_ENDPOINTS) {
      await apiRequest(concretePath(endpoint.path), {
        method: endpoint.method,
        headers: { 'X-Admin-Token': 'caller-secret-must-be-replaced' },
      });
    }
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).get('X-Admin-Token')).toBe('token-123');
    }

    fetchMock.mockClear();
    await apiRequest('/admin/not-an-endpoint', {
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    await apiRequest('/observations/facts', {
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    await claimOwner('one-time-owner-link-secret');
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).has('X-Admin-Token')).toBe(false);
    }
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/auth/owner/claim');
    expect(fetchMock.mock.calls[2]?.[1]?.body).toBe(
      JSON.stringify({ admin_token: 'one-time-owner-link-secret' }),
    );
  });

  it('uses the same-origin facade for profile pull/push without an admin header', async () => {
    sessionStorage.setItem('ed_admin_token', 'must-not-leak');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse({ blob: {}, updated_at: 'pull-time', blob_bytes: 2 }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ updated_at: 'push-time', blob_bytes: 42 }),
      );

    await pullProfileSync('profile-key-1234567890');
    await pushProfileSync('profile-key-1234567890', {
      version: 1,
      exported_at: 'now',
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/profile/sync/profile-key-1234567890',
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/profile/sync/profile-key-1234567890',
    );
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'PUT',
      body: JSON.stringify({ blob: { version: 1, exported_at: 'now' } }),
    });
    for (const [, init] of fetchMock.mock.calls)
      expect(new Headers(init?.headers).has('X-Admin-Token')).toBe(false);
  });

  it('preserves the profile endpoint problem body on a 413 response', async () => {
    const problem = {
      type: 'about:blank',
      title: 'Profile blob too large',
      status: 413,
      detail: 'Profile blob too large: 1048577 bytes (max 1048576).',
      instance: '/api/profile/sync/profile-key-1234567890',
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(problem, {
        status: 413,
        headers: { 'content-type': 'application/problem+json' },
      }),
    );

    await expect(
      pushProfileSync('profile-key-1234567890', { oversized: true }),
    ).rejects.toMatchObject({
      status: 413,
      path: '/api/profile/sync/profile-key-1234567890',
      body: problem,
      message: problem.detail,
    });
  });

  it('preserves structured, text, and empty error responses', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    fetchMock.mockResolvedValueOnce(
      new Response('{"detail":"No access","system_id64":9007199254740993}', {
        status: 403,
        headers: { 'content-type': 'application/json' },
      }),
    );
    const error = await apiRequest('/system/9007199254740993').catch(
      (value: unknown) => value,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      path: '/api/system/9007199254740993',
      body: { detail: 'No access', system_id64: '9007199254740993' },
      message: 'No access',
    });

    fetchMock.mockResolvedValueOnce(
      new Response('gateway down', { status: 502 }),
    );
    await expect(apiRequest('/health')).rejects.toMatchObject({
      body: 'gateway down',
    });
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 500 }));
    await expect(apiRequest('/health')).rejects.toMatchObject({ body: '' });
  });

  it('preserves abort failure identity', async () => {
    const aborted = new DOMException(
      'This operation was aborted',
      'AbortError',
    );
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(aborted);

    await expect(getHealth()).rejects.toBe(aborted);
  });
});
