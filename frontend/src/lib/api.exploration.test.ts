import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('exploration API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts observations to /exploration/import', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        sync_key: 'a'.repeat(32),
        status: 'succeeded',
        summary: {
          observations_received: 1,
          observations_staged: 1,
          duplicates_skipped: 0,
          event_counts: { Scan: 1 },
        },
      }),
      text: async () => JSON.stringify({
        sync_key: 'a'.repeat(32),
        status: 'succeeded',
        summary: {
          observations_received: 1,
          observations_staged: 1,
          duplicates_skipped: 0,
          event_counts: { Scan: 1 },
        },
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    const receipt = await api.importExploration({
      sync_key: 'a'.repeat(32),
      source: 'journal',
      observations: [{
        observation_key: 'b'.repeat(32),
        event_type: 'Scan',
        observed_at: '2026-08-08T09:00:00Z',
        system_id64: '1000',
        payload: {},
      }],
    });

    expect(receipt.summary.observations_staged).toBe(1);
    const [url, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toContain('/exploration/import');
    expect(init?.method).toBe('POST');
  });

  it('fetches facts by sync key', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        sync_key: 'a'.repeat(32),
        facts: [],
      }),
      text: async () => JSON.stringify({
        sync_key: 'a'.repeat(32),
        facts: [],
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    const facts = await api.getExplorationFacts('a'.repeat(32), {
      limit: 100,
      event_type: ['FSDJump', 'Scan'],
    });

    expect(facts.sync_key).toBe('a'.repeat(32));
    const [url] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toContain(`/exploration/facts/${'a'.repeat(32)}`);
    expect(String(url)).toContain('limit=100');
    expect(String(url)).toContain('event_type=FSDJump');
  });

  it('queries trail, viewport, selected-system summary, and Codex projections', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ url: String(input) }),
      text: async () => JSON.stringify({ url: String(input) }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);
    const syncKey = 'a'.repeat(32);

    await api.getExplorationTrail(syncKey, { limit: 250 });
    await api.getExplorationViewportVisits(syncKey, {
      min_x: 0, max_x: 1, min_y: 0, max_y: 1, min_z: 0, max_z: 1,
    }, 2);
    await api.getExplorationSummary(syncKey, 42);
    await api.getExplorationCodexByRegion(syncKey);

    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((url) => url.includes('/exploration/trail?'))).toBe(true);
    expect(urls.some((url) => url.includes('/exploration/viewport-visits?') && url.includes('zoom=2'))).toBe(true);
    expect(urls.some((url) => url.includes('/exploration/summary?') && url.includes('system_id64=42'))).toBe(true);
    expect(urls.some((url) => url.includes('/exploration/codex-by-region?'))).toBe(true);
  });
});
