import { useEffect, useState } from 'react';
import type { SimulationWorkspaceMode } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';

/**
 * Hash-based router with optional `system/{id64}` sub-routes.
 *
 * Supported hash formats (in priority order):
 *   #finder                       → route='finder',    selectedSystemId=null
 *   #pinned                       → route='my-work',   routeAlias='pinned',    selectedSystemId=null
 *   #pinned/system/12345678       → route='my-work',   routeAlias='pinned',    selectedSystemId=12345678
 *   #search-tuning                â†’ route='search-tuning', selectedSystemId=null
 *   #system/12345678              → route='finder',    selectedSystemId=12345678   (deep-link from external)
 *   #my-work                      → route='my-work', selectedSystemId=null
 *   #watchlist                    → route='my-work', routeAlias='watchlist', selectedSystemId=null
 *   #colony                       → route='my-work', routeAlias='colony', selectedSystemId=null
 *   #colony-planner/system/123    → route='colony-planner', plannerSystemId=123
 *   #colony-planner/system/123/project/abc → route='colony-planner', plannerSystemId=123, plannerProjectId='abc'
 *   #colony-planner/system/123/detail/456  → route='colony-planner', plannerSystemId=123, selectedSystemId=456
 *   #colony-planner/system/123/project/abc/detail/456 → route='colony-planner', plannerSystemId=123, plannerProjectId='abc', selectedSystemId=456
 *   #operator                     → route='operator', selectedSystemId=null
 *   #colony-planner               → route='colony-planner', plannerSystemId=null
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
export type Route = 'finder' | 'my-work' | 'compare' | 'map' | 'search-tuning' | 'fc' | 'admin' | 'operator' | 'colony-planner';
const VALID_ROUTES: Route[] = ['finder', 'my-work', 'compare', 'map', 'search-tuning', 'fc', 'admin', 'operator', 'colony-planner'];

export interface ParsedHash {
  route:            Route;
  routeAlias:       'watchlist' | 'pinned' | 'colony' | null;
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
  plannerProjectId: string | null;
  plannerMode: SimulationWorkspaceMode | null;
}

const VALID_PLANNER_MODES: SimulationWorkspaceMode[] = [
  'build-plan',
  'suggested-builds',
  'preview',
  'sequence',
  'map',
  'evidence',
  'validation',
  'export',
];

function parsePlannerMode(value: string | undefined): SimulationWorkspaceMode | null {
  if (!value) return null;
  return VALID_PLANNER_MODES.includes(value as SimulationWorkspaceMode)
    ? value as SimulationWorkspaceMode
    : null;
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
    return { route: 'finder', routeAlias: null, selectedSystemId: null, plannerSystemId: null, plannerProjectId: null, plannerMode: null };
  }

  let route: Route = 'finder';
  let routeAlias: ParsedHash['routeAlias'] = null;
  let i = 0;
  if (parts[0] === 'watchlist' || parts[0] === 'pinned' || parts[0] === 'colony') {
    route = 'my-work';
    routeAlias = parts[0] as 'watchlist' | 'pinned' | 'colony';
    i = 1;
  } else if ((VALID_ROUTES as string[]).includes(parts[0])) {
    route = parts[0] as Route;
    i = 1;
  }

  let selectedSystemId: number | null = null;
  let plannerSystemId: number | null = null;
  let plannerProjectId: string | null = null;
  let plannerMode: SimulationWorkspaceMode | null = null;
  if (parts[i] === 'system') {
    const id64 = parsePositiveId(parts[i + 1]);
    if (route === 'colony-planner') {
      plannerSystemId = id64;
      let cursor = i + 2;
      if (parts[cursor] === 'project' && parts[cursor + 1]) {
        plannerProjectId = decodeURIComponent(parts[cursor + 1]);
        cursor += 2;
      }
      if (parts[cursor] === 'mode') {
        plannerMode = parsePlannerMode(parts[cursor + 1]);
        if (plannerMode) {
          cursor += 2;
        }
      }
      if (parts[cursor] === 'detail') {
        selectedSystemId = parsePositiveId(parts[cursor + 1]);
      }
    } else {
      selectedSystemId = id64;
    }
  }

  return { route, routeAlias, selectedSystemId, plannerSystemId, plannerProjectId, plannerMode };
}

function buildHash(route: Route, selectedSystemId: number | null): string {
  const modalRoute = route === 'colony-planner' ? 'finder' : route;
  const base = `#${modalRoute}`;
  return selectedSystemId != null ? `${base}/system/${selectedSystemId}` : base;
}

function buildPlannerHash(
  plannerSystemId: number | null,
  plannerProjectId: string | null = null,
  plannerMode: SimulationWorkspaceMode | null = null,
  selectedSystemId: number | null = null,
): string {
  const base = '#colony-planner';
  if (plannerSystemId == null) return base;
  const projectSegment = plannerProjectId ? `/project/${encodeURIComponent(plannerProjectId)}` : '';
  const modeSegment = plannerMode ? `/mode/${plannerMode}` : '';
  const detailSegment = selectedSystemId != null ? `/detail/${selectedSystemId}` : '';
  return `${base}/system/${plannerSystemId}${projectSegment}${modeSegment}${detailSegment}`;
}

export interface HashRoute {
  route:            Route;
  routeAlias:       ParsedHash['routeAlias'];
  selectedSystemId: number | null;
  plannerSystemId:  number | null;
  plannerProjectId: string | null;
  plannerMode: SimulationWorkspaceMode | null;
  /** Navigate to a tab. Preserves any open system modal. */
  navigate:    (r: Route) => void;
  /** Open the system detail modal on top of the current tab or an explicit host tab. */
  openSystem:  (id64: number, options?: { hostRoute?: Route }) => void;
  /** Open the dedicated Colony Planner workspace for a system. */
  openColonyPlanner: (id64: number, options?: { projectId?: string | null; mode?: SimulationWorkspaceMode | null }) => void;
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
      window.location.hash = buildPlannerHash(parsed.plannerSystemId, parsed.plannerProjectId, parsed.plannerMode, null);
      return;
    }
    window.location.hash = buildHash(r, parsed.selectedSystemId);
  };

  const openSystem = (id64: number, options?: { hostRoute?: Route }) => {
    const hostRoute = options?.hostRoute ?? parsed.route;
    if (hostRoute === 'colony-planner' && parsed.plannerSystemId != null) {
      window.location.hash = buildPlannerHash(parsed.plannerSystemId, parsed.plannerProjectId, parsed.plannerMode, id64);
      return;
    }
    window.location.hash = buildHash(hostRoute, id64);
  };

  const openColonyPlanner = (id64: number, options?: { projectId?: string | null; mode?: SimulationWorkspaceMode | null }) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    window.location.hash = buildPlannerHash(systemId64, options?.projectId ?? null, options?.mode ?? null, null);
  };

  const closeSystem = () => {
    window.location.hash = parsed.route === 'colony-planner'
      ? buildPlannerHash(parsed.plannerSystemId, parsed.plannerProjectId, parsed.plannerMode, null)
      : buildHash(parsed.route, null);
  };

  return {
    route:            parsed.route,
    routeAlias: parsed.routeAlias,
    selectedSystemId: parsed.selectedSystemId,
    plannerSystemId:  parsed.plannerSystemId,
    plannerProjectId: parsed.plannerProjectId,
    plannerMode: parsed.plannerMode,
    navigate, openSystem, openColonyPlanner, closeSystem,
  };
}
