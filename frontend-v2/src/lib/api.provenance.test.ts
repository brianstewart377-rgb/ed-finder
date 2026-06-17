import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';


describe('provenance cockpit API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('call the Stage 20B provenance endpoint with a GET/read-only request only', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({}),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.provenanceCockpit(12866676218109);

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(1);
    expect(String(calls[0][0])).toBe('/api/colony-planner/system/12866676218109/provenance-cockpit');
    expect(['GET', undefined]).toContain(calls[0][1]?.method);
    expect(String(calls[0][1]?.method ?? 'GET')).not.toMatch(/POST|PATCH|DELETE|PUT/i);
  });
});
