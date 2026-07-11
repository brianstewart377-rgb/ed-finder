import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('observed evidence operator token forwarding', () => {
  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('forwards the shared admin token on observed evidence mutations', async () => {
    sessionStorage.setItem('ed_admin_token', 'token-123');

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        observation_id: 'obs_1',
        deleted: true,
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.createObservedFact({
      system_id64: 42,
      source: 'manual',
      fact_type: 'note',
      subject_type: 'system',
      status: 'unverified',
      notes: 'created',
    });
    await api.updateObservedFact('obs_1', { status: 'confirmed' });
    await api.deleteObservedFact('obs_1');

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(3);

    for (const [, init] of calls) {
      expect(init?.headers).toMatchObject({ 'X-Admin-Token': 'token-123' });
    }
  });
});
