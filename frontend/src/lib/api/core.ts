/**
 * Tiny fetch wrapper for the ed-finder API.
 *
 * Resolves the base URL in this order:
 *   1. import.meta.env.VITE_API_BASE  (set per environment in .env / .env.production)
 *   2. /api  — same-origin fallback when the bundle is served from the same
 *      host as the API (the production deploy via nginx).
 *
 * The wrapper is intentionally minimal — no axios, no react-query yet. We add
 * those only when we hit a real need (cancellation, retries, dedup, suspense).
 * Premature abstraction has bitten this codebase before; let's not.
 */

export const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, '') ??
  '/api'
);

export const ADMIN_TOKEN_SESSION_KEY = 'ed_admin_token';

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  // Allow callers to force an /api-prefixed endpoint without doubling when
  // API_BASE already ends with /api.
  if (path.startsWith('/api/') && /\/api$/i.test(API_BASE)) {
    return `${API_BASE}${path.slice(4)}`;
  }
  return `${API_BASE}${path}`;
}

export function readSessionAdminToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY) ?? '';
  } catch {
    return '';
  }
}

export function operatorMutationHeaders(): HeadersInit | undefined {
  const token = readSessionAdminToken().trim();
  if (!token) return undefined;
  return { 'X-Admin-Token': token };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    public readonly body: string,
  ) {
    super(`API ${status} on ${path}: ${body}`);
    this.name = 'ApiError';
  }
}

export async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept:         'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    // Surface the FastAPI Problem-Details body so the caller can show a
    // useful error. The vanilla app drops the body here, which makes
    // debugging deploys painful.
    let body = '';
    try {
      body = await res.text();
    } catch { /* ignore */ }
    throw new ApiError(res.status, path, body || res.statusText);
  }
  return res.json() as Promise<T>;
}
