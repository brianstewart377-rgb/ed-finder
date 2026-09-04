import { browser } from '$app/environment';
export const keys = {
  pinned: 'ed_pinned',
  compare: 'ed_compare_v2',
  sync: 'ed_sync_key',
  selectedRoute: 'ed_selected_route',
  myWork: 'ed_my_work_v1',
  colony: 'ed_colony_projects_v1',
  expansion: 'ed_expansion_plans_v1',
  fc: 'ed_fc_v2',
  profileSync: 'ed_profile_sync_key',
  profileLast: 'ed_profile_sync_last',
  selectedSystem: 'ed-finder:selected-system-context',
  density: 'ed_density_v1',
  admin: 'ed_admin_token',
  operatorRun: 'ed_operator_selected_source_run',
} as const;
function json(key: string, fallback: unknown) {
  if (!browser) return fallback;
  try {
    return JSON.parse(localStorage.getItem(key) ?? '') as unknown;
  } catch {
    return fallback;
  }
}
function state(key: string, fallback: unknown) {
  const value = json(key, fallback);
  return value && typeof value === 'object' && 'state' in value
    ? (value as { state: unknown }).state
    : value;
}
function makeKey() {
  const a = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_',
    b = crypto.getRandomValues(new Uint8Array(32));
  return Array.from(b, (x) => a[x % a.length]).join('');
}
export type Pin = {
  id64: string | number;
  name: string;
  pinned_at?: string;
  [key: string]: unknown;
};
export class PersistentState {
  pins = $state<Pin[]>([]);
  compare = $state<unknown>({});
  syncKey = $state('');
  contracts = $state<Record<string, unknown>>({});
  density = $state('comfortable');
  hydrate() {
    if (!browser) return;
    const pins = json(keys.pinned, []);
    this.pins = Array.isArray(pins) ? (pins as Pin[]) : [];
    this.compare = state(keys.compare, {});
    const sync = state(keys.sync, {}) as { syncKey?: string };
    this.syncKey =
      sync.syncKey && /^[\w-]{16,128}$/.test(sync.syncKey)
        ? sync.syncKey
        : makeKey();
    const bare = new Set<string>([
      keys.profileSync,
      keys.profileLast,
      keys.selectedSystem,
    ]);
    this.contracts = Object.fromEntries(
      [
        keys.selectedRoute,
        keys.myWork,
        keys.colony,
        keys.expansion,
        keys.fc,
        keys.profileSync,
        keys.profileLast,
        keys.selectedSystem,
      ].map((key) => [
        key,
        bare.has(key) ? localStorage.getItem(key) : state(key, {}),
      ]),
    );
    this.density = ['compact', 'comfortable', 'spacious'].includes(
      localStorage.getItem(keys.density) ?? '',
    )
      ? localStorage.getItem(keys.density)!
      : 'comfortable';
    document.documentElement.dataset.density = this.density;
    if (!localStorage.getItem(keys.sync)) this.persistSyncKey();
  }
  persistSyncKey() {
    localStorage.setItem(
      keys.sync,
      JSON.stringify({ state: { syncKey: this.syncKey }, version: 0 }),
    );
  }
  togglePin(pin: Pin) {
    const key = String(pin.id64);
    this.pins = this.pins.some((x) => String(x.id64) === key)
      ? this.pins.filter((x) => String(x.id64) !== key)
      : [
          {
            ...pin,
            id64: key,
            pinned_at: pin.pinned_at || new Date().toISOString(),
          },
          ...this.pins,
        ];
    localStorage.setItem(keys.pinned, JSON.stringify(this.pins));
  }
}
export const persistentState = new PersistentState();
