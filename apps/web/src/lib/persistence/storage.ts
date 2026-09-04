import { writable, type Readable } from 'svelte/store';

import { parseId64, type Id64 } from '../domain/id64';

export const LOCAL_STORAGE_KEYS = [
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
] as const;

export const SESSION_STORAGE_KEYS = [
  'ed_admin_token',
  'ed_operator_selected_source_run',
] as const;

export type LocalStorageKey = (typeof LOCAL_STORAGE_KEYS)[number];
export type SessionStorageKey = (typeof SESSION_STORAGE_KEYS)[number];
export type StorageAreaName = 'local' | 'session';
export type PersistenceProblem =
  'corrupt-json' | 'invalid-shape' | 'unsupported-version' | 'unavailable';

export interface PersistenceDiagnostic {
  key: LocalStorageKey | SessionStorageKey;
  problem: PersistenceProblem;
  /** Raw data is deliberately not included: session values may be sensitive. */
  detail: string;
  recoverable: boolean;
}

export interface PersistedState<T> {
  value: T;
  hydrated: boolean;
  diagnostic: PersistenceDiagnostic | null;
}

type DecodeResult<T> =
  | { ok: true; value: T }
  | { ok: false; problem: PersistenceProblem; detail: string };

export interface Codec<T> {
  readonly version: number;
  decode(raw: string): DecodeResult<T>;
  encode(value: T): string;
}

export function nullableCodec<T>(codec: Codec<T>): Codec<T | null> {
  return {
    version: codec.version,
    decode: codec.decode,
    // createPersistedStore removes null values before encoding.
    encode: (value) => (value === null ? '' : codec.encode(value)),
  };
}

function storageFor(area: StorageAreaName): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return area === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function createPersistedStore<T>(options: {
  key: LocalStorageKey | SessionStorageKey;
  area?: StorageAreaName;
  initial: () => T;
  codec: Codec<T>;
  crossTab?: boolean;
}) {
  const area = options.area ?? 'local';
  const inner = writable<PersistedState<T>>({
    value: options.initial(),
    hydrated: false,
    diagnostic: null,
  });
  let listening = false;

  function read(): PersistedState<T> {
    const storage = storageFor(area);
    if (!storage) {
      return {
        value: options.initial(),
        hydrated: true,
        diagnostic:
          typeof window === 'undefined'
            ? null
            : diagnostic('unavailable', 'Storage is unavailable', true),
      };
    }
    let raw: string | null;
    try {
      raw = storage.getItem(options.key);
    } catch {
      return {
        value: options.initial(),
        hydrated: true,
        diagnostic: diagnostic('unavailable', 'Storage read failed', true),
      };
    }
    if (raw === null)
      return { value: options.initial(), hydrated: true, diagnostic: null };
    const decoded = options.codec.decode(raw);
    return decoded.ok
      ? { value: decoded.value, hydrated: true, diagnostic: null }
      : {
          value: options.initial(),
          hydrated: true,
          diagnostic: diagnostic(decoded.problem, decoded.detail, true),
        };
  }

  function diagnostic(
    problem: PersistenceProblem,
    detail: string,
    recoverable: boolean,
  ): PersistenceDiagnostic {
    return { key: options.key, problem, detail, recoverable };
  }

  function hydrate() {
    inner.set(read());
    if (
      !listening &&
      options.crossTab &&
      area === 'local' &&
      typeof window !== 'undefined'
    ) {
      listening = true;
      window.addEventListener('storage', (event) => {
        if (
          (event.storageArea === null ||
            event.storageArea === window.localStorage) &&
          event.key === options.key
        )
          inner.set(read());
      });
    }
  }

  function set(value: T): boolean {
    const storage = storageFor(area);
    if (!storage) {
      inner.set({
        value,
        hydrated: true,
        diagnostic: diagnostic('unavailable', 'Storage is unavailable', true),
      });
      return false;
    }
    if (value === null) {
      try {
        storage.removeItem(options.key);
        inner.set({ value, hydrated: true, diagnostic: null });
        return true;
      } catch {
        return false;
      }
    }
    // A future envelope belongs to a newer application. Never erase it.
    const current = storage.getItem(options.key);
    if (current) {
      const parsed = safeJson(current);
      if (
        parsed.ok &&
        isRecord(parsed.value) &&
        typeof parsed.value.version === 'number' &&
        parsed.value.version > options.codec.version
      ) {
        inner.set({
          value,
          hydrated: true,
          diagnostic: diagnostic(
            'unsupported-version',
            `Stored version ${parsed.value.version} is newer than ${options.codec.version}`,
            true,
          ),
        });
        return false;
      }
    }
    try {
      storage.setItem(options.key, options.codec.encode(value));
      inner.set({ value, hydrated: true, diagnostic: null });
      return true;
    } catch {
      inner.set({
        value,
        hydrated: true,
        diagnostic: diagnostic('unavailable', 'Storage write failed', true),
      });
      return false;
    }
  }

  function clear(): boolean {
    const storage = storageFor(area);
    if (!storage) return false;
    try {
      storage.removeItem(options.key);
      inner.set({ value: options.initial(), hydrated: true, diagnostic: null });
      return true;
    } catch {
      return false;
    }
  }

  return {
    subscribe: inner.subscribe,
    hydrate,
    set,
    clear,
    read,
  } satisfies Readable<PersistedState<T>> & {
    hydrate(): void;
    set(value: T): boolean;
    clear(): boolean;
    read(): PersistedState<T>;
  };
}

function safeJson(raw: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) as unknown };
  } catch {
    return { ok: false };
  }
}

