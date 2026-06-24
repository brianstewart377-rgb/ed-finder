import type { PinnedEntry } from './usePinned';

/**
 * Factory helper so call-sites don't have to spell out the whole PinnedEntry
 * shape when toggling.
 */
export function toPinnedEntry(sys: {
  id64:         number;
  name:         string;
  coords?:      { x?: number | null; y?: number | null; z?: number | null } | null;
  distance?:    number | null;
  population?:  number | null;
  is_colonised?: boolean | null;
  _rating?:     { score?: number | null; economySuggestion?: string | null } | null;
}): PinnedEntry {
  return {
    id64:         sys.id64,
    name:         sys.name,
    x:            sys.coords?.x ?? null,
    y:            sys.coords?.y ?? null,
    z:            sys.coords?.z ?? null,
    population:   sys.population ?? null,
    is_colonised: !!sys.is_colonised,
    distance:     sys.distance ?? null,
    rating:       sys._rating?.score ?? null,
    economy:      sys._rating?.economySuggestion ?? null,
    pinned_at:    new Date().toISOString(),
  };
}
