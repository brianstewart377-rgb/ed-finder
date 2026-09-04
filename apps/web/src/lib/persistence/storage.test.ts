import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  LOCAL_STORAGE_KEYS,
  SESSION_STORAGE_KEYS,
  collectionCodec,
  compareCodec,
  createPersistedStore,
  fcCodec,
  densityCodec,
  id64StringCodec,
  pinnedCodec,
  rawStringCodec,
  selectedRouteCodec,
  syncKeyCodec,
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

  it('decodes the named legacy React fixtures without data loss', () => {
    const fixtures = legacyPersistenceFixtures;
    const cases = [
      [pinnedCodec, fixtures.pinnedBareArray],
      [compareCodec, fixtures.compareV2],
      [syncKeyCodec, fixtures.syncKey],
      [selectedRouteCodec, fixtures.selectedRoute],
      [collectionCodec(1), fixtures.myWorkV1],
      [collectionCodec(3), fixtures.colonyProjectsV1],
      [collectionCodec(1), fixtures.expansionPlansV1],
      [fcCodec, fixtures.fcRoute],
      [rawStringCodec(), fixtures.profileSyncKey],
      [rawStringCodec(), fixtures.profileSyncLast],
      [id64StringCodec, fixtures.selectedSystemContext],
      [densityCodec, fixtures.density],
      [rawStringCodec(), fixtures.adminToken],
      [rawStringCodec(), fixtures.operatorSelectedSourceRun],
    ] as const;
    for (const [codec, raw] of cases) expect(codec.decode(raw).ok).toBe(true);
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
    expect(result).toMatchObject({ ok: false, problem: 'invalid-shape' });
  });

  it.each([
    ['pinned id', pinnedCodec, '[{"id64":"01","name":"Lave","pinned_at":"x"}]'],
    ['pinned name', pinnedCodec, '[{"id64":"1","name":" ","pinned_at":"x"}]'],
    ['pinned timestamp', pinnedCodec, '[{"id64":"1","name":"Lave"}]'],
    ['compare id', compareCodec, '[{"id64":9007199254740992,"name":"Lave"}]'],
    ['compare name', compareCodec, '[{"id64":"1","name":""}]'],
  ])(
    'diagnoses an invalid %s entry instead of silently dropping it',
    (_name, codec, raw) => {
      expect(codec.decode(raw)).toMatchObject({
        ok: false,
        problem: 'invalid-shape',
      });
    },
  );

  it('validates the current URL-safe sync-key contract', () => {
    expect(
      syncKeyCodec.decode(
        '{"state":{"syncKey":"abcdefghijklmnop"},"version":0}',
      ),
    ).toMatchObject({ ok: true });
    for (const syncKey of [
      'legacy',
      'short',
      'invalid key!',
      'a'.repeat(129),
    ]) {
      expect(
        syncKeyCodec.decode(JSON.stringify({ state: { syncKey }, version: 0 })),
      ).toMatchObject({ ok: false, problem: 'invalid-shape' });
    }
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

  it.each([
    ['unsafe numeric id64', { state: { id64: 9007199254740992 }, version: 1 }],
    ['malformed string id64', { state: { id64: '01' }, version: 1 }],
    [
      'unsafe id64 nested in arrays and records',
      {
        state: { groups: [{ systems: [{ system_id64: 'not-an-id' }] }] },
        version: 1,
      },
    ],
  ])('rejects a collection with %s', (_name, envelope) => {
    expect(collectionCodec(1).decode(JSON.stringify(envelope))).toMatchObject({
      ok: false,
      problem: 'invalid-shape',
    });
  });

  it('normalises valid ids throughout nested arrays and records, including uint64 max', () => {
    const result = collectionCodec(1).decode(
      JSON.stringify({
        state: {
          groups: [
            {
              system_id64: 123,
              systems: [{ id64: '18446744073709551615', future: 'kept' }],
            },
          ],
        },
        version: 1,
        future: { preserved: true },
      }),
    );
    expect(result).toMatchObject({
      ok: true,
      value: {
        state: {
          groups: [
            {
              system_id64: '123',
              systems: [{ id64: '18446744073709551615', future: 'kept' }],
            },
          ],
        },
        version: 1,
        future: { preserved: true },
      },
    });
  });

  it.each([
    ['missing state', { version: 1 }],
    ['array state', { state: [], version: 1 }],
    ['missing version', { state: {} }],
    ['string version', { state: {}, version: '1' }],
    ['fractional version', { state: {}, version: 0.5 }],
    ['negative version', { state: {}, version: -1 }],
  ])('rejects a collection envelope with %s', (_name, envelope) => {
    expect(collectionCodec(1).decode(JSON.stringify(envelope))).toMatchObject({
      ok: false,
      problem: 'invalid-shape',
    });
  });

  it('rejects a non-finite JSON number as an invalid collection version', () => {
    expect(
      collectionCodec(1).decode('{"state":{},"version":1e400}'),
    ).toMatchObject({ ok: false, problem: 'invalid-shape' });
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

  it('reports private-mode reads during set as unavailable without throwing', () => {
    const store = createPersistedStore({
      key: 'ed_profile_sync_last',
      initial: () => '',
      codec: rawStringCodec(),
    });
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementationOnce(() => {
        throw new DOMException('denied', 'SecurityError');
      });
    expect(() => store.set('2026-09-04T00:00:00Z')).not.toThrow();
    expect(get(store)).toMatchObject({
      value: '2026-09-04T00:00:00Z',
      diagnostic: { problem: 'unavailable' },
    });
    getItem.mockRestore();
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
