import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('admin API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls cron status with a GET/read-only request only', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({}),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.adminCronStatus('token-123');

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(1);
    expect(String(calls[0][0])).toBe('/api/admin/cron-status');
    expect(['GET', undefined]).toContain(calls[0][1]?.method);
    expect(String(calls[0][1]?.method ?? 'GET')).not.toMatch(/POST|PATCH|DELETE|PUT/i);
    expect(calls[0][1]?.headers).toMatchObject({ 'X-Admin-Token': 'token-123' });
  });

  it('calls approved admin operations through the token-gated admin endpoint', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        ok: true,
        message: 'Telemetry hot-log snapshot completed.',
        operation_key: 'telemetry_hot_log_snapshot',
        job_run_id: 77,
        status: 'completed',
        exit_code: 0,
        output_text: 'snapshot output',
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.adminRunOperation('token-123', 'telemetry_hot_log_snapshot');

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(1);
    expect(String(calls[0][0])).toBe('/api/admin/operations/telemetry_hot_log_snapshot');
    expect(calls[0][1]?.method).toBe('POST');
    expect(calls[0][1]?.headers).toMatchObject({ 'X-Admin-Token': 'token-123' });
  });

  it('calls admin operation history through the token-gated read-only endpoint', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        schema_version: 'admin_operation_history/v1',
        read_only: true,
        operations: [],
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    await api.adminOperationHistory('token-123', 5);

    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit | undefined]>;
    expect(calls).toHaveLength(1);
    expect(String(calls[0][0])).toBe('/api/admin/operations/history?limit=5');
    expect(['GET', undefined]).toContain(calls[0][1]?.method);
    expect(String(calls[0][1]?.method ?? 'GET')).not.toMatch(/POST|PATCH|DELETE|PUT/i);
    expect(calls[0][1]?.headers).toMatchObject({ 'X-Admin-Token': 'token-123' });
  });
});
