import { get } from 'svelte/store';

import {
  collectionCodec,
  compareCodec,
  createPersistedStore,
  densityCodec,
  fcCodec,
  id64StringCodec,
  nullableCodec,
  pinnedCodec,
  rawStringCodec,
  selectedRouteCodec,
  syncKeyCodec,
  type CompareEntry,
  type FcState,
  type JsonRecord,
  type PinnedEntry,
  type VersionedCollection,
} from './storage';
import type { Id64 } from '../domain/id64';

const emptyCollection = (): VersionedCollection => ({ state: {}, version: 0 });

export const pins = createPersistedStore<PinnedEntry[]>({
  key: 'ed_pinned',
  initial: () => [],
  codec: pinnedCodec,
  crossTab: true,
});
export const compare = createPersistedStore<CompareEntry[]>({
  key: 'ed_compare_v2',
  initial: () => [],
  codec: compareCodec,
  crossTab: true,
});
export const syncKey = createPersistedStore({
  key: 'ed_sync_key',
  initial: () => ({ state: { syncKey: '' }, version: 0 }),
  codec: syncKeyCodec,
  crossTab: true,
});
export const selectedRoute = createPersistedStore({
  key: 'ed_selected_route',
  initial: () => ({ state: { selectedRouteId: null }, version: 0 }),
  codec: selectedRouteCodec,
  crossTab: true,
});
export const myWork = createPersistedStore({
  key: 'ed_my_work_v1',
  initial: emptyCollection,
  codec: collectionCodec(1),
  crossTab: true,
});
export const colonyProjects = createPersistedStore({
  key: 'ed_colony_projects_v1',
  initial: emptyCollection,
  codec: collectionCodec(3),
  crossTab: true,
});
export const expansionPlans = createPersistedStore({
  key: 'ed_expansion_plans_v1',
  initial: emptyCollection,
  codec: collectionCodec(1),
  crossTab: true,
});
export const fcRoute = createPersistedStore<FcState>({
  key: 'ed_fc_v2',
  initial: () => ({ waypoints: [], config: {} }),
  codec: fcCodec,
  crossTab: true,
});
export const profileSyncKey = createPersistedStore({
  key: 'ed_profile_sync_key',
  initial: () => '',
  codec: rawStringCodec(),
  crossTab: true,
});
export const profileSyncLast = createPersistedStore({
  key: 'ed_profile_sync_last',
  initial: () => '',
  codec: rawStringCodec(),
  crossTab: true,
});
export const selectedSystem = createPersistedStore<Id64 | null>({
  key: 'ed-finder:selected-system-context',
  initial: () => null,
  codec: nullableCodec(id64StringCodec),
  crossTab: true,
});
export const density = createPersistedStore({
  key: 'ed_density_v1',
  initial: () => 'comfortable',
  codec: densityCodec,
  crossTab: true,
});
export const adminToken = createPersistedStore({
  key: 'ed_admin_token',
  area: 'session',
  initial: () => '',
  codec: rawStringCodec(),
});
export const operatorHandoff = createPersistedStore({
  key: 'ed_operator_selected_source_run',
  area: 'session',
  initial: () => '',
  codec: rawStringCodec(),
});

export const applicationStores = {
  pins,
  compare,
  syncKey,
  selectedRoute,
  myWork,
  colonyProjects,
  expansionPlans,
  fcRoute,
  profileSyncKey,
  profileSyncLast,
  selectedSystem,
  density,
  adminToken,
  operatorHandoff,
};

let applicationStoresHydrated = false;

export function hydrateApplicationStores(): void {
  if (applicationStoresHydrated) return;
  applicationStoresHydrated = true;
  for (const store of Object.values(applicationStores)) store.hydrate();
}

/** Test seam for proving boot idempotence without weakening runtime ownership. */
export function resetApplicationStoreHydrationForTest(): void {
  if (import.meta.env.MODE !== 'test')
    throw new Error('Application-store hydration can only be reset in tests');
  applicationStoresHydrated = false;
}

/** Diagnostics are safe to render: they never contain persisted values or session tokens. */
export function persistenceDiagnostics() {
  const stores = Object.values(applicationStores) as Array<{
    subscribe: (
      run: (value: { diagnostic: unknown | null }) => void,
    ) => () => void;
  }>;
  return stores.flatMap((store) => {
    const state = get(store);
    return state.diagnostic ? [state.diagnostic] : [];
  });
}

export type MyWorkState = VersionedCollection & {
  state: JsonRecord & { systems?: Record<string, JsonRecord> };
};
