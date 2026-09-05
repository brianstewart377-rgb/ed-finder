import { describe, expect, it } from 'vitest';
import {
  optimiserRequestFingerprint,
  queryClient,
  queryKeys,
  type OptimiserQueryRequest,
} from './query';
import { parseId64 } from '$lib/domain/id64';

describe('Svelte Query application contract', () => {
  it('uses the accepted root defaults', () => {
    expect(queryClient.getDefaultOptions()).toMatchObject({
      queries: {
        staleTime: 30_000,
        gcTime: 300_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: 0 },
    });
  });

  it('keeps canonical Id64 in query keys', () => {
    expect(queryKeys.system(parseId64('9007199254740993'))).toEqual([
      'ed-finder',
      'system',
      '9007199254740993',
    ]);
  });

  it('fingerprints every optimiser request input deterministically', () => {
    const base: OptimiserQueryRequest = {
      system_id64: parseId64('9007199254740993'),
      target_archetype: 'agriculture',
      target_archetype_key: 'balanced',
      max_candidates: 5,
      preferred_body_ids: ['body-a', 'body-b'],
      allow_estimated_data: true,
      run_preview: true,
      include_ranking: true,
    };
    const reordered: OptimiserQueryRequest = {
      include_ranking: true,
      preferred_body_ids: ['body-a', 'body-b'],
      max_candidates: 5,
      target_archetype_key: 'balanced',
      run_preview: true,
      target_archetype: 'agriculture',
      system_id64: parseId64('9007199254740993'),
      allow_estimated_data: true,
    };
    expect(optimiserRequestFingerprint(reordered)).toBe(
      optimiserRequestFingerprint(base),
    );

    const variants: OptimiserQueryRequest[] = [
      base,
      { ...base, system_id64: parseId64('9007199254740994') },
      { ...base, target_archetype: 'tourism' },
      { ...base, target_archetype_key: 'fast-start' },
      { ...base, max_candidates: 6 },
      { ...base, preferred_body_ids: ['body-b', 'body-a'] },
      { ...base, allow_estimated_data: false },
      { ...base, run_preview: false },
      { ...base, include_ranking: false },
    ];
    expect(new Set(variants.map(optimiserRequestFingerprint)).size).toBe(
      variants.length,
    );

    expect(queryKeys.optimiser(base)).toEqual([
      'ed-finder',
      'system',
      '9007199254740993',
      'optimiser',
      optimiserRequestFingerprint(base),
    ]);
  });

  it('rejects optimiser fingerprints that cannot be sent as bounded JSON', () => {
    expect(() =>
      optimiserRequestFingerprint({
        system_id64: parseId64('1'),
        max_candidates: Number.NaN,
      }),
    ).toThrow('finite numbers');
  });
});
