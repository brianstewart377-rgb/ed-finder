import { describe, expect, it, vi } from 'vitest';
import { applyLegacyHash, legacyHashDestination } from './legacy-hash';

describe('legacy hash compatibility', () => {
  it.each([
    ['#finder', '/', ''],
    ['#my-work', '/my-work', ''],
    ['#watchlist', '/my-work/watchlist', ''],
    ['#pinned', '/my-work/pinned', ''],
    ['#colony', '/my-work/colony', ''],
    ['#map', '/explore', ''],
    ['#compare', '/compare', ''],
    ['#search-tuning', '/search-tuning', ''],
    ['#fc', '/fc', ''],
    ['#admin', '/admin', ''],
    ['#operator', '/operator', ''],
    ['#system/9007199254740993', '/', '?system=9007199254740993'],
    [
      '#map/system/18446744073709551615',
      '/explore',
      '?system=18446744073709551615',
    ],
  ])('maps %s', (hash, pathname, search) =>
    expect(legacyHashDestination(hash)).toEqual({ pathname, search }),
  );

  it('maps nested planner state and preserves the existing query', () => {
    expect(
      legacyHashDestination(
        '#colony-planner/system/18446744073709551615/project/a%20b/mode/export/detail/9007199254740993',
        '?from=share',
      ),
    ).toEqual({
      pathname:
        '/colony-planner/system/18446744073709551615/project/a%20b/mode/export',
      search: '?from=share&system=9007199254740993',
    });
  });

  it.each([
    '#system/-1',
    '#system/1e3',
    '#system/1.5',
    '#system/%201',
    '#system/18446744073709551616',
  ])('rejects unsafe id64 in %s', (hash) => {
    expect(legacyHashDestination(hash)).toEqual({ pathname: '/', search: '' });
  });

  it('is inactive after the hash has been replaced', () => {
    const replace = vi.fn();
    expect(applyLegacyHash({ hash: '', search: '' } as Location, replace)).toBe(
      false,
    );
    expect(replace).not.toHaveBeenCalled();
  });
});
