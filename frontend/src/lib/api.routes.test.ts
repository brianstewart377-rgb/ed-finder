import { afterEach, describe, expect, it, vi } from 'vitest';
import { getPersonalTrail, getRoute, importSpanshRoute, listExpeditions, listRoutes } from './api/routes';

afterEach(() => vi.unstubAllGlobals());

describe('route API client', () => {
  it('scopes route reads to the commander sync key', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([input, init]);
      return new Response(JSON.stringify({ routes: [], count: 0 }), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    await listRoutes('sync-key-1234567890', 'spansh');
    await getRoute('12345678-1234-5678-1234-567812345678', 'sync-key-1234567890');
    await getPersonalTrail('sync-key-1234567890', '2026-01-01T00:00:00Z', '2026-08-31T00:00:00Z');
    await listExpeditions('sync-key-1234567890');
    expect(String(calls[0]?.[0])).toContain('/routes/list?commander_id=sync-key-1234567890&type=spansh');
    expect(String(calls[1]?.[0])).toContain('commander_id=sync-key-1234567890');
    expect(String(calls[2]?.[0])).toContain('from_date=2026-01-01T00%3A00%3A00Z');
    expect(String(calls[3]?.[0])).toContain('/routes/expeditions?commander_id=sync-key-1234567890');
  });

  it('posts Spansh exact/neutron/carrier imports', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([input, init]);
      return new Response(JSON.stringify({}), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    await importSpanshRoute({
      commander_id: 'sync-key-1234567890',
      name: 'Neutron route',
      route_mode: 'neutron',
      waypoints: [{ order: 0, system_name: 'Sol', bookmarked: false }],
    });
    const init = calls[0]?.[1];
    expect(init?.method).toBe('POST');
    expect(String(init?.body)).toContain('"route_mode":"neutron"');
  });
});
