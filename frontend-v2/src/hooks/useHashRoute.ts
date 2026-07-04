import { useEffect, useState } from 'react';

/**
 * Hash-based router with selected-system context that is distinct from the
 * System Detail modal.
 *
 * Supported selected-system forms:
 *   #finder/context/123456       → Finder with selected context and no modal
 *   #finder/system/123456        → Finder with selected context and System Detail open
 *   #system/123456               → Finder Inspect alias with System Detail open
 *   #colony-planner/system/123   → Planner with selected context and no modal
 *   #colony-planner/system/123/project/abc
 *                                  → Planner with selected context and a requested local project
 *
 * `selectedSystemId` remains the modal ID for backwards compatibility. New
 * code should use `contextSystemId` for the route-owned selected system.
 */
export type Route = 'finder' | 'my-work' | 'watchlist' | 'pinned' | 'compare' | 'map' | 'search-tuning' | 'fc' | 'colony' | 'admin' | 'operator' | 'colony-planner' | 'colony-planner-prototype';
const VALID_ROUTES: Route[] = ['finder', 'my-work', 'watchlist', 'pinned', 'compare', 'map', 'search-tuning', 'fc', 'colony', 'admin', 'operator', 'colony-planner', 'colony-planner-prototype'];

export type SelectedSystemRouteStatus = 'none' | 'pending' | 'invalid';

export interface ParsedHash {
  route: Route;
  /** System Detail modal only. */
  selectedSystemId: number | null;
  /** Route-owned selected system across Finder, Inspect, and Plan. */
  contextSystemId: number | null;
  selectedSystemRouteStatus: SelectedSystemRouteStatus;
  /** Retained for existing planner consumers; equals contextSystemId on Planner routes. */
  plannerSystemId: number | null;
  plannerProjectId: string | null;
}

interface ParsedSystemId {
  id64: number | null;
  status: SelectedSystemRouteStatus;
}

function parsePositiveId(value: string | undefined): ParsedSystemId {
  if (!value) return { id64: null, status: 'invalid' };
  const n = Number(value);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n <= 0) {
    return { id64: null, status: 'invalid' };
  }
  return { id64: n, status: 'pending' };
}

function decodeProjectId(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const decoded = decodeURIComponent(value).trim();
    return decoded || null;
  } catch {
    return null;
  }
}

function emptyParsed(route: Route = 'finder'): ParsedHash {
  return {
    route,
    selectedSystemId: null,
    contextSystemId: null,
    selectedSystemRouteStatus: 'none',
    plannerSystemId: null,
    plannerProjectId: null,
  };
}

function parseHash(): ParsedHash {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean);

  if (parts.length === 0) return emptyParsed();

  let route: Route = 'finder';
  let i = 0;
  if (parts[0] === 'optimizer') {
    route = 'search-tuning';
    i = 1;
  } else if ((VALID_ROUTES as string[]).includes(parts[0])) {
    route = parts[0] as Route;
    i = 1;
  }

  const parsed = emptyParsed(route);
  const segment = parts[i];

  if (segment === 'context') {
    const system = parsePositiveId(parts[i + 1]);
    if (route !== 'finder' || parts.length !== i + 2) {
      return { ...parsed, selectedSystemRouteStatus: 'invalid' };
    }
    return {
      ...parsed,
      contextSystemId: system.id64,
      selectedSystemRouteStatus: system.status,
    };
  }

  if (segment !== 'system') return parsed;

  const system = parsePositiveId(parts[i + 1]);
  if (system.status === 'invalid') {
    return { ...parsed, selectedSystemRouteStatus: 'invalid' };
  }

  if (route === 'colony-planner') {
    const hasProjectSegment = parts[i + 2] === 'project';
    const projectId = hasProjectSegment ? decodeProjectId(parts[i + 3]) : null;
    const malformedProjectRoute = hasProjectSegment && (!projectId || parts.length !== i + 4);
    const unexpectedPlannerTail = !hasProjectSegment && parts.length !== i + 2;
    if (malformedProjectRoute || unexpectedPlannerTail) {
      return { ...parsed, selectedSystemRouteStatus: 'invalid' };
    }
    return {
      ...parsed,
      contextSystemId: system.id64,
      selectedSystemRouteStatus: 'pending',
      plannerSystemId: system.id64,
      plannerProjectId: projectId,
    };
  }

  if (parts.length !== i + 2) {
    return { ...parsed, selectedSystemRouteStatus: 'invalid' };
  }

  return {
    ...parsed,
    selectedSystemId: system.id64,
    contextSystemId: system.id64,
    selectedSystemRouteStatus: 'pending',
  };
}

