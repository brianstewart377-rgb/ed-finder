import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('api.health', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls the /api/health endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', database: 'connected', version: 'test' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const response = await api.health();

    expect(response.status).toBe('ok');
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'application/json',
          'Content-Type': 'application/json',
        }),
      }),
    );
  });
});
