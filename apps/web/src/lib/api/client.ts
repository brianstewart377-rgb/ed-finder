/** Typed application facade over the canonical shared browser transport. */
import {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
} from '@ed-finder/api-client/core';
import { parseId64, type Id64 } from '@ed-finder/api-client/id64';
import type { AuthSessionResponse, HealthResponse } from './generated';

export {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  LEGACY_ADMIN_ENDPOINTS,
  adminEndpointClass,
  apiRequest,
  canonicalApiPath,
};

export const getHealth = (signal?: AbortSignal): Promise<HealthResponse> =>
  apiRequest('/health', { signal });

export const getAuthSession = (
  signal?: AbortSignal,
): Promise<AuthSessionResponse> => apiRequest('/auth/session', { signal });

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
  return apiRequest(`/profile/sync/${encodeURIComponent(syncKey)}`, { signal });
}

export function pushProfileSync<TBlob>(
  syncKey: string,
  blob: TBlob,
  signal?: AbortSignal,
): Promise<ProfileSyncPushResponse> {
  return apiRequest(`/profile/sync/${encodeURIComponent(syncKey)}`, {
    method: 'PUT',
    body: JSON.stringify({ blob }),
    signal,
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
