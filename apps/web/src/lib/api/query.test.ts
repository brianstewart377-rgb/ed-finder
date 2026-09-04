import { describe, expect, it } from 'vitest';
import { queryClient, queryKeys } from './query';
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
});
