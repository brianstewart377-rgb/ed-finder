import { jsonFetch, resolveApiUrl } from './core';
import type { components } from '@/types/api.gen';

export type AuthUser = components['schemas']['AuthUserResponse'];
export type AuthSession = components['schemas']['AuthSessionResponse'];

export function frontierLoginUrl(returnTo: string): string {
  return resolveApiUrl(`/v1/auth/frontier/login?return_to=${encodeURIComponent(returnTo)}`);
}

export function authSession(): Promise<AuthSession> {
  return jsonFetch('/v1/auth/session');
}

export function authLogout(): Promise<AuthSession> {
  return jsonFetch('/v1/auth/logout', { method: 'POST' });
}

export function claimOwner(adminToken: string): Promise<AuthSession> {
  const payload: components['schemas']['OwnerClaimRequest'] = {
    admin_token: adminToken,
  };
  return jsonFetch('/v1/auth/owner/claim', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
