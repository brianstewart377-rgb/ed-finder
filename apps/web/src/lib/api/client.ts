/** Stable application-facing bootstrap API backed by the generated Hey API SDK. */
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import type { AuthSessionResponse, HealthResponse } from './generated';

const requestOptions = (signal?: AbortSignal) => ({
  credentials: 'same-origin' as const,
  signal,
  throwOnError: true as const,
});

function normaliseFailure(error: unknown): Error {
  if (error instanceof Error) return error;
  if (typeof error === 'string' && error.trim()) return new Error(error);
  if (error && typeof error === 'object' && 'message' in error) {
    const message = error.message;
    if (typeof message === 'string' && message.trim()) {
      const normalised = new Error(message);
      if ('name' in error && typeof error.name === 'string')
        normalised.name = error.name;
      return normalised;
    }
  }
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = error.detail;
    if (typeof detail === 'string' && detail.trim()) return new Error(detail);
  }
  return new Error('Bootstrap API request failed');
}

async function runRequest<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (error) {
    throw normaliseFailure(error);
  }
}

export const getHealth = (signal?: AbortSignal): Promise<HealthResponse> =>
  runRequest(
    async () => (await generatedGetHealth(requestOptions(signal))).data,
  );

export const getAuthSession = (
  signal?: AbortSignal,
): Promise<AuthSessionResponse> =>
  runRequest(
    async () => (await generatedGetAuthSession(requestOptions(signal))).data,
  );
