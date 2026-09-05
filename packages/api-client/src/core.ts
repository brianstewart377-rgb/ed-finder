/**
 * Tiny fetch wrapper for the ed-finder API.
 *
 * Framework adapters may explicitly configure a base URL at startup. Without
 * that injection, `/api` remains the same-origin fallback for consumers that
 * serve the application and API from one host.
 *
 * The wrapper is intentionally minimal — no axios, no react-query yet. We add
 * those only when we hit a real need (cancellation, retries, dedup, suspense).
 * Premature abstraction has bitten this codebase before; let's not.
 */

export const DEFAULT_API_BASE = '/api';

export let API_BASE = DEFAULT_API_BASE;

/** Configure the shared transport without coupling it to Vite or a UI framework. */
export function configureApiBase(base: string | undefined): string {
  if (base === undefined) {
    API_BASE = DEFAULT_API_BASE;
    return API_BASE;
  }

  // The base is caller-controlled, so scan it once instead of using a regex.
  let end = base.length;
  while (end > 0 && base[end - 1] === '/') {
    end -= 1;
  }

  API_BASE = end === base.length ? base : base.slice(0, end);
  return API_BASE;
}

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
    credentials: 'include',
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
