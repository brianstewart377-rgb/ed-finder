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

  it('isolates watchlists by both account and sync credential', () => {
    expect(queryKeys.watchlist('account-a', 'sync-a')).not.toEqual(
      queryKeys.watchlist('account-b', 'sync-a'),
    );
    expect(queryKeys.watchlist('account-a', 'sync-a')).not.toEqual(
      queryKeys.watchlist('account-a', 'sync-b'),
    );
    expect(queryKeys.watchlist(null, 'sync-a')).not.toEqual(
      queryKeys.watchlist('account-a', 'sync-a'),
    );
  });
});

describe('Finder ranking query keys', () => {
  const request = {
    reference_coords: { x: 1, y: 2, z: 3 },
    filters: { distance: { min: 0, max: 500 }, economy: 'any' as const },
    sort_by: 'distance',
    size: 50,
    from: 0,
  };

  it('partitions Any results by the committed anchor identity, not only its coordinates', () => {
    const first = queryKeys.explore(request, {
      id64: parseId64('158872029'),
      name: 'HD 38179',
    });
    const renamed = queryKeys.explore(request, {
      id64: parseId64('158872029'),
      name: 'HD 38179 (renamed)',
    });
    const twin = queryKeys.explore(request, {
      id64: parseId64('158872030'),
      name: 'HD 38179',
    });
    expect(first).not.toEqual(renamed);
    expect(first).not.toEqual(twin);
    expect(first).toEqual(
      queryKeys.explore(request, {
        id64: parseId64('158872029'),
        name: 'HD 38179',
      }),
    );
    expect(queryKeys.explore(request)).toEqual(
      queryKeys.explore(request, null),
    );
    expect(queryKeys.explore(request)).not.toEqual(first);
  });

  it('keys Any results by page size and offset through the wire request', () => {
    expect(queryKeys.explore({ ...request, size: 1 })).not.toEqual(
      queryKeys.explore(request),
    );
    expect(queryKeys.explore({ ...request, from: 2 })).not.toEqual(
      queryKeys.explore(request),
    );
  });

  it('keys selected rankings by archetype, floor, facade page size and offset', () => {
    const base = {
      archetype: 'flexible' as const,
      min_score: 60 as const,
      page_size: 1,
      offset: 0,
    };
    expect(queryKeys.rankings(base)).toEqual([
      'ed-finder',
      'explore',
      'rankings',
      'flexible',
      60,
      1,
      0,
    ]);
    expect(queryKeys.rankings({ ...base, page_size: 50 })).not.toEqual(
      queryKeys.rankings(base),
    );
    expect(queryKeys.rankings({ ...base, min_score: 88 })).not.toEqual(
      queryKeys.rankings(base),
    );
    expect(queryKeys.rankings({ ...base, offset: 1 })).not.toEqual(
      queryKeys.rankings(base),
    );
    expect(queryKeys.rankings({ ...base, archetype: 'paradise' })).not.toEqual(
      queryKeys.rankings(base),
    );
  });

  it('keys Any results by the facade page size even when the clamped wire request is identical', () => {
    const clamped = {
      galaxy_wide: true,
      sort_by: 'development',
      size: 25,
      from: 9_975,
    };
    expect(queryKeys.explore(clamped, null, 50)).not.toEqual(
      queryKeys.explore(clamped, null, 25),
    );
    expect(queryKeys.explore(clamped, null, 25)).toEqual(
      queryKeys.explore(clamped),
    );
  });
});