const jsonCodec = <T>(
  validate: (value: unknown) => T | null,
  version = 0,
): Codec<T> => ({
  version,
  decode(raw) {
    const parsed = safeJson(raw);
    if (!parsed.ok)
      return {
        ok: false,
        problem: 'corrupt-json',
        detail: 'Stored value is not valid JSON',
      };
    if (
      isRecord(parsed.value) &&
      typeof parsed.value.version === 'number' &&
      parsed.value.version > version
    ) {
      return {
        ok: false,
        problem: 'unsupported-version',
        detail: `Stored version ${parsed.value.version} is newer than ${version}`,
      };
    }
    const value = validate(parsed.value);
    return value === null
      ? {
          ok: false,
          problem: 'invalid-shape',
          detail: 'Stored value has the wrong shape',
        }
      : { ok: true, value };
  },
  encode: JSON.stringify,
});

export function rawStringCodec(
  validate: (value: string) => boolean = () => true,
): Codec<string> {
  return {
    version: 0,
    decode: (raw) =>
      validate(raw)
        ? { ok: true, value: raw }
        : {
            ok: false,
            problem: 'invalid-shape',
            detail: 'Stored string is invalid',
          },
    encode: (value) => value,
  };
}

export type JsonRecord = Record<string, unknown>;
export type PinnedEntry = JsonRecord & {
  id64: Id64;
  name: string;
  pinned_at: string;
};
export type CompareEntry = JsonRecord & { id64: Id64; name: string };
export interface FcState extends JsonRecord {
  waypoints: Array<JsonRecord & { id64?: Id64 | null }>;
  config: JsonRecord;
}
export interface VersionedCollection extends JsonRecord {
  state: JsonRecord;
  version: number;
}

function canonicaliseIds(value: unknown, key = ''): unknown {
  if (key === 'id64' || key.endsWith('_id64')) {
    if (value === null) return null;
    try {
      // Safe legacy React snapshots used numbers. Converting only safe integers
      // recovers those records without accepting already-rounded identifiers.
      if (typeof value === 'number') {
        if (!Number.isSafeInteger(value) || value < 0) return undefined;
        return parseId64(String(value));
      }
      return parseId64(value as string | bigint);
    } catch {
      return undefined;
    }
  }
  if (Array.isArray(value))
    return value
      .map((item) => canonicaliseIds(item))
      .filter((item) => item !== undefined);
  if (!isRecord(value)) return value;
  const output: JsonRecord = {};
  for (const [childKey, child] of Object.entries(value)) {
    const normalised = canonicaliseIds(child, childKey);
    if (normalised !== undefined) output[childKey] = normalised;
  }
  return output;
}

function arrayWithId(
  value: unknown,
): Array<JsonRecord & { id64: Id64 }> | null {
  if (!Array.isArray(value)) return null;
  const result: Array<JsonRecord & { id64: Id64 }> = [];
  for (const candidate of value) {
    const normalised = canonicaliseIds(candidate);
    if (!isRecord(normalised) || typeof normalised.id64 !== 'string') continue;
    result.push(normalised as JsonRecord & { id64: Id64 });
  }
  return result;
}

function collectionEnvelope(value: unknown): VersionedCollection | null {
  if (!isRecord(value) || !isRecord(value.state)) return null;
  return canonicaliseIds({
    ...value,
    version: typeof value.version === 'number' ? value.version : 0,
  }) as VersionedCollection;
}

export const pinnedCodec = jsonCodec<PinnedEntry[]>(
  (value) => arrayWithId(value) as PinnedEntry[] | null,
);
export const compareCodec = jsonCodec<CompareEntry[]>(
  (value) => arrayWithId(value) as CompareEntry[] | null,
);
export const fcCodec = jsonCodec<FcState>((value) => {
  const normalised = canonicaliseIds(value);
  if (
    !isRecord(normalised) ||
    !Array.isArray(normalised.waypoints) ||
    !isRecord(normalised.config)
  )
    return null;
  return normalised as FcState;
});
export const collectionCodec = (version: number) =>
  jsonCodec<VersionedCollection>(collectionEnvelope, version);
export const syncKeyCodec = jsonCodec<{
  state: { syncKey: string };
  version: number;
}>((value) => {
  if (
    !isRecord(value) ||
    !isRecord(value.state) ||
    typeof value.state.syncKey !== 'string'
  )
    return null;
  return {
    ...value,
    state: { ...value.state, syncKey: value.state.syncKey },
    version: typeof value.version === 'number' ? value.version : 0,
  } as { state: { syncKey: string }; version: number };
});
export const selectedRouteCodec = jsonCodec<{
  state: { selectedRouteId: string | null };
  version: number;
}>((value) => {
  if (
    !isRecord(value) ||
    !isRecord(value.state) ||
    (value.state.selectedRouteId !== null &&
      typeof value.state.selectedRouteId !== 'string')
  )
    return null;
  return {
    ...value,
    state: { ...value.state, selectedRouteId: value.state.selectedRouteId },
    version: typeof value.version === 'number' ? value.version : 0,
  } as { state: { selectedRouteId: string | null }; version: number };
});

export const id64StringCodec: Codec<Id64> = {
  version: 0,
  decode(raw) {
    try {
      return { ok: true, value: parseId64(raw) };
    } catch {
      return {
        ok: false,
        problem: 'invalid-shape',
        detail: 'Stored identifier is not a canonical uint64',
      };
    }
  },
  encode: (value) => value,
};
export const densityCodec = rawStringCodec(
  (value) =>
    value === 'compact' || value === 'comfortable' || value === 'spacious',
);

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
