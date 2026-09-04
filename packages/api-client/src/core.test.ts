import { afterEach, describe, expect, it, vi } from 'vitest';

async function loadCore() {
  vi.resetModules();
  return import('./core');
}

describe('API transport', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('uses the same-origin API default and preserves absolute URLs', async () => {
    const { API_BASE, DEFAULT_API_BASE, resolveApiUrl } = await loadCore();

    expect(API_BASE).toBe('/api');
    expect(DEFAULT_API_BASE).toBe('/api');
    expect(resolveApiUrl('/systems/42')).toBe('/api/systems/42');
    expect(resolveApiUrl('https://elsewhere.example.test/status')).toBe(
      'https://elsewhere.example.test/status',
    );
  });

  it('accepts an injected base URL without retaining trailing slashes', async () => {
    const { configureApiBase, resolveApiUrl } = await loadCore();

    expect(configureApiBase('https://api.example.test/custom///')).toBe(
      'https://api.example.test/custom',
    );
    expect(resolveApiUrl('/systems/42')).toBe(
      'https://api.example.test/custom/systems/42',
    );
    expect(configureApiBase(undefined)).toBe('/api');
  });

  it('does not duplicate an explicit /api path when the base already ends in /api', async () => {
    const { resolveApiUrl } = await loadCore();

    expect(resolveApiUrl('/api/system/42')).toBe('/api/system/42');
  });

  it('injects JSON defaults and credentials while allowing caller header overrides', async () => {
    vi.stubEnv('VITE_API_BASE', '/api');
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const { jsonFetch } = await loadCore();

    await jsonFetch('/contract', {
      method: 'POST',
      body: JSON.stringify({ value: 1 }),
      headers: {
        Accept: 'application/vnd.ed-finder+json',
        'X-Contract': 'planner',
      },
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith('/api/contract', {
      credentials: 'include',
      method: 'POST',
      body: '{"value":1}',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/vnd.ed-finder+json',
        'X-Contract': 'planner',
      },
    });
  });

  it('throws an ApiError with the logical path, status, and response body', async () => {
    vi.stubEnv('VITE_API_BASE', '/api');
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"invalid plan"}', {
      status: 422,
      statusText: 'Unprocessable Entity',
    })));
    const { ApiError, jsonFetch } = await loadCore();

    const error = await jsonFetch('/simulate/build').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      name: 'ApiError',
      status: 422,
      path: '/simulate/build',
      body: '{"detail":"invalid plan"}',
      message: 'API 422 on /simulate/build: {"detail":"invalid plan"}',
    });
  });

  it('falls back to statusText when an error response body cannot be read', async () => {
    vi.stubEnv('VITE_API_BASE', '/api');
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      text: vi.fn(async () => Promise.reject(new Error('stream unavailable'))),
    } as unknown as Response)));
    const { jsonFetch } = await loadCore();

    await expect(jsonFetch('/facility-templates')).rejects.toMatchObject({
      status: 503,
      path: '/facility-templates',
      body: 'Service Unavailable',
    });
  });

  it('preserves fetch transport failures unchanged', async () => {
    vi.stubEnv('VITE_API_BASE', '/api');
    const transportError = new TypeError('network offline');
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(transportError)));
    const { jsonFetch } = await loadCore();

    await expect(jsonFetch('/system/42')).rejects.toBe(transportError);
  });
});
