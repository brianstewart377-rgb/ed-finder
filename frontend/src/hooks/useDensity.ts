import { useEffect, useState, useCallback } from 'react';
import { readStorageItem, writeStorageItem } from '@/lib/browserStorage';

/**
 * UI density toggle. Persists across reloads in localStorage and applies
 * a class to <html>. Three states cycle in order:
 *
 *   compact  →  comfortable (default)  →  spacious  →  compact …
 *
 * Pure-CSS scaling of root font-size + .panel padding (in src/index.css).
 * Components using Tailwind's pixel utilities (text-[12px], px-4) are
 * less affected; components using rem/em scale fully. Good enough for an
 * "I'd like a bit more breathing room" knob without a full theme refactor.
 */
export type Density = 'compact' | 'comfortable' | 'spacious';

const STORAGE_KEY = 'ed_density_v1';
const ORDER: Density[] = ['compact', 'comfortable', 'spacious'];

function readInitial(): Density {
  const raw = readStorageItem(STORAGE_KEY);
  return raw === 'compact' || raw === 'spacious' ? raw : 'comfortable';
}

function applyToDom(density: Density) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.remove('density-compact', 'density-comfortable', 'density-spacious');
  root.classList.add(`density-${density}`);
}

export function useDensity() {
  const [density, setDensityState] = useState<Density>(readInitial);

  useEffect(() => {
    applyToDom(density);
    writeStorageItem(STORAGE_KEY, density);
  }, [density]);

  const setDensity = useCallback((d: Density) => setDensityState(d), []);
  const cycle      = useCallback(() => {
    setDensityState((prev) => {
      const idx = ORDER.indexOf(prev);
      return ORDER[(idx + 1) % ORDER.length];
    });
  }, []);

  return { density, setDensity, cycle };
}
