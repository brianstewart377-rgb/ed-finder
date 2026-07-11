import type { StateStorage } from 'zustand/middleware';

type BrowserStorageKind = 'localStorage' | 'sessionStorage';

function readBrowserStorageItem(storageKind: BrowserStorageKind, key: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window[storageKind].getItem(key);
  } catch {
    return null;
  }
}

function writeBrowserStorageItem(storageKind: BrowserStorageKind, key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window[storageKind].setItem(key, value);
  } catch {
    // Ignore quota and private-mode failures; callers degrade in-memory.
  }
}

function removeBrowserStorageItem(storageKind: BrowserStorageKind, key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window[storageKind].removeItem(key);
  } catch {
    // Ignore quota and private-mode failures; callers degrade in-memory.
  }
}

export function readStorageItem(key: string): string | null {
  return readBrowserStorageItem('localStorage', key);
}

export function writeStorageItem(key: string, value: string): void {
  writeBrowserStorageItem('localStorage', key, value);
}

export function removeStorageItem(key: string): void {
  removeBrowserStorageItem('localStorage', key);
}

export function readSessionStorageItem(key: string): string | null {
  return readBrowserStorageItem('sessionStorage', key);
}

export function writeSessionStorageItem(key: string, value: string): void {
  writeBrowserStorageItem('sessionStorage', key, value);
}

export function removeSessionStorageItem(key: string): void {
  removeBrowserStorageItem('sessionStorage', key);
}

export function readJsonStorage<T>(key: string, fallback: T): T {
  const raw = readStorageItem(key);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJsonStorage(key: string, value: unknown): void {
  writeStorageItem(key, JSON.stringify(value));
}

export function readJsonSessionStorage<T>(key: string, fallback: T): T {
  const raw = readSessionStorageItem(key);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJsonSessionStorage(key: string, value: unknown): void {
  writeSessionStorageItem(key, JSON.stringify(value));
}

export const localStateStorage: StateStorage = {
  getItem: (key) => readStorageItem(key),
  setItem: (key, value) => writeStorageItem(key, value),
  removeItem: (key) => removeStorageItem(key),
};

export const sessionStateStorage: StateStorage = {
  getItem: (key) => readSessionStorageItem(key),
  setItem: (key, value) => writeSessionStorageItem(key, value),
  removeItem: (key) => removeSessionStorageItem(key),
};
