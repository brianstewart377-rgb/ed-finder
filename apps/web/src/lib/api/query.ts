import { QueryClient } from '@tanstack/svelte-query';
import type { Id64 } from '$lib/domain/id64';

export interface OptimiserQueryRequest {
  readonly system_id64: Id64;
  readonly target_archetype?: string | null;
  readonly target_archetype_key?: string | null;
  readonly max_candidates?: number;
  readonly preferred_body_ids?: readonly string[];
  readonly allow_estimated_data?: boolean;
  readonly run_preview?: boolean;
  readonly include_ranking?: boolean;
}

function normalizedFingerprintValue(
  value: unknown,
  ancestors: Set<object>,
): unknown {
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value))
      throw new TypeError('Query fingerprints require finite numbers');
    return value;
  }
  if (typeof value === 'undefined') return undefined;
  if (typeof value !== 'object')
    throw new TypeError('Query fingerprints require JSON-compatible values');
  if (ancestors.has(value))
    throw new TypeError('Query fingerprints cannot contain cycles');

  ancestors.add(value);
  try {
    if (Array.isArray(value))
      return value.map(
        (item) => normalizedFingerprintValue(item, ancestors) ?? null,
      );
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null)
      throw new TypeError('Query fingerprints require plain objects');
    const normalized: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      const item = normalizedFingerprintValue(
        (value as Record<string, unknown>)[key],
        ancestors,
      );
      if (item !== undefined) normalized[key] = item;
    }
    return normalized;
  } finally {
    ancestors.delete(value);
  }
}

/** Stable wire-equivalent identity for every optimiser request input. */
export function optimiserRequestFingerprint(
  request: OptimiserQueryRequest,
): string {
  const fingerprint = JSON.stringify(
    normalizedFingerprintValue(request, new Set()),
  );
  if (fingerprint === undefined)
    throw new TypeError('Optimiser request cannot be fingerprinted');
  return fingerprint;
}

export const queryKeys = {
  all: ['ed-finder'] as const,
  auth: () => [...queryKeys.all, 'auth'] as const,
  health: () => [...queryKeys.all, 'health'] as const,
  system: (id64: Id64) => [...queryKeys.all, 'system', id64] as const,
  compare: (id64s: readonly Id64[]) =>
    [...queryKeys.all, 'compare', ...id64s] as const,
  optimiser: (request: OptimiserQueryRequest) =>
    [
      ...queryKeys.system(request.system_id64),
      'optimiser',
      optimiserRequestFingerprint(request),
    ] as const,
  operator: (resource: string) =>
    [...queryKeys.all, 'operator', resource] as const,
};

/** The one application query client; feature providers should reuse this root. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 300_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
});
