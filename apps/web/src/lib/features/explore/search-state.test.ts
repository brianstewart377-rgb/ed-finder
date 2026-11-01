import { describe, expect, it } from 'vitest';
import { parseId64 } from '$lib/domain/id64';
import { BODY_FILTER_OPTIONS, type BodyFilterValues } from './body-filters';
import {
  MAX_BODIES_PARAMETER_LENGTH,
  parseExploreSearchParams,
  serializeExploreSearchParams,
} from './search-state';

const parse = (query: string) =>
  parseExploreSearchParams(new URLSearchParams(query));

describe('Explore search URL', () => {
  it('leaves plain Explore empty', () => {
    const result = parse('');
    expect(result.near).toBeNull();
    expect(result.bodyFilters).toEqual({});
    expect(result.issues).toEqual([]);
    expect(result.canonical.toString()).toBe('');
  });

  it.each(['0', '9007199254740993', '18446744073709551615'])(
    'restores a lossless id64 %s',
    (near) => {
      const result = parse(`near=${near}`);
      expect(result.near).toBe(near);
      expect(result.canonical.get('near')).toBe(near);
      expect(result.issues).toEqual([]);
    },
  );

  it.each([
    '',
    '01',
    '-1',
    '1.5',
    '1e3',
    'NaN',
    'undefined',
    ' 1',
    '18446744073709551616',
  ])('canonicalizes an invalid near parameter away: %s', (near) => {
    const result = parse(`near=${encodeURIComponent(near)}&selected=42`);
    expect(result.near).toBeNull();
    expect(result.issues).toHaveLength(1);
    expect(result.canonical.toString()).toBe('selected=42');
  });

  it('rejects an overlong near parameter before parsing its integer', () => {
    const result = parse(`near=${'1'.repeat(100_000)}`);
    expect(result.near).toBeNull();
    expect(result.canonical.has('near')).toBe(false);
    expect(result.issues).toHaveLength(1);
  });

  it('rejects repeated near and bodies parameters entirely', () => {
    const result = parse(
      'near=1&near=2&bodies=elw_count:1-&bodies=ring_count:-3',
    );
    expect(result.near).toBeNull();
    expect(result.bodyFilters).toEqual({});
    expect(result.issues).toHaveLength(2);
    expect(result.canonical.toString()).toBe('');
  });

  it('round-trips open and closed ranges with the anchor and unrelated state', () => {
    const result = parse(
      'archetype=flexible&selected=42&near=9007199254740993&bodies=ring_count:-3,landable_count:2-5,elw_count:1-&extra=a&extra=b',
    );
    expect(result.bodyFilters).toEqual({
      elw_count: { min: 1 },
      landable_count: { min: 2, max: 5 },
      ring_count: { max: 3 },
    });
    expect(result.issues).toEqual([]);
    expect(result.canonical.get('bodies')).toBe(
      'elw_count:1-,landable_count:2-5,ring_count:-3',
    );
    expect(result.canonical.getAll('extra')).toEqual(['a', 'b']);
    expect(result.canonical.get('archetype')).toBe('flexible');
    expect(result.canonical.get('selected')).toBe('42');
    expect(parse(result.canonical.toString()).canonical.toString()).toBe(
      result.canonical.toString(),
    );
  });

  it.each([
    '',
    'unknown:1-',
    'elw_count:-',
    'elw_count:-1-',
    'elw_count:1--2',
    'elw_count:1.5-',
    'elw_count:1e2-',
    'elw_count:01-',
    'elw_count:1-01',
    'elw_count:2-1',
    'elw_count:1000-',
    'elw_count:-1000',
    'elw_count:1-2:3',
    'elw_count: 1-',
    'elw_count:NaN-',
    '__proto__:1-',
    'constructor:1-',
  ])(
    'drops malformed body entries without dropping valid ones: %s',
    (entry) => {
      const result = parse(
        `bodies=${encodeURIComponent(`${entry},ring_count:-3`)}`,
      );
      expect(result.bodyFilters).toEqual({ ring_count: { max: 3 } });
      expect(result.canonical.get('bodies')).toBe('ring_count:-3');
      expect(result.issues).toHaveLength(1);
    },
  );

  it.each([
    'elw_count:1-,elw_count:2-',
    'elw_count:broken,elw_count:2-',
    'elw_count:1-,elw_count:broken',
    'elw_count:1-,elw_count:2-,elw_count:3-',
  ])('drops duplicate body keys entirely: %s', (entries) => {
    const result = parse(`bodies=${entries},ring_count:-3`);
    expect(result.bodyFilters).toEqual({ ring_count: { max: 3 } });
    expect(result.issues).toHaveLength(1);
  });

  it('accepts every supported body key at the hard bound within the URL size limit', () => {
    const bodyFilters: BodyFilterValues = {};
    for (const { key } of BODY_FILTER_OPTIONS)
      bodyFilters[key] = { min: 999, max: 999 };
    const encoded = serializeExploreSearchParams({ bodyFilters });
    expect(encoded.get('bodies')!.length).toBeLessThanOrEqual(
      MAX_BODIES_PARAMETER_LENGTH,
    );
    expect(parse(encoded.toString()).bodyFilters).toEqual(bodyFilters);
    expect(parse(encoded.toString()).issues).toEqual([]);
  });

  it('drops the whole bodies parameter if its encoded content exceeds the bound', () => {
    const result = parse(
      `near=42&bodies=elw_count:1-,${'x'.repeat(MAX_BODIES_PARAMETER_LENGTH)}`,
    );
    expect(result.bodyFilters).toEqual({});
    expect(result.canonical.toString()).toBe('near=42');
    expect(result.issues).toHaveLength(1);
  });

  it('removes cleared inputs without disturbing ranking or passive URL state', () => {
    const base = new URLSearchParams(
      'archetype=flexible&near=42&bodies=elw_count:1-&selected=42&system=99',
    );
    expect(
      serializeExploreSearchParams(
        { near: null, bodyFilters: {} },
        base,
      ).toString(),
    ).toBe('archetype=flexible&selected=42&system=99');
    expect(base.get('near')).toBe('42');
    expect(
      serializeExploreSearchParams({
        near: parseId64('42'),
        bodyFilters: { elw_count: { min: 2, max: 1 } },
      }).toString(),
    ).toBe('near=42');
  });
});
