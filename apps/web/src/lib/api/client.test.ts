import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
  claimOwner,
  getAuthSession,
  getHealth,
} from './client';

vi.mock('./generated/sdk.gen', () => ({
  authSessionApiAuthSessionGet: vi.fn(),
  healthApiHealthGet: vi.fn(),
}));

const mockedGetHealth = vi.mocked(generatedGetHealth);
const mockedGetAuthSession = vi.mocked(generatedGetAuthSession);

describe('bootstrap API client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('calls the generated health SDK with same-origin credentials and cancellation', async () => {
    const health = {
      status: 'ok',
      database: 'connected',
      version: 'test',
      build_sha: 'abc',
    };
    const controller = new AbortController();
    mockedGetHealth.mockResolvedValue({
      data: health,
      request: new Request('http://localhost/api/health', {
        signal: controller.signal,
      }),
      response: new Response(),
    });

    await expect(getHealth(controller.signal)).resolves.toEqual(health);
    expect(mockedGetHealth).toHaveBeenCalledWith({
      credentials: 'include',
      signal: controller.signal,
      throwOnError: true,
    });
  });

  it('calls the generated session SDK and normalises structured failures', async () => {
    mockedGetAuthSession.mockRejectedValue({ detail: 'Session unavailable' });

    await expect(getAuthSession()).rejects.toThrow('Session unavailable');
    expect(mockedGetAuthSession).toHaveBeenCalledWith({
      credentials: 'include',
      signal: undefined,
      throwOnError: true,
    });
  });

  it('normalises generated JSON, text, and empty response failures', async () => {
    mockedGetHealth.mockRejectedValueOnce({
      response: new Response(
        '{"detail":"No health","system_id64":18446744073709551615}',
        {
          status: 403,
          headers: { 'content-type': 'application/json' },
        },
      ),
    });
    await expect(getHealth()).rejects.toMatchObject({
      status: 403,
      path: '/api/health',
      body: { detail: 'No health', system_id64: '18446744073709551615' },
      message: 'No health',
    });

    mockedGetHealth.mockRejectedValueOnce({
      response: new Response('gateway down', { status: 502 }),
    });
    await expect(getHealth()).rejects.toMatchObject({
      status: 502,
      body: 'gateway down',
      message: 'gateway down',
    });

    mockedGetHealth.mockRejectedValueOnce(
      new Response(null, { status: 503, statusText: 'Unavailable' }),
    );
    await expect(getHealth()).rejects.toMatchObject({
      status: 503,
      body: '',
      message: 'Unavailable',
    });
  });

  it('normalises generated network Errors and object failures with causes', async () => {
    const network = new Error('socket closed');
    mockedGetHealth.mockRejectedValueOnce(network);
    const networkFailure = await getHealth().catch((error: unknown) => error);
    expect(networkFailure).toBeInstanceOf(ApiError);
    expect(networkFailure).toMatchObject({
      status: 0,
      path: '/api/health',
      body: '',
      message: 'socket closed',
      cause: network,
    });

    const objectFailure = {
      status: 429,
      error: { detail: 'bounded' },
      message: 'Rate limited',
    };
    mockedGetHealth.mockRejectedValueOnce(objectFailure);
    await expect(getHealth()).rejects.toMatchObject({
      status: 429,
      body: { detail: 'bounded' },
      message: 'Rate limited',
      cause: objectFailure,
    });
  });

  it('deduplicates /api and rejects cross-origin base URLs', () => {
    expect(canonicalApiPath('/health')).toBe('/api/health');
    expect(canonicalApiPath('/api/health')).toBe('/api/health');
    expect(canonicalApiPath('/api?probe=1')).toBe('/api?probe=1');
    expect(canonicalApiPath('/api/admin/../auth/session')).toBe(
      '/api/auth/session',
    );
    expect(() => canonicalApiPath('https://example.test/api/health')).toThrow(
      'same-origin',
    );
    expect(() => canonicalApiPath('/admin/../../outside')).toThrow(
      'stay under /api',
    );
  });

  it('limits admin tokens to the explicit endpoint policy', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, ' token-123 ');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response('{}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    );
    await apiRequest('/admin/data-status');
    await apiRequest('/operator/source-runs');
    await apiRequest('/status');
    await apiRequest('/cache/clear', { method: 'POST' });
    await apiRequest('/enrichment/station-status');
    await apiRequest('/observations/facts', { method: 'POST' });
    await apiRequest('/observations/facts/observation-1', { method: 'PATCH' });
    await apiRequest('/observations/facts/observation-1', {
      method: 'DELETE',
    });
    await apiRequest('/observations/facts', {
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    await apiRequest('/auth/session', {
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    await apiRequest('/observations/facts-export', {
      method: 'POST',
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    await apiRequest('/admin/%2e%2e/auth/session');
    await apiRequest('/observations/facts/../compare', { method: 'POST' });
    await apiRequest('/operator/..\\auth/session');

    for (const call of fetchMock.mock.calls.slice(0, 8))
      expect(new Headers(call[1]?.headers).get('X-Admin-Token')).toBe(
        'token-123',
      );
    for (const call of fetchMock.mock.calls.slice(8))
      expect(new Headers(call[1]?.headers).has('X-Admin-Token')).toBe(false);
    expect(
      fetchMock.mock.calls.every((call) => call[1]?.credentials === 'include'),
    ).toBe(true);
    expect(adminEndpointClass('/api/operator/source-runs')).toBe('operator');
    expect(adminEndpointClass('/observations/facts', 'POST')).toBe('operator');
    expect(adminEndpointClass('/observations/facts', 'GET')).toBeNull();
    expect(adminEndpointClass('/observations/facts-export', 'POST')).toBeNull();
    expect(adminEndpointClass('/admin/../auth/session')).toBeNull();
    expect(
      adminEndpointClass('/observations/facts/../compare', 'POST'),
    ).toBeNull();
    expect(adminEndpointClass('/api/static/app.js')).toBeNull();
    expect(fetchMock.mock.calls[11][0]).toBe('/api/auth/session');
    expect(fetchMock.mock.calls[12][0]).toBe('/api/observations/compare');
    expect(fetchMock.mock.calls[13][0]).toBe('/api/auth/session');
  });

  it('does not preserve a caller-supplied header when no session token exists', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await apiRequest('/admin/data-status', {
      headers: { 'X-Admin-Token': 'caller-supplied' },
    });

    expect(
      new Headers(fetchMock.mock.calls[0][1]?.headers).has('X-Admin-Token'),
    ).toBe(false);
  });

  it('submits owner-claim credentials only in the JSON body', async () => {
    sessionStorage.setItem(ADMIN_TOKEN_SESSION_KEY, 'prior-token');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await claimOwner('new-owner-token');

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe('/api/auth/owner/claim');
    expect(String(path)).not.toContain('new-owner-token');
    expect(JSON.parse(String(init?.body))).toEqual({
      admin_token: 'new-owner-token',
    });
    expect(new Headers(init?.headers).has('X-Admin-Token')).toBe(false);
  });

  it('preserves structured, text, and empty error responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
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

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('gateway down', { status: 502 }),
    );
    await expect(apiRequest('/health')).rejects.toMatchObject({
      body: 'gateway down',
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(null, { status: 500 }),
    );
    await expect(apiRequest('/health')).rejects.toMatchObject({ body: '' });
    vi.restoreAllMocks();
  });

  it('preserves abort failure identity when normalising cross-realm errors', async () => {
    const aborted = new DOMException(
      'This operation was aborted',
      'AbortError',
    );
    mockedGetHealth.mockRejectedValue(aborted);

    await expect(getHealth()).rejects.toBe(aborted);
  });
});
