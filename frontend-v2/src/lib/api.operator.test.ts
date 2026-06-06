import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('operator API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('call Stage 19 operator endpoints with GET/read-only requests only', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({}),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.operatorSafetyGates('token-123');
    await api.operatorSourceRuns('token-123', 25);
    await api.operatorSourceRunDetail('token-123', 'source/run 1');
    await api.operatorSourceRunArtifacts('token-123', 'source/run 1');
    await api.operatorSourceRunBridge('token-123', 'source/run 1');
    await api.operatorSourceRunStagingImpact('token-123', 'source/run 1', 25);
    await api.operatorDiagnosticRows('token-123', { sourceRunKey: 'source/run 1', limit: 25 });

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(7);
    expect(calls.map(([url]) => String(url))).toEqual([
      '/api/operator/safety-gates',
      '/api/operator/source-runs?limit=25',
      '/api/operator/source-run-detail?source_run_key=source%2Frun+1',
      '/api/operator/source-run-artifacts?source_run_key=source%2Frun+1',
      '/api/operator/source-run-bridge?source_run_key=source%2Frun+1',
      '/api/operator/source-run-staging-impact?source_run_key=source%2Frun+1&limit=25',
      '/api/operator/diagnostic-staging-rows?limit=25&source_run_key=source%2Frun+1',
    ]);

    for (const [, init] of calls) {
      expect(['GET', undefined]).toContain(init?.method);
      expect(String(init?.method ?? 'GET')).not.toMatch(/POST|PATCH|DELETE|PUT/i);
      expect(init?.headers).toMatchObject({ 'X-Admin-Token': 'token-123' });
    }
  });
});
