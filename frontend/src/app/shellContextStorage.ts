import { readStorageItem, removeStorageItem, writeStorageItem } from '@/lib/browserStorage';

export const SHELL_SELECTED_SYSTEM_STORAGE_KEY = 'ed-finder:selected-system-context';

export function readPersistedShellContextSystemId(): number | null {
  const raw = readStorageItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function persistShellContextSystemId(id64: number | null) {
  if (id64 == null) {
    removeStorageItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY);
    return;
  }
  writeStorageItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY, String(id64));
}
