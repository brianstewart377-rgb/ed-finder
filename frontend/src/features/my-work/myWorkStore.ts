import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { localStateStorage } from '@/lib/browserStorage';

export type SavedSystemLabel = 'considering' | 'favourite' | 'ready_to_plan';

export interface SavedSystemSnapshot {
  id64: number;
  name: string;
  x: number | null;
  y: number | null;
  z: number | null;
  population: number | null;
  is_colonised: boolean;
}

export interface MyWorkSystemRecord extends SavedSystemSnapshot {
  labels: SavedSystemLabel[];
  explicit_colonised_at: string | null;
  updated_at: string;
}

interface MyWorkState {
  systems: Record<string, MyWorkSystemRecord>;
  rememberSystem: (snapshot: SavedSystemSnapshot) => void;
  setLabel: (snapshot: SavedSystemSnapshot, label: SavedSystemLabel, enabled: boolean) => void;
  setExplicitColonised: (snapshot: SavedSystemSnapshot, enabled: boolean) => void;
  clearSystemMetadata: (id64: number) => void;
}

const STORAGE_KEY = 'ed_my_work_v1';
const SKIP_PERSIST_HYDRATION = import.meta.env.MODE === 'test';

export const useMyWorkStore = create<MyWorkState>()(
  persist(
    (set, get) => ({
      systems: {},
      rememberSystem: (snapshot) => {
        const key = String(snapshot.id64);
        const existing = get().systems[key];
        const next = normaliseRecord({
          ...(existing ?? { labels: [], explicit_colonised_at: null, updated_at: new Date().toISOString() }),
          ...snapshot,
          updated_at: existing?.updated_at ?? new Date().toISOString(),
        });
        set((state) => ({
          systems: {
            ...state.systems,
            [key]: next,
          },
        }));
      },
      setLabel: (snapshot, label, enabled) => {
        const key = String(snapshot.id64);
        const existing = get().systems[key];
        const labelSet = new Set(existing?.labels ?? []);
        if (enabled) {
          labelSet.add(label);
        } else {
          labelSet.delete(label);
        }
        const next = normaliseRecord({
          ...(existing ?? { explicit_colonised_at: null, updated_at: new Date().toISOString() }),
          ...snapshot,
          labels: Array.from(labelSet),
          updated_at: new Date().toISOString(),
        });
        set((state) => ({
          systems: {
            ...state.systems,
            [key]: next,
          },
        }));
      },
      setExplicitColonised: (snapshot, enabled) => {
        const key = String(snapshot.id64);
        const existing = get().systems[key];
        const next = normaliseRecord({
          ...(existing ?? { labels: [], updated_at: new Date().toISOString() }),
          ...snapshot,
          explicit_colonised_at: enabled ? new Date().toISOString() : null,
          updated_at: new Date().toISOString(),
        });
        set((state) => ({
          systems: {
            ...state.systems,
            [key]: next,
          },
        }));
      },
      clearSystemMetadata: (id64) => {
        const key = String(id64);
        set((state) => {
          const systems = { ...state.systems };
          delete systems[key];
          return { systems };
        });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStateStorage),
      skipHydration: SKIP_PERSIST_HYDRATION,
      version: 1,
      migrate: (persistedState) => ({
        ...(persistedState as Partial<MyWorkState> | undefined),
        systems: normaliseSystemRecord((persistedState as { systems?: unknown } | undefined)?.systems),
      }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as Partial<MyWorkState> | undefined),
        systems: normaliseSystemRecord((persistedState as { systems?: unknown } | undefined)?.systems),
      }),
    },
  ),
);

export function rehydrateMyWorkStore(): Promise<void> {
  return Promise.resolve(useMyWorkStore.persist.rehydrate());
}

function normaliseRecord(record: Partial<MyWorkSystemRecord> & Pick<MyWorkSystemRecord, 'id64'>): MyWorkSystemRecord {
  return {
    id64: record.id64,
    name: record.name?.trim() || `System ${record.id64}`,
    x: record.x ?? null,
    y: record.y ?? null,
    z: record.z ?? null,
    population: record.population ?? null,
    is_colonised: Boolean(record.is_colonised),
    labels: normaliseLabels(record.labels),
    explicit_colonised_at: record.explicit_colonised_at ?? null,
    updated_at: record.updated_at ?? new Date().toISOString(),
  };
}

function normaliseSystemRecord(value: unknown): Record<string, MyWorkSystemRecord> {
  const entries = value && typeof value === 'object' ? Object.values(value) : [];
  return entries.reduce<Record<string, MyWorkSystemRecord>>((record, candidate) => {
    if (!candidate || typeof candidate !== 'object') return record;
    const system = candidate as Partial<MyWorkSystemRecord>;
    if (!system.id64 || !Number.isFinite(system.id64)) return record;
    record[String(system.id64)] = normaliseRecord(system as Partial<MyWorkSystemRecord> & Pick<MyWorkSystemRecord, 'id64'>);
    return record;
  }, {});
}

function normaliseLabels(labels: unknown): SavedSystemLabel[] {
  if (!Array.isArray(labels)) return [];
  const unique = new Set<SavedSystemLabel>();
  for (const candidate of labels) {
    if (candidate === 'considering' || candidate === 'favourite' || candidate === 'ready_to_plan') {
      unique.add(candidate);
    }
  }
  return Array.from(unique);
}
