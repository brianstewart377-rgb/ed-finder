import { useEffect, useState } from 'react';

/**
 * Hash-based router with optional `system/{id64}` sub-route.
 *
 * Supported hash formats (in priority order):
 *   #finder                       → route='finder',    selectedSystemId=null
 *   #pinned                       → route='pinned',    selectedSystemId=null
 *   #pinned/system/12345678       → route='pinned',    selectedSystemId=12345678
 *   #search-tuning                → route='search-tuning', selectedSystemId=null
 *   #optimizer                    → route='search-tuning', selectedSystemId=null (legacy alias)
 *   #system/12345678              → route='finder',    selectedSystemId=12345678   (deep-link from external)
 *   <empty> or unknown            → route='finder',    selectedSystemId=null
 *
 * The system sub-route is intentionally a **child** of each tab so closing
 * the modal restores the user to the same tab they were on. External links
 * (#system/N alone) default to the Finder tab as a sensible landing.
 *
 * 4-tab + sub-route is still simple enough that this hand-rolled parser
 * beats pulling in react-router. Re-evaluate that trade-off when v2 sprouts
 * its 6th sub-route.
 */
export type Route = 'finder' | 'watchlist' | 'pinned' | 'compare' | 'map' | 'search-tuning' | 'fc' | 'colony' | 'admin';
const VALID_ROUTES: Route[] = ['finder', 'watchlist', 'pinned', 'compare', 'map', 'search-tuning', 'fc', 'colony', 'admin'];

export interface ParsedHash {
  route:            Route;
  selectedSystemId: number | null;
}

function parseHash(): ParsedHash {
  const raw   = window.location.hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean);

  if (parts.length === 0) return { route: 'finder', selectedSystemId: null };

  let route: Route = 'finder';
  let i = 0;
  if (parts[0] === 'optimizer') {
    route = 'search-tuning';
    i = 1;
  } else if ((VALID_ROUTES as string[]).includes(parts[0])) {
    route = parts[0] as Route;
    i = 1;
  }

  let selectedSystemId: number | null = null;
  if (parts[i] === 'system' && parts[i + 1]) {
    const n = Number(parts[i + 1]);
    if (Number.isFinite(n) && n > 0) selectedSystemId = n;
  }

  return { route, selectedSystemId };
}

function buildHash(route: Route, selectedSystemId: number | null): string {
  const base = `#${route}`;
  return selectedSystemId != null ? `${base}/system/${selectedSystemId}` : base;
}

export interface HashRoute {
  route:            Route;
  selectedSystemId: number | null;
  /** Navigate to a tab. Preserves any open system modal. */
  navigate:    (r: Route) => void;
  /** Open the system detail modal on top of the current tab. */
  openSystem:  (id64: number) => void;
  /** Close the modal — pops back to the current tab. */
  closeSystem: () => void;
}

export function useHashRoute(): HashRoute {
  const [parsed, setParsed] = useState<ParsedHash>(parseHash);

  useEffect(() => {
    const onHash = () => setParsed(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = (r: Route) => {
    window.location.hash = buildHash(r, parsed.selectedSystemId);
  };

  const openSystem = (id64: number) => {
    window.location.hash = buildHash(parsed.route, id64);
  };

  const closeSystem = () => {
    window.location.hash = buildHash(parsed.route, null);
  };

  return {
    route:            parsed.route,
    selectedSystemId: parsed.selectedSystemId,
    navigate, openSystem, closeSystem,
  };
}
