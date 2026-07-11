/**
 * Sync-key store (Zustand + persist).
 *
 * Phase 3 frontend companion to AUDIT_REPORT.md §H1: the new server-side
 * watchlist + notes endpoints (/api/v2/watchlist/{sync_key}/...) require
 * a 16-128 char user-chosen key. This store centralises that key:
 *
 *   • Persisted to localStorage under `ed_sync_key`.
 *   • Auto-generated on first use (32 chars, URL-safe).
 *   • User can edit it (paste a key from another device to sync) or
 *     reset it (will lose access to existing slot's data unless they
 *     remember the old key).
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { localStateStorage } from '@/lib/browserStorage';

const ALPHABET =
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

function generate(length = 32): string {
  // Use crypto.getRandomValues when available (always in modern browsers
  // and in jsdom 22+). Fall back to Math.random for very old envs —
  // these keys are not cryptographic credentials, just unguessable.
  const bytes = new Uint8Array(length);
  if (typeof crypto !== 'undefined' && 'getRandomValues' in crypto) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  let out = '';
  for (let i = 0; i < length; i += 1) {
    out += ALPHABET[bytes[i] % ALPHABET.length];
  }
  return out;
}

const SYNC_KEY_RE = /^[A-Za-z0-9_-]{16,128}$/;

interface SyncKeyState {
  syncKey: string;
  /** Reset to a fresh random key — orphans the existing server-side data. */
  regenerate: () => void;
  /** Adopt a key from another device (e.g. user pastes it). */
  setKey: (key: string) => boolean;
}

const SKIP_PERSIST_HYDRATION = import.meta.env.MODE === 'test';

export const useSyncKeyStore = create<SyncKeyState>()(
  persist(
    (set) => ({
      syncKey: generate(),
      regenerate: () => set({ syncKey: generate() }),
      setKey: (key: string) => {
        const trimmed = key.trim();
        if (!SYNC_KEY_RE.test(trimmed) || trimmed === 'legacy') return false;
        set({ syncKey: trimmed });
        return true;
      },
    }),
    {
      name:    'ed_sync_key',
      storage: createJSONStorage(() => localStateStorage),
      skipHydration: SKIP_PERSIST_HYDRATION,
    },
  ),
);

export function rehydrateSyncKeyStore(): Promise<void> {
  return Promise.resolve(useSyncKeyStore.persist.rehydrate());
}
