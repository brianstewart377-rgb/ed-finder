import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  LOCAL_STORAGE_KEYS,
  SESSION_STORAGE_KEYS,
  collectionCodec,
  compareCodec,
  createPersistedStore,
  fcCodec,
  pinnedCodec,
  rawStringCodec,
} from './storage';
import { legacyPersistenceFixtures } from './fixtures';
import { adminToken, selectedSystem } from './stores';

describe('persistence compatibility', () => {
  beforeEach(() => localStorage.clear());

  it('locks the exact local and session key inventory', () => {
    expect(LOCAL_STORAGE_KEYS).toEqual([
      'ed_pinned',
      'ed_compare_v2',
      'ed_sync_key',
      'ed_selected_route',
      'ed_my_work_v1',
      'ed_colony_projects_v1',
      'ed_expansion_plans_v1',
      'ed_fc_v2',
      'ed_profile_sync_key',
      'ed_profile_sync_last',
      'ed-finder:selected-system-context',
      'ed_density_v1',
    ]);
    expect(SESSION_STORAGE_KEYS).toEqual([
      'ed_admin_token',
      'ed_operator_selected_source_run',
    ]);
  });

  it('hydrates and round-trips the exact bare-array pin shape with canonical id64', () => {
    localStorage.setItem(
      'ed_pinned',
      legacyPersistenceFixtures.pinnedBareArray,
    );
    const store = createPersistedStore({
      key: 'ed_pinned',
      initial: () => [],
      codec: pinnedCodec,
    });
    store.hydrate();
    expect(get(store).value).toEqual([
      {
        id64: '12345',
        name: 'Test System',
        x: 0,
        y: 0,
        z: 0,
        population: 0,
        is_colonised: false,
        economy: 'Tourism',
        pinned_at: '2026-07-07T00:00:00Z',
      },
    ]);
    expect(store.set(get(store).value)).toBe(true);
    expect(JSON.parse(localStorage.getItem('ed_pinned')!)).toEqual(
      get(store).value,
    );
  });

  it('preserves oversized decimal identifiers and uint64 max exactly', () => {
    const result = compareCodec.decode(
      JSON.stringify([
        { id64: '9007199254740993', name: 'Above safe integer' },
        { id64: '18446744073709551615', name: 'Uint64 max' },
      ]),
    );
    expect(result.ok && result.value.map((entry) => entry.id64)).toEqual([
      '9007199254740993',
      '18446744073709551615',
    ]);
  });

  it('hydrates selected-system zero and uint64 max as canonical strings', () => {
    localStorage.setItem('ed-finder:selected-system-context', '0');
    selectedSystem.hydrate();
    expect(get(selectedSystem).value).toBe('0');
    localStorage.setItem(
      'ed-finder:selected-system-context',
      '18446744073709551615',
    );
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'ed-finder:selected-system-context',
      }),
    );
    expect(get(selectedSystem).value).toBe('18446744073709551615');
  });

  it('keeps the admin token session-only', () => {
    sessionStorage.clear();
    expect(adminToken.set('temporary-admin-token')).toBe(true);
    expect(sessionStorage.getItem('ed_admin_token')).toBe(
      'temporary-admin-token',
    );
    expect(localStorage.getItem('ed_admin_token')).toBeNull();
    adminToken.clear();
  });

  it('drops an unsafe legacy numeric id instead of preserving a rounded value', () => {
    const result = pinnedCodec.decode(
      '[{"id64":9007199254740992,"name":"lossy","pinned_at":"x"}]',
    );
    expect(result).toEqual({ ok: true, value: [] });
  });

  it('migrates FC waypoint ids and merges legacy config without losing unknown fields', () => {
    const result = fcCodec.decode(
      JSON.stringify({
        waypoints: [
          { id: 'wp-sync', name: 'Achenar', id64: 123, x: 67, future: 'kept' },
        ],
        config: { jump_range_ly: 420, future_config: true },
        future_root: 1,
      }),
    );
    expect(result.ok && result.value).toMatchObject({
      waypoints: [{ id64: '123', future: 'kept' }],
      config: { jump_range_ly: 420, future_config: true },
      future_root: 1,
    });
  });

  it('normalises collection envelopes and preserves unknown fields', () => {
    const result = collectionCodec(3).decode(
      JSON.stringify({
        state: {
          projects: [{ id: 'p', system_id64: 123, unknown: 'kept' }],
          extra: 1,
        },
        version: 1,
        future: true,
      }),
    );
    expect(result.ok && result.value).toMatchObject({
      state: { projects: [{ system_id64: '123', unknown: 'kept' }], extra: 1 },
      version: 1,
      future: true,
    });
  });

  it('reports corrupt JSON and wrong types without crashing or erasing the entry', () => {
    localStorage.setItem('ed_compare_v2', '{broken');
    const store = createPersistedStore({
      key: 'ed_compare_v2',
      initial: () => [],
      codec: compareCodec,
    });
    expect(() => store.hydrate()).not.toThrow();
    expect(get(store).diagnostic?.problem).toBe('corrupt-json');
    expect(localStorage.getItem('ed_compare_v2')).toBe('{broken');

    localStorage.setItem('ed_compare_v2', '{}');
    store.hydrate();
    expect(get(store).diagnostic?.problem).toBe('invalid-shape');
  });

  it('refuses to overwrite a newer unknown envelope', () => {
    const raw = JSON.stringify({
      state: { systems: {} },
      version: 99,
      future: 'data',
    });
    localStorage.setItem('ed_my_work_v1', raw);
    const store = createPersistedStore({
      key: 'ed_my_work_v1',
      initial: () => ({ state: {}, version: 0 }),
      codec: collectionCodec(1),
    });
    store.hydrate();
    expect(get(store).diagnostic?.problem).toBe('unsupported-version');
    expect(store.set({ state: {}, version: 1 })).toBe(false);
    expect(localStorage.getItem('ed_my_work_v1')).toBe(raw);
  });

  it('reacts to cross-tab storage events', () => {
    const store = createPersistedStore({
      key: 'ed_profile_sync_key',
      initial: () => '',
      codec: rawStringCodec(),
      crossTab: true,
    });
    store.hydrate();
    localStorage.setItem('ed_profile_sync_key', 'new-device-key');
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'ed_profile_sync_key',
        storageArea: localStorage,
      }),
    );
    expect(get(store).value).toBe('new-device-key');
  });

  it('is SSR safe when window is absent', () => {
    vi.stubGlobal('window', undefined);
    const store = createPersistedStore({
      key: 'ed_profile_sync_last',
      initial: () => '',
      codec: rawStringCodec(),
    });
    expect(() => store.hydrate()).not.toThrow();
    expect(get(store)).toEqual({ value: '', hydrated: true, diagnostic: null });
    vi.unstubAllGlobals();
  });
});
