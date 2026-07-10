import { useCallback, useEffect, useState } from 'react';
import {
  rehydrateColonyProjectStore,
  type ColonyProject,
} from '@/features/colony-planner/colonyProjectStore';
import type { FcWaypoint, FcConfig } from '@/features/fc-planner/useFcPlanner';
import {
  rehydrateMyWorkStore,
  type MyWorkSystemRecord,
} from '@/features/my-work/myWorkStore';
import type { PinnedEntry } from '@/features/pinned/usePinned';
import { api, ApiError } from '@/lib/api';
import { rehydratePinnedStore } from '@/store/pinnedStore';
import type { SystemResult } from '@/types/api';

/**
 * Profile sync — pulls / pushes the user's local-only state (Pinned,
 * Compare, Colony tracker, FC route) as a single JSONB blob keyed by a
 * user-chosen sync key.
 *
 * Trust model: the sync key IS the credential. Anyone who knows it can
 * read or overwrite the slot. This matches the legacy app's threat
 * model (a single shared instance) and avoids JWT/OAuth ceremony for
 * what is effectively a notes-app-grade payload.
 *
 * UX model: **manual** push / pull buttons in the Admin tab. We do NOT
 * auto-sync on every state change because:
 *   1. It's hard to define merge semantics across two devices that have
 *      diverged (last-write-wins risks data loss).
 *   2. A noisy POST-on-every-pin would hammer the API.
 * The legacy app didn't have sync at all, so manual is already a strict
 * improvement.
 */

const SYNC_KEY_STORAGE = 'ed_profile_sync_key';
const LAST_PUSH_STORAGE = 'ed_profile_sync_last';

interface PersistedStoreEnvelope<TState> {
  state: TState;
  version?: number;
}

interface LegacyColonyEntry {
  id: string;
  name: string;
  phase: 'planning' | 'building' | 'active' | 'complete';
  target_population: number | null;
  notes: string;
  id64: number | null;
  x: number | null;
  y: number | null;
  z: number | null;
  current_population: number | null;
  claimed_at: string;
  updated_at: string;
}

/** What we serialise to the slot. Each top-level field maps 1:1 to the
 *  localStorage key used by the corresponding feature, so push/pull is a
 *  trivial copy. New tabs just add a key here and to gather/apply. */
export interface ProfileBlob {
  version:    1;
  exported_at: string;
  ed_pinned?:    PinnedEntry[];
  ed_compare_v2?: SystemResult[];
  ed_colony_v2?:  LegacyColonyEntry[];
  ed_fc_v2?:      { waypoints: FcWaypoint[]; config: FcConfig };
  ed_my_work_v1?: PersistedStoreEnvelope<{ systems: Record<string, MyWorkSystemRecord> }>;
  ed_colony_projects_v1?: PersistedStoreEnvelope<{ projects: Record<string, ColonyProject> }>;
}

function gatherLocalBlob(): ProfileBlob {
  const read = <T,>(key: string): T | undefined => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : undefined;
    } catch { return undefined; }
  };
  return {
    version:        1,
    exported_at:    new Date().toISOString(),
    ed_pinned:      read('ed_pinned'),
    ed_compare_v2:  read('ed_compare_v2'),
    ed_colony_v2:   read('ed_colony_v2'),
    ed_fc_v2:       read('ed_fc_v2'),
    ed_my_work_v1:  read('ed_my_work_v1'),
    ed_colony_projects_v1: read('ed_colony_projects_v1'),
  };
}

function applyLocalBlob(blob: ProfileBlob): void {
  // Only write keys that are present + valid in the blob. Missing keys
  // are NOT cleared — pulling on a fresh device should add data, not
  // wipe local-only branches that the remote slot doesn't know about.
  const writeIf = (key: string, value: unknown) => {
    if (value !== undefined && value !== null) {
      try { localStorage.setItem(key, JSON.stringify(value)); }
      catch { /* quota / private mode */ }
    }
  };
  writeIf('ed_pinned',     blob.ed_pinned);
  writeIf('ed_compare_v2', blob.ed_compare_v2);
  writeIf('ed_colony_v2',  blob.ed_colony_v2);
  writeIf('ed_fc_v2',      blob.ed_fc_v2);
  writeIf('ed_my_work_v1', blob.ed_my_work_v1);
  writeIf('ed_colony_projects_v1', blob.ed_colony_projects_v1);

  void rehydratePinnedStore();
  void rehydrateMyWorkStore();
  void rehydrateColonyProjectStore();

  void rehydratePinnedStore();

  // Force the in-memory hooks to re-read by firing a synthetic 'storage'
  // event. They listen for it to support cross-tab sync; we get a
  // free re-render in this tab too.
  // (Same-window storage events aren't fired automatically; we dispatch
  // one per key — so all listening hooks pick up the change.)
  for (const key of ['ed_pinned', 'ed_compare_v2', 'ed_colony_v2', 'ed_fc_v2', 'ed_my_work_v1', 'ed_colony_projects_v1']) {
    window.dispatchEvent(new StorageEvent('storage', {
      key, newValue: localStorage.getItem(key),
    }));
  }
}

