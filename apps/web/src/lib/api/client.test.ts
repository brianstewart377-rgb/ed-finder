import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import { getAuthSession, getHealth } from './client';

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
      credentials: 'same-origin',
      signal: controller.signal,
      throwOnError: true,
    });
  });

  it('calls the generated session SDK and normalises structured failures', async () => {
    mockedGetAuthSession.mockRejectedValue({ detail: 'Session unavailable' });

    await expect(getAuthSession()).rejects.toThrow('Session unavailable');
    expect(mockedGetAuthSession).toHaveBeenCalledWith({
      credentials: 'same-origin',
      signal: undefined,
      throwOnError: true,
    });
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
