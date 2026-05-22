import { useEffect, useState } from 'react';

/**
 * Hash-based router with optional `system/{id64}` sub-routes.
 *
 * Supported hash formats (in priority order):
 *   #finder                       → route='finder',    selectedSystemId=null
 *   #pinned                       → route='pinned',    selectedSystemId=null
 *   #pinned/system/12345678       → route='pinned',    selectedSystemId=12345678
 *   #search-tuning                → route='search-tuning', selectedSystemId=null
 *   #optimizer                    → route='search-tuning', selectedSystemId=null (legacy alias)
 *   #system/12345678              → route='finder',    selectedSystemId=12345678   (deep-link from external)
 *   #colony-planner/system/123    → route='colony-planner', plannerSystemId=123
 *   #colony-planner               → route='colony-planner', plannerSystemId=null
 *   #colony-planner-prototype     → route='colony-planner-prototype', static visual prototype
 *   <empty> or unknown            → route='finder',    selectedSystemId=null
 *
 * Modal system sub-routes are intentionally a **child** of each tab so
 * closing the modal restores the user to the same tab they were on. External
 * links (#system/N alone) default to the Finder tab as a sensible landing.
 *
 * Colony Planner is a dedicated workspace route, not a modal child. Its
 * `plannerSystemId` must stay separate from `selectedSystemId` so rendering
 * the workspace does not accidentally open System Detail over it.
 *
 * The route set is still simple enough that this hand-rolled parser beats
 * pulling in react-router. Re-evaluate that trade-off if nested routes grow.
 */
export type Route = 'finder' | 'watchlist' | 'pinned' | 'compare' | 'map' | 'search-tuning' | 'fc' | 'colony' | 'admin' | 'colony-planner' | 'colony-planner-prototype';
const VALID_ROUTES: Route[] = ['finder', 'watchlist', 'pinned', 'compare', 'map', 'search-tuning', 'fc', 'colony', 'admin', 'colony-planner', 'colony-planner-prototype'];

export interface ParsedHash {
  route:            Route;
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
}

function parsePositiveId(value: string | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function parseHash(): ParsedHash {
  const raw   = window.location.hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean);

  if (parts.length === 0) {
    return { route: 'finder', selectedSystemId: null, plannerSystemId: null };
  }

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
  let plannerSystemId: number | null = null;
  if (parts[i] === 'system') {
    const id64 = parsePositiveId(parts[i + 1]);
    if (route === 'colony-planner') {
      plannerSystemId = id64;
    } else {
      selectedSystemId = id64;
    }
  }

  return { route, selectedSystemId, plannerSystemId };
}

function buildHash(route: Route, selectedSystemId: number | null): string {
  const modalRoute = route === 'colony-planner' ? 'finder' : route;
  const base = `#${modalRoute}`;
  return selectedSystemId != null ? `${base}/system/${selectedSystemId}` : base;
}

function buildPlannerHash(plannerSystemId: number | null): string {
  const base = '#colony-planner';
  return plannerSystemId != null ? `${base}/system/${plannerSystemId}` : base;
}

export interface HashRoute {
  route:            Route;
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
  /** Navigate to a tab. Preserves any open system modal. */
  navigate:    (r: Route) => void;
  /** Open the system detail modal on top of the current tab. */
  openSystem:  (id64: number) => void;
  /** Open the dedicated Colony Planner workspace for a system. */
  openColonyPlanner: (id64: number) => void;
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
    window.location.hash = r === 'colony-planner'
      ? buildPlannerHash(parsed.plannerSystemId)
      : buildHash(r, parsed.selectedSystemId);
  };

  const openSystem = (id64: number) => {
    window.location.hash = buildHash(parsed.route, id64);
  };

  const openColonyPlanner = (id64: number) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    window.location.hash = buildPlannerHash(systemId64);
  };

  const closeSystem = () => {
    window.location.hash = parsed.route === 'colony-planner'
      ? buildPlannerHash(parsed.plannerSystemId)
      : buildHash(parsed.route, null);
  };

  return {
    route:            parsed.route,
    selectedSystemId: parsed.selectedSystemId,
    plannerSystemId:  parsed.plannerSystemId,
    navigate, openSystem, openColonyPlanner, closeSystem,
  };
}
