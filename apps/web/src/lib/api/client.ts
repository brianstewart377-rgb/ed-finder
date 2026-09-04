/** Stable application API boundary; generated types remain the schema authority. */
import type { AuthSessionResponse } from './generated';
import {
  authSessionApiAuthSessionGet as generatedGetAuthSession,
  healthApiHealthGet as generatedGetHealth,
} from './generated/sdk.gen';
import { apiRequest } from './transport';
export {
  ADMIN_TOKEN_SESSION_KEY,
  ApiError,
  apiRequest,
  parseApiJson,
} from './transport';
const defaults = (signal?: AbortSignal) => ({
  credentials: 'include' as const,
  signal,
  throwOnError: true as const,
});
export const getHealth = async (signal?: AbortSignal) =>
  (await generatedGetHealth(defaults(signal))).data;
export const getAuthSession = async (signal?: AbortSignal) =>
  (await generatedGetAuthSession(defaults(signal))).data;
export const logout = () =>
  apiRequest<AuthSessionResponse>('/api/auth/logout', { method: 'POST' });
export const claimOwner = (admin_token: string) =>
  apiRequest<AuthSessionResponse>('/api/auth/owner/claim', {
    method: 'POST',
    body: JSON.stringify({ admin_token }),
  });
export type Id64 = string;
export type SearchHit = Record<string, unknown> & { id64: Id64; name: string };
export type SearchResponse = {
  count: number;
  total?: number;
  results: SearchHit[];
};
export const autocomplete = (q: string, limit = 8) =>
  apiRequest<{
    results: Array<{
      id64: Id64;
      name: string;
      x: number;
      y: number;
      z: number;
    }>;
  }>(
    `/api/local/autocomplete?${new URLSearchParams({ q, limit: String(limit) })}`,
  );
export const localSearch = (body: unknown) =>
  apiRequest<SearchResponse>('/api/local/search', {
    method: 'POST',
    body: JSON.stringify(body),
  });
export const clusterSearch = (body: unknown) =>
  apiRequest<Record<string, unknown>>('/api/search/cluster', {
    method: 'POST',
    body: JSON.stringify(body),
  });
export const getWatchlist = (syncKey: string) =>
  apiRequest<{
    watchlist: Array<Record<string, unknown> & { system_id64: Id64 }>;
  }>(`/api/v2/watchlist/${encodeURIComponent(syncKey)}`);
export const addWatchlist = (syncKey: string, id64: Id64) =>
  apiRequest(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, {
    method: 'POST',
  });
export const removeWatchlist = (syncKey: string, id64: Id64) =>
  apiRequest(`/api/v2/watchlist/${encodeURIComponent(syncKey)}/${id64}`, {
    method: 'DELETE',
  });
