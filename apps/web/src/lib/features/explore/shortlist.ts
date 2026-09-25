import { get } from 'svelte/store';
import type { ExploreSystem, WatchlistEntry } from '$lib/api/client';
import type {
  CompareEntry,
  PersistedStore,
  PinnedEntry,
} from '$lib/persistence/storage';
import { COMPARE_MAX } from './compare-metrics';

type SelectionResult = { selected: boolean; error: string | null };
const saveError =
  'Your shortlist could not be saved in this browser. Check browser storage before leaving this page.';

export function snapshotFromExplore(system: ExploreSystem): CompareEntry {
  return {
    ...system,
    name: system.name?.trim() || `System ${system.id64}`,
    archetype_score:
      system.archetype_score ?? system.overall_development_potential ?? null,
  };
}

export function snapshotFromPin(pin: PinnedEntry): CompareEntry {
  return {
    ...pin,
    coords: pin.coords ?? {
      x: pin.x ?? null,
      y: pin.y ?? null,
      z: pin.z ?? null,
    },
    // Legacy pin.economy is a suggestion, not the system's current economy.
    primaryEconomy: pin.primaryEconomy ?? pin.primary_economy ?? null,
  };
}

export function snapshotFromWatchlist(entry: WatchlistEntry): CompareEntry {
  return {
    id64: entry.system_id64,
    name: entry.name,
    coords: { x: entry.x ?? null, y: entry.y ?? null, z: entry.z ?? null },
    population: entry.population,
    is_colonised: entry.is_colonised,
    archetype_score: entry.archetype_score ?? entry.score ?? null,
    primary_archetype: entry.primary_archetype,
    secondary_archetype: entry.secondary_archetype,
    buildability_score: entry.buildability_score,
    purity_score: entry.purity_score,
    economy_suggestion: entry.economy_suggestion,
  };
}

/** Retain complete snapshots so a different Finder search never loses facts. */
export function toggleComparison(
  store: PersistedStore<CompareEntry[]>,
  snapshot: CompareEntry,
): SelectionResult {
  const entries = get(store).value;
  const exists = entries.some((entry) => entry.id64 === snapshot.id64);
  if (!exists && entries.length >= COMPARE_MAX) {
    return {
      selected: false,
      error: `Comparison is full (max ${COMPARE_MAX}). Remove a system first.`,
    };
  }
  const saved = store.set(
    exists
      ? entries.filter((entry) => entry.id64 !== snapshot.id64)
      : [...entries, snapshot],
  );
  return {
    selected: get(store).value.some((entry) => entry.id64 === snapshot.id64),
    error: saved ? null : saveError,
  };
}

export function togglePin(
  store: PersistedStore<PinnedEntry[]>,
  snapshot: CompareEntry,
): SelectionResult {
  const entries = get(store).value;
  const exists = entries.some((entry) => entry.id64 === snapshot.id64);
  const coords =
    snapshot.coords && typeof snapshot.coords === 'object'
      ? (snapshot.coords as Record<string, unknown>)
      : {};
  const pin: PinnedEntry = {
    ...snapshot,
    x: coords.x ?? null,
    y: coords.y ?? null,
    z: coords.z ?? null,
    economy: snapshot.economy_suggestion ?? snapshot.primaryEconomy ?? null,
    pinned_at: new Date().toISOString(),
  };
  const saved = store.set(
    exists
      ? entries.filter((entry) => entry.id64 !== snapshot.id64)
      : [pin, ...entries],
  );
  return {
    selected: get(store).value.some((entry) => entry.id64 === snapshot.id64),
    error: saved ? null : saveError,
  };
}
