import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, parseApiJson } from './client';
describe('application API client', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });
  it('preserves every id64 as text before JSON parsing', () => {
    expect(
      parseApiJson(
        '{"id64":9223372036854775807,"system_id64":10477373803,"score":12}',
      ),
    ).toEqual({
      id64: '9223372036854775807',
      system_id64: '10477373803',
      score: 12,
    });
  });
  it('uses included credentials and injects the session admin token', async () => {
    sessionStorage.setItem('ed_admin_token', 'secret');
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{"ok":true}'));
    await apiRequest('/api/admin/status');
    expect(fetcher).toHaveBeenCalledWith(
      '/api/admin/status',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({ 'X-Admin-Token': 'secret' }),
      }),
    );
  });
  it('unwraps system envelopes and exposes structured errors', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response('{"system":{"id64":9007199254740993,"name":"Far"}}'),
      )
      .mockResolvedValueOnce(new Response('{"detail":"no"}', { status: 403 }));
    await expect(apiRequest('/api/system/1')).resolves.toEqual({
      id64: '9007199254740993',
      name: 'Far',
    });
    const failure = apiRequest('/api/private');
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await failure.catch((error) =>
      expect(error).toMatchObject({
        status: 403,
        path: '/api/private',
        body: '{"detail":"no"}',
      }),
    );
  });
});
