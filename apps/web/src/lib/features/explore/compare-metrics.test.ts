import { describe, expect, it } from 'vitest';
import { parseId64 } from '$lib/domain/id64';
import type { CompareEntry } from '$lib/persistence/storage';
import { buildCompareRows, compareCsv, COMPARE_MAX } from './compare-metrics';

const entry = (
  id: string,
  fields: Record<string, unknown> = {},
): CompareEntry => ({
  id64: parseId64(id),
  name: `System ${id}`,
  ...fields,
});

describe('comparison snapshots', () => {
  it('retains the V2 metric set and the six-system limit', () => {
    expect(COMPARE_MAX).toBe(6);
    expect(buildCompareRows([]).map((row) => row.label)).toEqual([
      'Development score',
      'Primary archetype',
      'Secondary archetype',
      'Archetype confidence',
      'Buildability',
      'Purity',
      'Estimated slots',
      'Primary economy',
      'Distance from ref',
      'Population',
      'Status',
      'Main star',
      'Security',
      'Allegiance',
      'ELW',
      'Water worlds',
      'Ammonia',
      'Terraformable',
      'Landable',
      'Bio signals',
      'Geo signals',
    ]);
  });

  it('compares known numbers, marks ties fairly, and prefers shorter distances', () => {
    const rows = buildCompareRows([
      entry('1', { archetype_score: 91, distance: 25, purity_score: 50 }),
      entry('2', {
        overall_development_potential: 91,
        distance: 12,
        purity_score: 50,
      }),
      entry('3', { archetype_score: 70, distance: 0 }),
    ]);
    expect(
      rows
        .find((row) => row.label === 'Development score')
        ?.cells.map((cell) => cell.best),
    ).toEqual([true, true, false]);
    expect(
      rows
        .find((row) => row.label === 'Distance from ref')
        ?.cells.map((cell) => cell.best),
    ).toEqual([false, true, false]);
    expect(
      rows
        .find((row) => row.label === 'Purity')
        ?.cells.every((cell) => !cell.best),
    ).toBe(true);
  });

  it('does not invent unknown data or turn invalid values into winners', () => {
    const rows = buildCompareRows([
      entry('1', {
        population: null,
        distance: 0,
        elw_count: 0,
        purity_score: '90',
        is_colonised: false,
      }),
      entry('2', {
        population: 0,
        distance: NaN,
        purity_score: 80,
        is_colonised: true,
      }),
    ]);
    const cells = (label: string) =>
      rows.find((row) => row.label === label)!.cells;
    expect(cells('Population').map((cell) => cell.display)).toEqual([
      'Unknown',
      'Population unknown',
    ]);
    expect(cells('Distance from ref').map((cell) => cell.display)).toEqual([
      'Unavailable',
      'Unavailable',
    ]);
    expect(cells('ELW').map((cell) => cell.display)).toEqual([
      '0',
      'Unavailable',
    ]);
    expect(cells('Purity').every((cell) => !cell.best)).toBe(true);
    expect(
      buildCompareRows([entry('3')]).find((row) => row.label === 'Status')
        ?.cells[0].display,
    ).toBe('Unknown');
  });

  it('exports the displayed metrics with CSV escaping and safe spreadsheet text', () => {
    const csv = compareCsv([
      entry('18446744073709551615', {
        name: '=HYPERLINK("bad")',
        archetype_score: 91,
        primary_archetype: 'refinery_industrial',
      }),
    ]);
    expect(csv).toContain('"Metric","\'=HYPERLINK(""bad"")"');
    expect(csv).toContain('"Development score","91"');
    expect(csv).toContain(
      '"Primary archetype","Refinery / Industrial Megacomplex"',
    );
    expect(csv).toContain('"Landable","Unavailable"');
  });
});
