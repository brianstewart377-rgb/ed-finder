/**
 * Application API facade.
 *
 * V3 boundary (issue #579, docs/development/v3-application-stack-decision.md):
 *   FastAPI/OpenAPI
 *     -> generated Hey API SDK operations   (authoritative transport for ordinary ops)
 *       -> this handwritten facade          (application normalization)
 *         -> Svelte components               (import ONLY this facade)
 *
 * Ordinary API operations delegate to the generated Hey API SDK. The generated
 * `client` is configured here (once) so every operation carries the application
 * normalization the raw SDK does not:
 *   - same-origin `credentials: 'include'`;
 *   - bounded session-only `X-Admin-Token` injected only for require_admin routes;
 *   - lossless Id64 preservation BEFORE the SDK's `JSON.parse` can round a token;
 *   - structured `ApiError` on any non-2xx / transport failure.
 * Application-shaped concerns (system-envelope unwrapping, optimiser request
 * defaults, profile-sync helpers) stay here in the facade. SSE stays outside the
 * generated query lane (see ./events).
 *
 * Components never import generated modules directly
 * (tests/test_svelte_generated_client_boundary.py).
 */
import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
} from '@ed-finder/api-client/core';
import { parseLosslessJson } from '@ed-finder/api-client/lossless-json';
import { parseId64, type Id64 } from '@ed-finder/api-client/id64';
import { client } from './generated/client.gen';
import {
  authLogoutApiAuthLogoutPost,
  authSessionApiAuthSessionGet,
  claimOwnerApiAuthOwnerClaimPost,
  getProfileSyncApiProfileSyncSyncKeyGet,
  getSystemApiSystemId64Get,
  healthApiHealthGet,
  postOptimiserCandidatesApiOptimiserCandidatesPost,
  putProfileSyncApiProfileSyncSyncKeyPut,
} from './generated/sdk.gen';
import type { AuthSessionResponse, HealthResponse } from './generated';

export {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
};

function sessionAdminToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}

function requestPathname(url: string): string {
  try {
    return new URL(url, 'https://ed-finder.invalid').pathname;
  } catch {
    return url;
  }
}

// Configure the generated client once with the application transport contract.
// The app is served same-origin (nginx proxies `/api`); we pin an absolute
// same-origin base because the generated client builds `new Request(url)`
// before dispatch, and the platform URL parser rejects a bare relative path
// outside a document base (undici in Node, and any non-browser runtime).
// In the browser this resolves to the current origin — identical to the
// relative path — so cookies stay first-party under `credentials: 'include'`.
client.setConfig({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin,
  credentials: 'include',
});

// Bounded session-only admin token: injected only for require_admin routes,
// and never carried in from a caller (a one-time owner secret must not become
// a reusable header).
client.interceptors.request.use((request) => {
  request.headers.delete('X-Admin-Token');
  if (adminEndpointClass(requestPathname(request.url), request.method)) {
    const token = sessionAdminToken();
    if (token) request.headers.set('X-Admin-Token', token);
  }
  return request;
});

// Lossless Id64 lane: re-serialise the JSON body with identifier fields already
// projected to decimal strings, BEFORE the SDK's `JSON.parse` can round an
// id64 token past Number.MAX_SAFE_INTEGER.
client.interceptors.response.use(async (response) => {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('json')) return response;
  const text = await response.text();
  if (!text) return response;
  let body: string;
  try {
    body = JSON.stringify(parseLosslessJson(text));
  } catch {
    body = text;
  }
  const headers = new Headers(response.headers);
  headers.delete('content-length');
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
});

// Structured, uniform application errors.
client.interceptors.error.use((error, response, request) => {
  if (error instanceof ApiError) return error;
  const status = response?.status ?? 0;
  const path = request ? requestPathname(request.url) : '';
  return new ApiError(status, path, error);
});

export const getHealth = async (
  signal?: AbortSignal,
): Promise<HealthResponse> =>
  (await healthApiHealthGet({ throwOnError: true, signal })).data;

export const getAuthSession = async (
  signal?: AbortSignal,
): Promise<AuthSessionResponse> =>
  (await authSessionApiAuthSessionGet({ throwOnError: true, signal })).data;

export async function getSystem<T extends Record<string, unknown>>(
  id64: Id64,
): Promise<T> {
  const { data } = await getSystemApiSystemId64Get({
    throwOnError: true,
    // The path carries the lossless decimal id64; the generated OpenAPI type is
    // a JS number, so bridge it explicitly rather than coercing through Number().
    path: { id64: parseId64(id64) as unknown as number },
  });
  const envelope = data as unknown as { record?: T; system: T };
  return envelope.record ?? envelope.system;
}

export function optimiserCandidates<
  TResponse,
  TRequest extends Record<string, unknown>,
>(request: TRequest): Promise<TResponse> {
  return postOptimiserCandidatesApiOptimiserCandidatesPost({
    throwOnError: true,
    body: {
      max_candidates: 5,
      allow_estimated_data: true,
      run_preview: true,
      include_ranking: true,
      ...request,
    } as never,
  }).then((result) => result.data as TResponse);
}

export interface ProfileSyncPullResponse<TBlob> {
  blob: TBlob;
  updated_at: string;
  blob_bytes: number;
}

export interface ProfileSyncPushResponse {
  updated_at: string;
  blob_bytes: number;
}

export function pullProfileSync<TBlob>(
  syncKey: string,
  signal?: AbortSignal,
): Promise<ProfileSyncPullResponse<TBlob>> {
  return getProfileSyncApiProfileSyncSyncKeyGet({
    throwOnError: true,
    path: { sync_key: syncKey },
    signal,
  }).then((result) => result.data as unknown as ProfileSyncPullResponse<TBlob>);
}

export function pushProfileSync<TBlob>(
  syncKey: string,
  blob: TBlob,
  signal?: AbortSignal,
): Promise<ProfileSyncPushResponse> {
  return putProfileSyncApiProfileSyncSyncKeyPut({
    throwOnError: true,
    path: { sync_key: syncKey },
    body: { blob } as never,
    signal,
  }).then((result) => result.data as unknown as ProfileSyncPushResponse);
}

export const authLogout = <T = AuthSessionResponse>(): Promise<T> =>
  authLogoutApiAuthLogoutPost({ throwOnError: true }).then(
    (result) => result.data as unknown as T,
  );

export const claimOwner = <T = AuthSessionResponse>(
  adminToken: string,
): Promise<T> =>
  claimOwnerApiAuthOwnerClaimPost({
    throwOnError: true,
    body: { admin_token: adminToken },
  }).then((result) => result.data as unknown as T);

export const frontierLoginUrl = (returnTo: string): string =>
  `/api/auth/frontier/login?return_to=${encodeURIComponent(returnTo)}`;
