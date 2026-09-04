import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import {
  ApiError,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
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
  beforeEach(() => vi.resetAllMocks());

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

  it('deduplicates /api and rejects cross-origin base URLs', () => {
    expect(canonicalApiPath('/health')).toBe('/api/health');
    expect(canonicalApiPath('/api/health')).toBe('/api/health');
    expect(() => canonicalApiPath('https://example.test/api/health')).toThrow(
      'same-origin',
    );
  });

  it('limits admin tokens to the explicit endpoint policy', async () => {
    sessionStorage.setItem('ed_admin_token', ' token-123 ');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response('{}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    );
    await apiRequest('/admin/data-status');
    await apiRequest('/auth/session', {
      headers: { 'X-Admin-Token': 'must-not-leak' },
    });
    expect(
      new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-Admin-Token'),
    ).toBe('token-123');
    expect(
      new Headers(fetchMock.mock.calls[1][1]?.headers).has('X-Admin-Token'),
    ).toBe(false);
    expect(adminEndpointClass('/api/operator/source-runs')).toBe('operator');
    expect(adminEndpointClass('/observations/facts', 'POST')).toBe('operator');
    expect(adminEndpointClass('/observations/facts', 'GET')).toBeNull();
    expect(adminEndpointClass('/api/static/app.js')).toBeNull();
    fetchMock.mockRestore();
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

    await expect(getHealth()).rejects.toMatchObject({
      message: 'This operation was aborted',
      name: 'AbortError',
    });
  });
});