function buildPlainHash(route: Route): string {
  return `#${route}`;
}

function buildModalHash(route: Route, id64: number): string {
  const modalRoute = route === 'colony-planner' ? 'finder' : route;
  return `#${modalRoute}/system/${id64}`;
}

function buildFinderContextHash(id64: number): string {
  return `#finder/context/${id64}`;
}

function buildPlannerHash(plannerSystemId: number | null, plannerProjectId: string | null = null): string {
  const base = '#colony-planner';
  if (plannerSystemId == null) return base;
  if (plannerProjectId) return `${base}/system/${plannerSystemId}/project/${encodeURIComponent(plannerProjectId)}`;
  return `${base}/system/${plannerSystemId}`;
}

export interface HashRoute {
  route: Route;
  /** System Detail modal only. */
  selectedSystemId: number | null;
  contextSystemId: number | null;
  selectedSystemRouteStatus: SelectedSystemRouteStatus;
  plannerSystemId: number | null;
  plannerProjectId: string | null;
  /** Navigate to a workspace without inventing a modal. */
  navigate: (r: Route) => void;
  /** Open System Detail as an explicit Inspect action. */
  openSystem: (id64: number) => void;
  /** Open the dedicated Colony Planner workspace for a system. */
  openColonyPlanner: (id64: number, options?: { projectId?: string | null }) => void;
  /** Close an explicit Inspect modal while preserving Finder selected context. */
  closeSystem: () => void;
}

export function useHashRoute(): HashRoute {
  const [parsed, setParsed] = useState<ParsedHash>(parseHash);

  useEffect(() => {
    const onHash = () => setParsed(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const hasContext = parsed.contextSystemId != null && parsed.selectedSystemRouteStatus === 'pending';

  const navigate = (r: Route) => {
    if (r === 'colony-planner') {
      const projectId = parsed.route === 'colony-planner' ? parsed.plannerProjectId : null;
      window.location.hash = buildPlannerHash(hasContext ? parsed.contextSystemId : null, projectId);
      return;
    }

    if (r === 'finder') {
      if (parsed.selectedSystemId != null) {
        window.location.hash = buildModalHash('finder', parsed.selectedSystemId);
        return;
      }
      window.location.hash = hasContext ? buildFinderContextHash(parsed.contextSystemId as number) : buildPlainHash('finder');
      return;
    }

    if (parsed.selectedSystemId != null) {
      window.location.hash = buildModalHash(r, parsed.selectedSystemId);
      return;
    }

    window.location.hash = buildPlainHash(r);
  };

  const openSystem = (id64: number) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || !Number.isInteger(systemId64) || systemId64 <= 0) return;
    window.location.hash = buildModalHash(parsed.route, systemId64);
  };

  const openColonyPlanner = (id64: number, options?: { projectId?: string | null }) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || !Number.isInteger(systemId64) || systemId64 <= 0) return;
    window.location.hash = buildPlannerHash(systemId64, options?.projectId ?? null);
  };

  const closeSystem = () => {
    if (parsed.selectedSystemId == null) return;
    if (parsed.route === 'finder' && hasContext) {
      window.location.hash = buildFinderContextHash(parsed.contextSystemId as number);
      return;
    }
    window.location.hash = buildPlainHash(parsed.route);
  };

  return {
    route: parsed.route,
    selectedSystemId: parsed.selectedSystemId,
    contextSystemId: parsed.contextSystemId,
    selectedSystemRouteStatus: parsed.selectedSystemRouteStatus,
    plannerSystemId: parsed.plannerSystemId,
    plannerProjectId: parsed.plannerProjectId,
    navigate,
    openSystem,
    openColonyPlanner,
    closeSystem,
  };
}
