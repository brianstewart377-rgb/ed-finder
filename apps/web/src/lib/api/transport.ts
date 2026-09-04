export const ADMIN_TOKEN_SESSION_KEY = 'ed_admin_token';
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
function adminToken() {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_SESSION_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}
export function parseApiJson(text: string): unknown {
  return JSON.parse(
    text.replace(/("(?:system_)?id64"\s*:\s*)(-?\d+)/g, '$1"$2"'),
  );
}
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = adminToken();
  const response = await globalThis.fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-Admin-Token': token } : {}),
      ...init.headers,
    },
  });
  const text = await response.text();
  if (!response.ok)
    throw new ApiError(response.status, path, text || response.statusText);
  const parsed = text ? parseApiJson(text) : null;
  if (parsed && typeof parsed === 'object' && 'system' in parsed)
    return (parsed as { system: T }).system;
  return parsed as T;
}
