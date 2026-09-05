import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseId64 } from '$lib/domain/id64';

import {
  DEFAULT_FC_CONFIG,
  LOCAL_STORAGE_KEYS,
  PERSISTENCE_KEYS,
  SESSION_STORAGE_KEYS,
  colonyProjectsCodec,
  collectionCodec,
  compareCodec,
  createPersistedStore,
  densityCodec,
  expansionPlansCodec,
  fcCodec,
  id64StringCodec,
  myWorkCodec,
  normalisePlanRecord,
  opaqueJsonCodec,
  pinnedCodec,
  profileSyncKeyCodec,
  rawStringCodec,
  replaceExpansionPlanSlotSystem,
  selectedRouteCodec,
  syncKeyCodec,
  type ExpansionPlanRecord,
} from './storage';
import { legacyPersistenceFixtures } from './fixtures';
import {
  adminToken,
  colonyProjects,
  compare,
  density,
  expansionPlans,
  fcRoute,
  myWork,
  operatorHandoff,
  profileSyncKey,
  profileSyncLast,
  selectedSystem,
} from './stores';

describe('persistence compatibility', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('locks the exact local and session key inventory', () => {
    expect(LOCAL_STORAGE_KEYS).toEqual([
      'ed_pinned',
      'ed_compare_v2',
      'ed_colony_v2',
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

  it('uses the exact current collection envelopes for empty state', () => {
    myWork.hydrate();
    colonyProjects.hydrate();
    expansionPlans.hydrate();
    expect(get(myWork).value).toEqual({ state: { systems: {} }, version: 1 });
    expect(get(colonyProjects).value).toEqual({
      state: { projects: {} },
      version: 3,
    });
    expect(get(expansionPlans).value).toEqual({
      state: { plans: {} },
      version: 1,
    });
  });

  it('decodes the named legacy React fixtures without data loss', () => {
    const fixtures = legacyPersistenceFixtures;
    const cases = [
      [pinnedCodec, fixtures.pinnedBareArray],
      [compareCodec, fixtures.compareV2],
      [opaqueJsonCodec, fixtures.legacyColonyV2],
      [syncKeyCodec, fixtures.syncKey],
      [selectedRouteCodec, fixtures.selectedRoute],
      [myWorkCodec, fixtures.myWorkV1],
      [colonyProjectsCodec, fixtures.colonyProjectsV1],
      [expansionPlansCodec, fixtures.expansionPlansV1],
      [fcCodec, fixtures.fcRoute],
      [profileSyncKeyCodec, fixtures.profileSyncKey],
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

  it('hydrates and round-trips Compare as a bare array, never an envelope', () => {
    localStorage.setItem('ed_compare_v2', legacyPersistenceFixtures.compareV2);
    const store = createPersistedStore({
      key: PERSISTENCE_KEYS.compare,
      initial: () => [],
      codec: compareCodec,
    });
    store.hydrate();
    expect(get(store).value).toEqual([
      {
        id64: '42',
        name: 'Persisted',
        population: 0,
        coords: { x: 0, y: 0, z: 0 },
      },
    ]);
    expect(store.set(get(store).value)).toBe(true);
    const persisted = JSON.parse(localStorage.getItem('ed_compare_v2')!);
    expect(Array.isArray(persisted)).toBe(true);
    expect(persisted).toEqual(get(store).value);
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

  it('keeps the operator handoff session-only', () => {
    sessionStorage.clear();
    expect(operatorHandoff.set('run-001')).toBe(true);
    expect(sessionStorage.getItem(PERSISTENCE_KEYS.operatorHandoff)).toBe(
      'run-001',
    );
    expect(localStorage.getItem(PERSISTENCE_KEYS.operatorHandoff)).toBeNull();
    operatorHandoff.clear();
  });

  it('stores the profile key and last-push receipt as raw strings', () => {
    expect(profileSyncKey.set('profile-sync-key-1234567890')).toBe(true);
    expect(profileSyncLast.set('2026-09-05T12:00:00+00:00')).toBe(true);
    expect(localStorage.getItem(PERSISTENCE_KEYS.profileSyncKey)).toBe(
      'profile-sync-key-1234567890',
    );
    expect(localStorage.getItem(PERSISTENCE_KEYS.profileSyncLast)).toBe(
      '2026-09-05T12:00:00+00:00',
    );
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
      config: {
        ...DEFAULT_FC_CONFIG,
        jump_range_ly: 420,
        future_config: true,
      },
      future_root: 1,
    });
  });

  it('backfills the complete FC config when a legacy snapshot omits it', () => {
    expect(fcCodec.decode('{"waypoints":[]}')).toEqual({
      ok: true,
      value: { waypoints: [], config: DEFAULT_FC_CONFIG },
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
    [
      'unsafe numeric id64 list',
      { state: { related_id64s: [9007199254740992] }, version: 1 },
    ],
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
          related_id64s: [0, '18446744073709551615'],
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
          related_id64s: ['0', '18446744073709551615'],
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

  it('normalises My Work records and drops corrupt or unsafe legacy entries', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-05T12:00:00.000Z'));
    const result = myWorkCodec.decode(
      JSON.stringify({
        state: {
          systems: {
            wrongKey: {
              id64: 42,
              name: '  Normalised  ',
              labels: ['favourite', 'invalid', 'favourite', 'ready_to_plan'],
              is_colonised: 1,
            },
            max: {
              id64: '18446744073709551615',
              name: '',
              labels: null,
              updated_at: '2026-09-04T00:00:00Z',
            },
            lossy: { id64: 9007199254740992, name: 'drop me' },
            corrupt: 'drop me too',
          },
        },
        version: 1,
      }),
    );
    vi.useRealTimers();

    expect(result.ok && result.value).toEqual({
      state: {
        systems: {
          '42': {
            id64: '42',
            name: 'Normalised',
            labels: ['favourite', 'ready_to_plan'],
            is_colonised: true,
            x: null,
            y: null,
            z: null,
            population: null,
            explicit_colonised_at: null,
            updated_at: '2026-09-05T12:00:00.000Z',
          },
          '18446744073709551615': {
            id64: '18446744073709551615',
            name: 'System 18446744073709551615',
            labels: [],
            updated_at: '2026-09-04T00:00:00Z',
            x: null,
            y: null,
            z: null,
            population: null,
            is_colonised: false,
            explicit_colonised_at: null,
          },
        },
      },
      version: 1,
    });
  });

  it('migrates legacy colony arrays to the current collection version', () => {
    const result = colonyProjectsCodec.decode(
      legacyPersistenceFixtures.colonyProjectsV1,
    );
    expect(result.ok && result.value).toMatchObject({
      version: 3,
      state: {
        projects: {
          'legacy-project': {
            system_id64: '123',
            status: 'draft',
            declared_roles: [],
            objective: null,
            start_approach: null,
            created_from: null,
          },
        },
      },
    });
  });

  it('recovers corrupt expansion collections and records without unsafe selectors', () => {
    expect(expansionPlansCodec.decode('{broken')).toMatchObject({
      ok: false,
      problem: 'corrupt-json',
    });
    expect(
      expansionPlansCodec.decode(
        JSON.stringify({ state: { plans: 'not-an-object' }, version: 1 }),
      ),
    ).toEqual({
      ok: true,
      value: { state: { plans: {} }, version: 1 },
    });

    const result = expansionPlansCodec.decode(
      JSON.stringify({
        state: {
          plans: {
            nullRecord: null,
            textRecord: 'bad',
            unsafe: {
              id: 'unsafe',
              anchor_system_id64: 9007199254740992,
              slots: [],
            },
            valid: {
              id: 'plan-max',
              anchor_system_id64: '18446744073709551615',
              archived_at: null,
              future: 'kept',
              slots: [
                null,
                {
                  slot_index: 0,
                  system_id64: 84,
                  system_name: 'First Target',
                  economies: ['Refinery'],
                  scores: { refinery: 80 },
                  distance_from_anchor_ly: 12,
                  colony_project_id: 'project-1',
                  future_slot: true,
                },
                { slot_index: 1, system_id64: 'bad-id' },
              ],
            },
          },
        },
        version: 1,
      }),
    );

    expect(result.ok && result.value).toMatchObject({
      state: {
        plans: {
          'plan-max': {
            anchor_system_id64: '18446744073709551615',
            future: 'kept',
            slots: [
              {
                slot_index: 0,
                system_id64: '84',
                colony_project_id: 'project-1',
                future_slot: true,
              },
            ],
          },
        },
      },
      version: 1,
    });
    const plans = result.ok ? Object.values(result.value.state.plans) : [];
    expect(() =>
      plans.filter((plan) =>
        plan.slots.some((slot) => slot.system_id64 === '84'),
      ),
    ).not.toThrow();
    expect(normalisePlanRecord([null, 'bad'])).toEqual({});
  });

  it('preserves slot data and clears only the replaced system project link', () => {
    const plan: ExpansionPlanRecord = {
      id: 'plan-1',
      anchor_system_id64: parseId64('42'),
      archived_at: null,
      plan_name: 'Refinery loop',
      slots: [
        {
          slot_index: 0,
          system_id64: parseId64('84'),
          system_name: 'First Target',
          economies: ['Refinery'],
          scores: { refinery: 80 },
          distance_from_anchor_ly: 12,
          colony_project_id: 'project-1',
          future_slot: 'kept',
        },
        {
          slot_index: 1,
          system_id64: parseId64('85'),
          colony_project_id: 'project-2',
        },
      ],
    };
    const updated = replaceExpansionPlanSlotSystem(
      plan,
      0,
      {
        system_id64: parseId64('126'),
        system_name: 'Replacement Target',
        scores: { refinery: 92 },
        distance_from_anchor_ly: 18,
      },
      '2026-09-05T12:00:00Z',
    );

    expect(updated.slots[0]).toMatchObject({
      system_id64: '126',
      system_name: 'Replacement Target',
      colony_project_id: null,
      economies: ['Refinery'],
      future_slot: 'kept',
    });
    expect(updated.slots[1]).toBe(plan.slots[1]);
    expect(updated.slots[1].colony_project_id).toBe('project-2');
    expect(updated.updated_at).toBe('2026-09-05T12:00:00Z');
  });

  it('rewrites a valid expansion legacy snapshot through its one-time migration path', () => {
    localStorage.setItem(
      PERSISTENCE_KEYS.expansionPlans,
      JSON.stringify({
        state: {
          plans: [
            {
              id: 'legacy-plan',
              anchor_system_id64: 42,
              slots: [{ slot_index: 0, system_id64: 84 }],
            },
          ],
        },
        version: 0,
      }),
    );

    expansionPlans.hydrate();

    expect(
      JSON.parse(localStorage.getItem(PERSISTENCE_KEYS.expansionPlans)!),
    ).toMatchObject({
      state: {
        plans: {
          'legacy-plan': {
            anchor_system_id64: '42',
            slots: [{ system_id64: '84', colony_project_id: null }],
          },
        },
      },
      version: 1,
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

  it('installs one guarded listener and never writes in response to an event', () => {
    const addEventListener = vi.spyOn(window, 'addEventListener');
    const store = createPersistedStore({
      key: PERSISTENCE_KEYS.profileSyncLast,
      initial: () => '',
      codec: rawStringCodec(),
      crossTab: true,
    });
    store.hydrate();
    store.hydrate();
    expect(
      addEventListener.mock.calls.filter(([event]) => event === 'storage'),
    ).toHaveLength(1);

    localStorage.setItem(PERSISTENCE_KEYS.profileSyncLast, 'remote-value');
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: PERSISTENCE_KEYS.profileSyncLast,
        storageArea: localStorage,
      }),
    );
    expect(get(store).value).toBe('remote-value');
    expect(setItem).not.toHaveBeenCalled();
  });

  it('enables cross-tab reads only for local application stores', () => {
    expect(compare.crossTab).toBe(true);
    expect(fcRoute.crossTab).toBe(true);
    expect(adminToken.area).toBe('session');
    expect(adminToken.crossTab).toBe(false);
  });

  it('updates Compare from a guarded native cross-tab event', () => {
    compare.hydrate();
    localStorage.setItem(
      PERSISTENCE_KEYS.compare,
      JSON.stringify([{ id64: '18446744073709551615', name: 'Remote max' }]),
    );
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: PERSISTENCE_KEYS.compare,
        storageArea: localStorage,
      }),
    );
    expect(get(compare).value).toEqual([
      { id64: '18446744073709551615', name: 'Remote max' },
    ]);
  });

  it('updates FC state cross-tab and backfills remote legacy config', () => {
    fcRoute.hydrate();
    localStorage.setItem(
      PERSISTENCE_KEYS.fcRoute,
      JSON.stringify({
        waypoints: [
          {
            id: 'wp-remote',
            name: 'Achenar',
            x: 67,
            y: 12,
            z: -33,
            id64: 123,
          },
        ],
        config: { jump_range_ly: 420 },
      }),
    );
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: PERSISTENCE_KEYS.fcRoute,
        storageArea: localStorage,
      }),
    );
    expect(get(fcRoute).value).toMatchObject({
      waypoints: [{ id64: '123', name: 'Achenar' }],
      config: { ...DEFAULT_FC_CONFIG, jump_range_ly: 420 },
    });
  });

  it('defaults and writes the raw density preference', () => {
    density.hydrate();
    expect(get(density).value).toBe('comfortable');
    expect(localStorage.getItem(PERSISTENCE_KEYS.density)).toBe('comfortable');

    expect(density.set('spacious')).toBe(true);
    expect(localStorage.getItem(PERSISTENCE_KEYS.density)).toBe('spacious');
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
