import { jsonFetch } from './core';

export interface AuthUser {
  commander_name: string | null;
  is_owner: boolean;
}
export interface AuthSession {
  authenticated: boolean;
  user: AuthUser | null;
  owner_claim_available: boolean;
}

export function authSession(): Promise<AuthSession> {
  return jsonFetch('/auth/session');
}

export function authLogout(): Promise<AuthSession> {
  return jsonFetch('/auth/logout', { method: 'POST' });
}

export function claimOwner(adminToken: string): Promise<AuthSession> {
  return jsonFetch('/auth/owner/claim', {
    method: 'POST',
    body: JSON.stringify({ admin_token: adminToken }),
  });
}