export type SyncState =
  | { kind: 'idle' }
  | { kind: 'busy'; what: 'pull' | 'push' }
  | { kind: 'ok';   what: 'pull' | 'push'; bytes?: number; updated_at: string }
  | { kind: 'err';  what: 'pull' | 'push'; message: string };

export interface UseProfileSync {
  syncKey:     string;
  setSyncKey:  (k: string) => void;
  hasKey:      boolean;
  lastPushAt:  string | null;
  /** Reload the slot from the server and overwrite local state. */
  pull:  () => Promise<void>;
  /** Snapshot local state and PUT it to the slot. */
  push:  () => Promise<void>;
  state: SyncState;
  resetState: () => void;
  /** Generate a 24-char random sync key so users don't pick guessable ones. */
  generateKey: () => string;
}

export function useProfileSync(): UseProfileSync {
  const [syncKey, setSyncKeyState] = useState<string>(
    () => localStorage.getItem(SYNC_KEY_STORAGE) ?? '',
  );
  const [lastPushAt, setLastPushAt] = useState<string | null>(
    () => localStorage.getItem(LAST_PUSH_STORAGE),
  );
  const [state, setState] = useState<SyncState>({ kind: 'idle' });

  // Cross-tab sync of the key itself (so signing in on one tab doesn't
  // leave others without a key).
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === SYNC_KEY_STORAGE)  setSyncKeyState(e.newValue ?? '');
      if (e.key === LAST_PUSH_STORAGE) setLastPushAt(e.newValue);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setSyncKey = useCallback((k: string) => {
    setSyncKeyState(k);
    if (k) localStorage.setItem(SYNC_KEY_STORAGE, k);
    else   localStorage.removeItem(SYNC_KEY_STORAGE);
  }, []);

  const pull = useCallback(async () => {
    if (!syncKey) return;
    setState({ kind: 'busy', what: 'pull' });
    try {
      const data = await api.profileSyncPull<ProfileBlob>(syncKey);
      applyLocalBlob(data.blob);
      setState({ kind: 'ok', what: 'pull', bytes: data.blob_bytes, updated_at: data.updated_at });
    } catch (e: unknown) {
      const message = e instanceof ApiError && e.status === 404
        ? 'Slot is empty — push from another device first.'
        : e instanceof Error ? e.message : String(e);
      setState({
        kind:    'err',
        what:    'pull',
        message,
      });
    }
  }, [syncKey]);

  const push = useCallback(async () => {
    if (!syncKey) return;
    setState({ kind: 'busy', what: 'push' });
    try {
      const blob = gatherLocalBlob();
      const data = await api.profileSyncPush(syncKey, blob);
      localStorage.setItem(LAST_PUSH_STORAGE, data.updated_at);
      setLastPushAt(data.updated_at);
      setState({ kind: 'ok', what: 'push', bytes: data.blob_bytes, updated_at: data.updated_at });
    } catch (e: unknown) {
      setState({
        kind:    'err',
        what:    'push',
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [syncKey]);

  const generateKey = useCallback((): string => {
    // 24 chars from a 64-symbol alphabet ≈ 144 bits. More than enough.
    const bytes = new Uint8Array(18);
    crypto.getRandomValues(bytes);
    return btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
      .slice(0, 24);
  }, []);

  const resetState = useCallback(() => setState({ kind: 'idle' }), []);

  return {
    syncKey, setSyncKey, hasKey: syncKey.length >= 16,
    lastPushAt,
    pull, push, state, resetState, generateKey,
  };
}
