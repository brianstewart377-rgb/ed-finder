import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { parseId64 } from '$lib/domain/id64';
import { compare, pins } from '$lib/persistence/stores';
import { PERSISTENCE_KEYS } from '$lib/persistence/storage';
import {
  snapshotFromExplore,
  snapshotFromPin,
  snapshotFromWatchlist,
  toggleComparison,
  togglePin,
} from './shortlist';

const system = {
  id64: parseId64('9007199254740993'),
  name: 'Test system',
  coords: { x: 1, y: 2, z: 3 },
  distance: 12,
  primaryEconomy: 'Industrial',
  overall_development_potential: 81,
  elw_count: 2,
};

describe('Finder shortlist actions', () => {
  beforeEach(() => {
    localStorage.clear();
    pins.set([]);
    compare.set([]);
  });

  it('pins full snapshots newest first and removes by exact Id64', () => {
    const first = snapshotFromExplore(system);
    expect(togglePin(pins, first)).toEqual({ selected: true, error: null });
    togglePin(pins, {
      ...first,
      id64: parseId64('9007199254740992'),
      name: 'Second',
    });
    const saved = get(pins).value;
    expect(saved.map((entry) => entry.name)).toEqual(['Second', 'Test system']);
    expect(saved[1]).toMatchObject({
      x: 1,
      y: 2,
      z: 3,
      economy: 'Industrial',
      archetype_score: 81,
    });
    expect(snapshotFromPin(saved[1])).toMatchObject({ ...first, elw_count: 2 });
    expect(togglePin(pins, first).selected).toBe(false);
    expect(get(pins).value.map((entry) => entry.id64)).toEqual([
      '9007199254740992',
    ]);
  });

  it('persists six comparison snapshots, rejects a seventh, and still removes at capacity', () => {
    for (let index = 1; index <= 6; index++) {
      expect(
        toggleComparison(compare, { ...system, id64: parseId64(String(index)) })
          .selected,
      ).toBe(true);
    }
    const before = localStorage.getItem(PERSISTENCE_KEYS.compare);
    expect(
      toggleComparison(compare, snapshotFromExplore(system)).error,
    ).toMatch(/6/);
    expect(localStorage.getItem(PERSISTENCE_KEYS.compare)).toBe(before);
    expect(
      toggleComparison(compare, { ...system, id64: parseId64('3') }).selected,
    ).toBe(false);
    expect(get(compare).value).toHaveLength(5);
    expect(get(compare).value[0]).toMatchObject({ elw_count: 2, distance: 12 });
  });

  it('adapts legacy pins and backend watchlist rows without inventing missing facts', () => {
    expect(
      snapshotFromPin({
        id64: system.id64,
        name: 'Legacy',
        pinned_at: '',
        x: 1,
        economy: 'Extraction',
      }),
    ).toMatchObject({
      id64: system.id64,
      name: 'Legacy',
      primaryEconomy: null,
      coords: { x: 1, y: null, z: null },
    });
    const snapshot = snapshotFromWatchlist({
      system_id64: system.id64,
      name: system.name,
      added_at: '2026-09-21T00:00:00Z',
      score: 30,
      archetype_score: 70,
      economy_suggestion: 'Agriculture',
    });
    expect(snapshot).toMatchObject({ id64: system.id64, archetype_score: 70 });
    expect(snapshot.primaryEconomy).toBeUndefined();
    expect(snapshot.elw_count).toBeUndefined();
  });

  it('reports storage failures instead of claiming durable success', () => {
    const spy = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('quota');
      });
    expect(
      toggleComparison(compare, snapshotFromExplore(system)).error,
    ).toMatch(/saved/);
    spy.mockRestore();
  });
});
