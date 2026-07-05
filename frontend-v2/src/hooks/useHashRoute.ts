import { useEffect, useState } from 'react';

/**
 * Hash-based router with optional `system/{id64}` sub-routes.
 *
 * Supported hash formats (in priority order):
 *   #finder                       → route='finder',    contextSystemId=null, selectedSystemId=null
 *   #finder/context/12345678      → route='finder',    contextSystemId=12345678, selectedSystemId=null
 *   #pinned                       → route='pinned',    selectedSystemId=null
 *   #pinned/system/12345678       → route='pinned',    selectedSystemId=12345678
 *   #search-tuning                → route='search-tuning', selectedSystemId=null
 *   #optimizer                    → route='search-tuning', selectedSystemId=null (legacy alias)
 *   #finder/system/12345678       → route='finder',    contextSystemId=12345678, selectedSystemId=12345678
 *   #system/12345678              → route='finder',    contextSystemId=12345678, selectedSystemId=12345678   (deep-link from external)
 *   #my-work                      → route='my-work', selectedSystemId=null
 *   #colony-planner/system/123    → route='colony-planner', plannerSystemId=123
 *   #colony-planner/system/123/project/abc → route='colony-planner', plannerSystemId=123, plannerProjectId='abc'
 *   #operator                     → route='operator', selectedSystemId=null
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
export type Route = 'finder' | 'my-work' | 'watchlist' | 'pinned' | 'compare' | 'map' | 'search-tuning' | 'fc' | 'colony' | 'admin' | 'operator' | 'colony-planner' | 'colony-planner-prototype';
const VALID_ROUTES: Route[] = ['finder', 'my-work', 'watchlist', 'pinned', 'compare', 'map', 'search-tuning', 'fc', 'colony', 'admin', 'operator', 'colony-planner', 'colony-planner-prototype'];

export interface ParsedHash {
  route:            Route;
  contextSystemId:  number | null;
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
  plannerProjectId: string | null;
  invalidSelectedContext: boolean;
  invalidPlannerSystem: boolean;
  invalidPlannerProject: boolean;
}

function parsePositiveId(value: string | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function parsedBase(route: Route): ParsedHash {
  return {
    route,
    contextSystemId: null,
    selectedSystemId: null,
    plannerSystemId: null,
    plannerProjectId: null,
    invalidSelectedContext: false,
    invalidPlannerSystem: false,
    invalidPlannerProject: false,
  };
}

function parseHash(): ParsedHash {
  const raw   = window.location.hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean);

  if (parts.length === 0) return parsedBase('finder');

  let route: Route = 'finder';
  let i = 0;
  const rootIsSystemAlias = parts[0] === 'system';
  if (parts[0] === 'optimizer') {
    route = 'search-tuning';
    i = 1;
  } else if (rootIsSystemAlias) {
    route = 'finder';
    i = 0;
  } else if ((VALID_ROUTES as string[]).includes(parts[0])) {
    route = parts[0] as Route;
    i = 1;
  }

  const parsed = parsedBase(route);

  if (rootIsSystemAlias) {
    const id64 = parsePositiveId(parts[1]);
    parsed.contextSystemId = id64;
    parsed.selectedSystemId = id64;
    parsed.invalidSelectedContext = parts.length !== 2 || id64 == null;
    if (parsed.invalidSelectedContext && id64 == null) {
      parsed.contextSystemId = null;
      parsed.selectedSystemId = null;
    }
    return parsed;
  }

  if (route === 'finder') {
    if (i === 0 && parts[0] !== 'finder') {
      return parsed;
    }

    const remainder = parts.slice(i);
    if (remainder.length === 0) return parsed;

    if (remainder[0] === 'context') {
      const id64 = parsePositiveId(remainder[1]);
      parsed.contextSystemId = id64;
      parsed.invalidSelectedContext = remainder.length !== 2 || id64 == null;
      if (parsed.invalidSelectedContext && id64 == null) {
        parsed.contextSystemId = null;
      }
      return parsed;
    }

    if (remainder[0] === 'system') {
      const id64 = parsePositiveId(remainder[1]);
      parsed.contextSystemId = id64;
      parsed.selectedSystemId = id64;
      parsed.invalidSelectedContext = remainder.length !== 2 || id64 == null;
      if (parsed.invalidSelectedContext && id64 == null) {
        parsed.contextSystemId = null;
        parsed.selectedSystemId = null;
      }
      return parsed;
    }

    parsed.invalidSelectedContext = remainder.length > 0;
    return parsed;
  }

  if (route === 'colony-planner') {
    const remainder = parts.slice(i);
    if (remainder.length === 0) return parsed;

    if (remainder[0] !== 'system') {
      parsed.invalidPlannerSystem = true;
      return parsed;
    }

    const id64 = parsePositiveId(remainder[1]);
    parsed.plannerSystemId = id64;

    if (remainder.length === 2 && id64 != null) {
      return parsed;
    }

    if (id64 == null) {
      parsed.plannerSystemId = null;
      parsed.invalidPlannerSystem = true;
      return parsed;
    }

    if (remainder[2] === 'project') {
      if (remainder.length < 4) {
        parsed.invalidPlannerProject = true;
        return parsed;
      }
    } else if (remainder.length < 4 || remainder[2] !== 'project') {
      parsed.invalidPlannerSystem = true;
      return parsed;
    }

    const projectId = remainder[3]?.trim() ?? '';
    if (projectId.length === 0 || remainder.length !== 4) {
      parsed.invalidPlannerProject = true;
      return parsed;
    }

    parsed.plannerProjectId = projectId;
    return parsed;
  }

  if (parts[i] === 'system' && parts.length === i + 2) {
    parsed.selectedSystemId = parsePositiveId(parts[i + 1]);
  }

  return parsed;
}

function buildHash(route: Route, selectedSystemId: number | null): string {
  const modalRoute = route === 'colony-planner' ? 'finder' : route;
  const base = `#${modalRoute}`;
  return selectedSystemId != null ? `${base}/system/${selectedSystemId}` : base;
}

export function buildFinderContextHash(contextSystemId: number | null): string {
  return contextSystemId != null ? `#finder/context/${contextSystemId}` : '#finder';
}

function buildPlannerHash(plannerSystemId: number | null, plannerProjectId: string | null = null): string {
  const base = '#colony-planner';
  if (plannerSystemId == null) return base;
  if (plannerProjectId) return `${base}/system/${plannerSystemId}/project/${encodeURIComponent(plannerProjectId)}`;
  return `${base}/system/${plannerSystemId}`;
}

export interface HashRoute {
  route:            Route;
  contextSystemId:  number | null;
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
  plannerProjectId: string | null;
  invalidSelectedContext: boolean;
  invalidPlannerSystem: boolean;
  invalidPlannerProject: boolean;
  /** Navigate to a tab. Preserves any open system modal. */
  navigate:    (r: Route) => void;
  /** Open the system detail modal on top of the current tab. */
  openSystem:  (id64: number) => void;
  /** Open the dedicated Colony Planner workspace for a system. */
  openColonyPlanner: (id64: number, options?: { projectId?: string | null }) => void;
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
    if (r === 'colony-planner') {
      const plannerSystemId = parsed.route === 'colony-planner'
        ? parsed.plannerSystemId
        : (parsed.invalidSelectedContext ? null : (parsed.contextSystemId ?? parsed.selectedSystemId ?? parsed.plannerSystemId));
      const plannerProjectId = parsed.route === 'colony-planner' && !parsed.invalidPlannerProject
        ? parsed.plannerProjectId
        : null;
      window.location.hash = buildPlannerHash(plannerSystemId, plannerProjectId);
      return;
    }
    if (r === 'finder') {
      window.location.hash = buildFinderContextHash(
        parsed.contextSystemId ?? parsed.plannerSystemId ?? parsed.selectedSystemId,
      );
      return;
    }
    window.location.hash = buildHash(r, parsed.selectedSystemId);
  };

  const openSystem = (id64: number) => {
    if (parsed.route === 'finder' || parsed.route === 'colony-planner') {
      window.location.hash = buildHash('finder', id64);
      return;
    }
    window.location.hash = buildHash(parsed.route, id64);
  };

  const openColonyPlanner = (id64: number, options?: { projectId?: string | null }) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    window.location.hash = buildPlannerHash(systemId64, options?.projectId ?? null);
  };

  const closeSystem = () => {
    if (parsed.route === 'finder') {
      window.location.hash = buildFinderContextHash(parsed.contextSystemId ?? parsed.selectedSystemId);
      return;
    }
    window.location.hash = parsed.route === 'colony-planner'
      ? buildPlannerHash(parsed.plannerSystemId, parsed.plannerProjectId)
      : buildHash(parsed.route, null);
  };

  return {
    route:            parsed.route,
    contextSystemId:  parsed.contextSystemId,
    selectedSystemId: parsed.selectedSystemId,
    plannerSystemId:  parsed.plannerSystemId,
    plannerProjectId: parsed.plannerProjectId,
    invalidSelectedContext: parsed.invalidSelectedContext,
    invalidPlannerSystem: parsed.invalidPlannerSystem,
    invalidPlannerProject: parsed.invalidPlannerProject,
    navigate, openSystem, openColonyPlanner, closeSystem,
  };
}
