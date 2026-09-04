/** Application-facing API facade. Generated declarations stay behind this module. */
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import type { AuthSessionResponse, HealthResponse } from './generated';
import type { Id64 } from '$lib/domain/id64';
import { parseId64 } from '$lib/domain/id64';
import { parseLosslessJson } from './lossless-json';

export const ADMIN_TOKEN_SESSION_KEY = 'ed_admin_token';
const generatedOptions = (signal?: AbortSignal) => ({
  credentials: 'include' as const,
  signal,
  throwOnError: true as const,
});

export function canonicalApiPath(path: string): string {
  if (/^https?:\/\//i.test(path))
    throw new TypeError('API paths must be same-origin');
  const rooted = path.startsWith('/') ? path : `/${path}`;
  return rooted === '/api' || rooted.startsWith('/api/')
    ? rooted
    : `/api${rooted}`;
}

export type AdminEndpointClass =
  'admin' | 'operator' | 'owner-maintenance' | null;
export function adminEndpointClass(
  path: string,
  method = 'GET',
): AdminEndpointClass {
  const canonical = canonicalApiPath(path).split(/[?#]/, 1)[0];
  if (canonical.startsWith('/api/admin/')) return 'admin';
  if (canonical.startsWith('/api/operator/')) return 'operator';
  if (
    canonical === '/api/status' ||
    canonical.startsWith('/api/cache/') ||
    canonical.startsWith('/api/enrichment/')
  )
    return 'owner-maintenance';
  if (
    canonical.startsWith('/api/observations/facts') &&
    ['POST', 'PATCH', 'DELETE'].includes(method.toUpperCase())
  )
    return 'operator';
  return null;
}

function sessionAdminToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    public readonly body: unknown,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = 'ApiError';
  }
}

function usefulMessage(
  status: number,
  path: string,
  body: unknown,
  statusText: string,
): string {
  let detail = '';
  if (typeof body === 'string') detail = body;
  else if (body && typeof body === 'object') {
    const candidate =
      (body as { detail?: unknown; message?: unknown }).detail ??
      (body as { message?: unknown }).message;
    if (typeof candidate === 'string') detail = candidate;
  }
  return (
    detail.trim() ||
    statusText.trim() ||
    `API request failed (${status}) on ${path}`
  );
}

async function readResponse(
  response: Response,
  path: string,
): Promise<unknown> {
  const text = await response.text();
  if (!text) return '';
  if (
    !(response.headers.get('content-type') ?? '').toLowerCase().includes('json')
  )
    return text;
  try {
    return parseLosslessJson(text);
  } catch (cause) {
    throw new ApiError(
      response.status,
      path,
      text,
      'API returned invalid JSON',
      { cause },
    );
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const canonicalPath = canonicalApiPath(path);
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  if (init.body != null && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  if (adminEndpointClass(canonicalPath, init.method ?? 'GET')) {
    const token = sessionAdminToken();
    if (token) headers.set('X-Admin-Token', token);
  } else headers.delete('X-Admin-Token');
  let response: Response;
  try {
    response = await fetch(canonicalPath, {
      ...init,
      credentials: 'include',
      headers,
    });
  } catch (cause) {
    throw new ApiError(
      0,
      canonicalPath,
      '',
      `Network request failed on ${canonicalPath}`,
      { cause },
    );
  }
  const body = await readResponse(response, canonicalPath);
  if (!response.ok)
    throw new ApiError(
      response.status,
      canonicalPath,
      body,
      usefulMessage(response.status, canonicalPath, body, response.statusText),
    );
  return body as T;
}

async function runGenerated<T>(
  path: string,
  request: () => Promise<{ data: T }>,
): Promise<T> {
  try {
    return (await request()).data;
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    if (cause instanceof Error) throw cause;
    const candidate = cause as {
      status?: unknown;
      error?: unknown;
      message?: unknown;
      detail?: unknown;
      name?: unknown;
    } | null;
    if (
      candidate?.name === 'AbortError' &&
      typeof candidate.message === 'string'
    ) {
      const aborted = new Error(candidate.message);
      aborted.name = 'AbortError';
      throw aborted;
    }
    const detail = candidate?.detail ?? candidate?.error;
    const message =
      typeof candidate?.message === 'string'
        ? candidate.message
        : typeof candidate?.detail === 'string'
          ? candidate.detail
          : 'API request failed';
    throw new ApiError(
      typeof candidate?.status === 'number' ? candidate.status : 0,
      path,
      detail ?? '',
      message,
      { cause },
    );
  }
}

export const getHealth = (signal?: AbortSignal): Promise<HealthResponse> =>
  runGenerated('/api/health', () =>
    generatedGetHealth(generatedOptions(signal)),
  );
export const getAuthSession = (
  signal?: AbortSignal,
): Promise<AuthSessionResponse> =>
  runGenerated('/api/auth/session', () =>
    generatedGetAuthSession(generatedOptions(signal)),
  );

export async function getSystem<T extends Record<string, unknown>>(
  id64: Id64,
): Promise<T> {
  const response = await apiRequest<{ record?: T; system: T }>(
    `/system/${parseId64(id64)}`,
  );
  return response.record ?? response.system;
}

export function optimiserCandidates<
  TResponse,
  TRequest extends Record<string, unknown>,
>(request: TRequest): Promise<TResponse> {
  return apiRequest('/optimiser/candidates', {
    method: 'POST',
    body: JSON.stringify({
      max_candidates: 5,
      allow_estimated_data: true,
      run_preview: true,
      include_ranking: true,
      ...request,
    }),
  });
}

export const authLogout = <T = AuthSessionResponse>(): Promise<T> =>
  apiRequest('/auth/logout', { method: 'POST' });
export const claimOwner = <T = AuthSessionResponse>(
  adminToken: string,
): Promise<T> =>
  apiRequest('/auth/owner/claim', {
    method: 'POST',
    body: JSON.stringify({ admin_token: adminToken }),
  });
export const frontierLoginUrl = (returnTo: string): string =>
  `/api/auth/frontier/login?return_to=${encodeURIComponent(returnTo)}`;
