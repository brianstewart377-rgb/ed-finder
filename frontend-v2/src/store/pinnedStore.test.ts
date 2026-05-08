/**
 * Phase 7 — Pinned store (Zustand + persist) tests.
 *
 * Validates:
 *   • Empty initial state when localStorage is empty
 *   • toggle() round-trip add/remove with same id64
 *   • has() returns true after add, false after remove
 *   • Storage adapter reads the BARE legacy array shape (so existing
 *     vanilla-app users keep their pins after the migration)
 *   • clear() empties the store
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { usePinnedStore, exportPinnedJson, type PinnedEntry } from './pinnedStore';

const baseEntry: PinnedEntry = {
  id64:         12345,
  name:         'Test System',
  x: 0, y: 0, z: 0,
  population:   0,
  is_colonised: false,
  rating:       80,
  economy:      'Tourism',
  pinned_at:    '',
};

beforeEach(() => {
  localStorage.clear();
  // Reset the store between tests — Zustand keeps state across `import`s.
  usePinnedStore.setState({ entries: [] });
});

describe('pinnedStore', () => {
  it('starts empty when localStorage is empty', () => {
    expect(usePinnedStore.getState().entries).toEqual([]);
  });

  it('toggle() adds, returns true', () => {
    const added = usePinnedStore.getState().toggle(baseEntry);
    expect(added).toBe(true);
    expect(usePinnedStore.getState().entries.length).toBe(1);
    expect(usePinnedStore.getState().has(baseEntry.id64)).toBe(true);
  });

  it('toggle() on the same id64 removes, returns false', () => {
    usePinnedStore.getState().toggle(baseEntry);
    const removed = usePinnedStore.getState().toggle(baseEntry);
    expect(removed).toBe(false);
    expect(usePinnedStore.getState().entries.length).toBe(0);
    expect(usePinnedStore.getState().has(baseEntry.id64)).toBe(false);
  });

  it('persists to legacy bare-array shape under ed_pinned', () => {
    usePinnedStore.getState().toggle(baseEntry);
    const raw = localStorage.getItem('ed_pinned');
    expect(raw).not.toBeNull();
    // Must be a plain array — NOT Zustand's default {state: ..., version: ...}
    const parsed = JSON.parse(raw as string);
    expect(Array.isArray(parsed)).toBe(true);
    expect(parsed[0].id64).toBe(baseEntry.id64);
  });

  it('honours pinned_at if provided, generates one otherwise', () => {
    usePinnedStore.getState().toggle({ ...baseEntry, pinned_at: '2025-01-01T00:00:00Z' });
    expect(usePinnedStore.getState().entries[0].pinned_at).toBe('2025-01-01T00:00:00Z');

    usePinnedStore.setState({ entries: [] });
    usePinnedStore.getState().toggle(baseEntry);
    expect(usePinnedStore.getState().entries[0].pinned_at).toMatch(/T/);
  });

  it('remove() removes by id64', () => {
    usePinnedStore.getState().toggle(baseEntry);
    usePinnedStore.getState().toggle({ ...baseEntry, id64: 99999 });
    usePinnedStore.getState().remove(baseEntry.id64);
    expect(usePinnedStore.getState().entries.length).toBe(1);
    expect(usePinnedStore.getState().entries[0].id64).toBe(99999);
  });

  it('clear() empties everything', () => {
    usePinnedStore.getState().toggle(baseEntry);
    usePinnedStore.getState().clear();
    expect(usePinnedStore.getState().entries).toEqual([]);
  });

  it('exportPinnedJson runs without throwing', () => {
    // jsdom does not implement URL.createObjectURL — stub it for this test.
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => {},          configurable: true });
    try {
      expect(() => exportPinnedJson([baseEntry])).not.toThrow();
    } finally {
      Object.defineProperty(URL, 'createObjectURL', { value: origCreate, configurable: true });
      Object.defineProperty(URL, 'revokeObjectURL', { value: origRevoke, configurable: true });
    }
  });
});
