import { describe, expect, it } from 'vitest';
import { legacyHashPath, routeFromPath } from './routing';
describe('route compatibility', () => {
  it.each([
    ['#system/9223372036854775807', '/finder/system/9223372036854775807'],
    ['#watchlist/system/42', '/my-work/system/42'],
    ['#pinned', '/my-work'],
    ['#colony', '/my-work'],
    ['#map', '/map'],
    ['#compare', '/compare'],
    ['#search-tuning', '/search-tuning'],
    ['#fc', '/fc'],
    ['#admin', '/admin'],
    ['#operator', '/operator'],
    [
      '#colony-planner/system/42/project/a/mode/map/detail/9',
      '/colony-planner/system/42/project/a/mode/map/detail/9',
    ],
  ])('maps %s', (hash, path) => expect(legacyHashPath(hash)).toBe(path));
  it('keeps aliases visible to My Work', () =>
    expect(routeFromPath('/watchlist')).toMatchObject({
      route: 'my-work',
      alias: 'watchlist',
    }));
});
