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
  archetype_score?: number | null;
  primary_archetype?: string | null;
  secondary_archetype?: string | null;
  buildability_score?: number | null;
  purity_score?: number | null;
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
    archetype_score: sys.archetype_score ?? null,
    primary_archetype: sys.primary_archetype ?? null,
    secondary_archetype: sys.secondary_archetype ?? null,
    buildability_score: sys.buildability_score ?? null,
    purity_score: sys.purity_score ?? null,
    pinned_at:    new Date().toISOString(),
  };
}
