import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { api } from '@/lib/api';
import { NavBar } from '@/components/NavBar';
import type { SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { useSearch } from '@/features/search/useSearch';
import { useWatchlist } from '@/features/watchlist/useWatchlist';
import { usePinned } from '@/features/pinned/usePinned';
import { toPinnedEntry } from '@/features/pinned/pinnedEntry';
import { useCompare } from '@/features/compare/useCompare';
import { useSearchTuning } from '@/features/search-tuning/useSearchTuning';
import { useFcPlanner } from '@/features/fc-planner/useFcPlanner';
import { useAdmin } from '@/features/admin/useAdmin';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import {
  defaultDraftProjectName,
  type ColonyProjectObjective,
  type ColonyProjectStartApproach,
} from '@/features/colony-planner/plannerDraftContext';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import { EliteNewsBar } from '@/features/news/EliteNewsBar';
import { writeSelectedOperatorSourceRun } from '@/features/operator/operatorSelection';
import { useHashRoute, type HashRoute } from '@/hooks/useHashRoute';
import { setCoalsackBackgroundVariables } from '@/app/coalsackBackground';
import { FinderView } from '@/app/FinderView';
import { SavedSystemNotice } from '@/app/SavedSystemNotice';
import { toCompareSnapshot } from '@/app/compareSnapshot';
import {
  type SavedSystemActionState,
  type SavedSystemNoticeState,
  savedSystemFailureDetail,
} from '@/app/savedSystems';
import { systemStatusLabel } from '@/lib/format';
import type { SystemDetail } from '@/types/api';
import './index.css';

const LazyCompareTab = lazy(async () => ({ default: (await import('@/features/compare/CompareTab')).CompareTab }));
const LazyAdvancedSearchTuningTab = lazy(async () => ({ default: (await import('@/features/search-tuning/AdvancedSearchTuningTab')).AdvancedSearchTuningTab }));
const LazyFcPlannerTab = lazy(async () => ({ default: (await import('@/features/fc-planner/FcPlannerTab')).FcPlannerTab }));
const LazyAdminTab = lazy(async () => ({ default: (await import('@/features/admin/AdminTab')).AdminTab }));
const LazyOperatorCockpitTab = lazy(async () => ({ default: (await import('@/features/operator/OperatorCockpitTab')).OperatorCockpitTab }));
const LazyMapTab = lazy(async () => ({ default: (await import('@/features/map/MapTab')).MapTab }));
const LazySystemDetailModal = lazy(async () => ({ default: (await import('@/features/system-detail/SystemDetailModal')).SystemDetailModal }));
const LazyColonyPlannerWorkspace = lazy(async () => ({ default: (await import('@/features/colony-planner/ColonyPlannerWorkspace')).ColonyPlannerWorkspace }));
const LazyMyWorkWorkspace = lazy(async () => ({ default: (await import('@/features/my-work/MyWorkWorkspace')).MyWorkWorkspace }));
const LazyReactQueryDevtools = lazy(async () => ({ default: (await import('@tanstack/react-query-devtools')).ReactQueryDevtools }));
const SHELL_SELECTED_SYSTEM_STORAGE_KEY = 'ed-finder:selected-system-context';

/**
 * Root app shell: NavBar + tab content + system-detail modal overlay.
 *
 * State (search filters, watchlist, pins, compare) lives at this level so
 * tabs can share data and the modal — which can open from any tab — can
 * call into the same hooks for "Save to Watchlist" / "Pin" / "Add to
 * Compare" without re-implementing them.
 *
 * Audit fix (2026-05-08, AUDIT_REPORT.md §3 / Phase 7): the whole tree is
 * wrapped in QueryClientProvider so any descendant `useQuery`/`useMutation`
 * shares one cache. Devtools mount in dev only.
 */
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
      {import.meta.env.DEV && (
        <Suspense fallback={null}>
          <LazyReactQueryDevtools initialIsOpen={false} />
        </Suspense>
      )}
    </QueryClientProvider>
  );
}

function AppInner() {
  const hashRoute = useHashRoute();

  useEffect(() => setCoalsackBackgroundVariables(), []);

  return <LiveAppInner hashRoute={hashRoute} />;
}

function LiveAppInner({ hashRoute }: { hashRoute: HashRoute }) {
  const {
    route,
    routeAlias,
    selectedSystemId,
    plannerSystemId,
    plannerProjectId,
    plannerMode,
    navigate,
    openSystem,
    openColonyPlanner,
    closeSystem,
  } = hashRoute;
  const search    = useSearch();
  const watchlist = useWatchlist();
  const pinned    = usePinned();
  const compare   = useCompare();
  const searchTuning = useSearchTuning();
  const fc        = useFcPlanner();
  const admin     = useAdmin();
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const [health, setHealth] = useState<string>('Checking API');
  const [detailFocus, setDetailFocus] = useState<'colony-planner' | null>(null);
  const [savedSystemActionState, setSavedSystemActionState] = useState<Record<number, SavedSystemActionState>>({});
  const [savedSystemNotice, setSavedSystemNotice] = useState<SavedSystemNoticeState | null>(null);
  const [shellContextSystemId, setShellContextSystemId] = useState<number | null>(() => readPersistedShellContextSystemId());
  const routeSystemId = plannerSystemId ?? selectedSystemId;
  const shellSystem = useSystemDetail(shellContextSystemId);

  useEffect(() => {
    if (routeSystemId != null) {
      setShellContextSystemId(routeSystemId);
    }
  }, [routeSystemId]);

  useEffect(() => {
    persistShellContextSystemId(shellContextSystemId);
  }, [shellContextSystemId]);

  const previousRouteRef = useRef(route);
  useEffect(() => {
    if (previousRouteRef.current !== 'finder' && route === 'finder') {
      setShellContextSystemId(null);
    }
    previousRouteRef.current = route;
  }, [route]);

  const shellSelectedSystem = shellContextSystemId != null
    ? buildShellSelectedSystem(shellContextSystemId, shellSystem.data, shellSystem.loading)
    : null;

  const openSystemDetail = (id64: number, options?: { focus?: 'colony-planner'; hostRoute?: HashRoute['route'] }) => {
    setDetailFocus(options?.focus ?? null);
    setShellContextSystemId(id64);
    openSystem(id64, { hostRoute: options?.hostRoute });
  };

  const openColonyPlannerWorkspace = (id64: number) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    setDetailFocus(null);
    setShellContextSystemId(systemId64);
    openColonyPlanner(systemId64);
  };

  const openShellContextInPlan = () => {
    if (shellContextSystemId == null) return;
    setDetailFocus(null);
    openColonyPlanner(shellContextSystemId, {
      mode: route === 'colony-planner' ? plannerMode : 'build-plan',
    });
  };

  const closeSystemDetail = () => {
    setDetailFocus(null);
    setShellContextSystemId(null);
    closeSystem();
  };

  const openOperatorDashboard = (sourceRunKey?: string) => {
    writeSelectedOperatorSourceRun(sourceRunKey ?? null);
    navigate('operator');
  };

  const toggleSavedSystem = useCallback(async (
    id64: number,
    hint: {
      name?: string | null;
      x?: number | null;
      y?: number | null;
      z?: number | null;
      population?: number | null;
      is_colonised?: boolean;
      developmentScore?: number | null;
      economy_suggestion?: string | null;
      primary_archetype?: string | null;
      secondary_archetype?: string | null;
      buildability_score?: number | null;
      purity_score?: number | null;
    },
  ) => {
    if (savedSystemActionState[id64] && savedSystemActionState[id64] !== 'idle') return;
    const saved = watchlist.has(id64);
    const actionState: SavedSystemActionState = saved ? 'removing' : 'saving';
    const name = hint.name?.trim() || `System ${id64}`;

    setSavedSystemActionState((current) => ({ ...current, [id64]: actionState }));
    try {
      if (saved) {
        await watchlist.remove(id64);
        setSavedSystemNotice({
          tone: 'success',
          message: 'Removed from saved',
          detail: `${name} was removed from My Work saved systems.`,
        });
        return;
      }
      await watchlist.add(id64, {
        name,
        x: hint.x ?? null,
        y: hint.y ?? null,
        z: hint.z ?? null,
        population: hint.population ?? null,
        is_colonised: hint.is_colonised ?? false,
        economy_suggestion: hint.economy_suggestion ?? null,
        archetype_score: hint.developmentScore ?? null,
        primary_archetype: hint.primary_archetype ?? null,
        secondary_archetype: hint.secondary_archetype ?? null,
        buildability_score: hint.buildability_score ?? null,
        purity_score: hint.purity_score ?? null,
      });
      setSavedSystemNotice({
        tone: 'success',
        message: 'Saved to My Work',
        detail: `${name} is available in saved systems.`,
        actionLabel: 'Open My Work',
      });
    } catch (error) {
      setSavedSystemNotice({
        tone: 'error',
        message: saved ? 'Could not remove saved system' : 'Could not save system',
        detail: savedSystemFailureDetail(error, saved),
      });
    } finally {
      setSavedSystemActionState((current) => {
        const next = { ...current };
        delete next[id64];
        return next;
      });
    }
  }, [savedSystemActionState, watchlist]);

  const startPlanFromSystemDetail = useCallback((
    system: import('@/types/api').SystemDetail,
    planStart: {
      objective: ColonyProjectObjective;
      startApproach: ColonyProjectStartApproach;
    },
  ) => {
    const targetArchetype = system.primary_archetype
      ?? archetypeFromEconomy(system.primary_economy)
      ?? 'refinery_industrial';
    const saved = saveProject(null, {
      system_id64: system.id64,
      system_name: system.name || 'Unknown system',
      project_name: defaultDraftProjectName(system.name || 'Unknown system', planStart.objective),
      build_plan_placements: [],
      target_archetype: targetArchetype,
      notes: '',
      status: 'draft',
      objective: planStart.objective,
      start_approach: planStart.startApproach,
      created_from: 'system_detail',
    });
    setDetailFocus(null);
    setShellContextSystemId(system.id64);
    openColonyPlanner(system.id64, { projectId: saved.id });
  }, [openColonyPlanner, saveProject]);

  // First-paint: health only. Finder should open calm and empty until the
  // player explicitly runs a search.
  useEffect(() => {
    api.health()
      .then(() => setHealth('Online'))
      .catch(() => setHealth('API connection issue'));
  }, []);

  const plannerWorkspaceRoute = route === 'colony-planner';

  return (
    <>
      <a
        href="#app-content"
        className="sr-only fixed left-4 top-4 z-[100] rounded-chunk-sm border border-orange/55 bg-bg2/95 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-orange shadow-brand-glow focus:not-sr-only focus:outline-none focus:ring-2 focus:ring-orange/80"
      >
        Skip to main content
      </a>
      <main
        id="app-content"
        className={[
          'min-h-screen px-4 py-6 sm:px-6 sm:py-10',
          plannerWorkspaceRoute ? 'pb-10' : 'pb-28',
          plannerWorkspaceRoute ? 'max-w-none' : 'mx-auto max-w-[1840px]',
        ].join(' ')}
      >
      <NavBar
        current={route}
        onNavigate={navigate}
        watchlistCount={watchlist.entries.length}
        pinnedCount={pinned.entries.length}
        compareCount={compare.entries.length}
        fcCount={fc.waypoints.length}
        health={health}
        fullWidth={plannerWorkspaceRoute}
        selectedSystem={shellSelectedSystem}
        onOpenSelectedSystemInPlan={shellSelectedSystem && route !== 'colony-planner' ? openShellContextInPlan : undefined}
        onDismissSelectedSystem={closeSystemDetail}
      />

      <SavedSystemNotice
        notice={savedSystemNotice}
        onDismiss={() => setSavedSystemNotice(null)}
        onOpenMyWork={() => {
          setSavedSystemNotice(null);
          navigate('my-work');
        }}
      />

      {route === 'finder' && (
        <FinderView
          search={search}
          watchlist={watchlist}
          pinned={pinned}
          compare={compare}
          savedActionStates={savedSystemActionState}
          onToggleSavedForLater={toggleSavedSystem}
          onShowOnMap={(id64) => openSystemDetail(id64, { hostRoute: 'map' })}
          onOpenDetail={openSystemDetail}
        />
      )}

      <Suspense fallback={<WorkspaceFallback label="Loading workspace" fullWidth={plannerWorkspaceRoute} />}>
        {route === 'my-work' && (
          <LazyMyWorkWorkspace
            key={route}
            initialSection="saved-systems"
            routeSource={routeAlias === 'watchlist' || routeAlias === 'pinned' || routeAlias === 'colony' ? routeAlias : 'my-work'}
            watchlist={watchlist}
            pinned={pinned}
            onOpenDetail={openSystemDetail}
            onOpenPlanner={openColonyPlanner}
          />
        )}

        {route === 'compare' && (
          <LazyCompareTab
            compare={compare}
            onOpenDetail={openSystemDetail}
            selectedSystem={shellSelectedSystem}
          />
        )}

        {route === 'search-tuning' && (
          <LazyAdvancedSearchTuningTab
            searchTuning={searchTuning}
            search={search}
            onOpenDetail={openSystemDetail}
            onOpenColonyPlanner={openColonyPlannerWorkspace}
          />
        )}

        {route === 'colony-planner' && (
          <LazyColonyPlannerWorkspace
            id64={plannerSystemId}
            projectId={plannerProjectId}
            onBackToFinder={() => navigate('finder')}
            onOpenSystemDetail={(id64) => openSystemDetail(id64, { hostRoute: 'colony-planner' })}
            onOpenMyWork={() => navigate('my-work')}
            initialCockpitMode={plannerMode ?? 'build-plan'}
            onCockpitModeChange={(mode) => {
              if (plannerSystemId == null) return;
              openColonyPlanner(plannerSystemId, {
                projectId: plannerProjectId,
                mode,
              });
            }}
            onPlanDeleted={(projectName) => {
              setSavedSystemNotice({
                tone: 'success',
                message: 'Draft deleted',
                detail: `${projectName} was removed from this browser.`,
              });
            }}
          />
        )}

        {route === 'fc' && (
          <LazyFcPlannerTab
            fc={fc}
            onOpenDetail={openSystemDetail}
            selectedSystem={shellSelectedSystem}
          />
        )}

        {route === 'admin' && (
          <LazyAdminTab admin={admin} onOpenOperator={openOperatorDashboard} />
        )}

        {route === 'operator' && (
          <LazyOperatorCockpitTab admin={admin} />
        )}

        {route === 'map' && (
          <LazyMapTab
            systems={search.results}
            reference={{
              name: search.filters.refName,
              x:    search.filters.refCoords.x,
              z:    search.filters.refCoords.z,
            }}
            initialSelectedSystemId={selectedSystemId}
            onReturnToFinder={() => navigate('finder')}
            onOpenSelectedSystem={(id64) => openSystemDetail(id64, { hostRoute: 'map' })}
          />
        )}
      </Suspense>

      <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
        Vite {import.meta.env.MODE} build · root-served live app
      </footer>

      {selectedSystemId !== null && (
        <Suspense fallback={null}>
          <LazySystemDetailModal
            id64={selectedSystemId}
            focusIntent={detailFocus}
            onClose={closeSystemDetail}
            savedForLater={shellSystem.data ? watchlist.has(shellSystem.data.id64) : false}
            saveForLaterState={shellSystem.data ? savedSystemActionState[shellSystem.data.id64] ?? 'idle' : 'idle'}
            onToggleSaveForLater={(system) => {
              const developmentScore = system.archetype?.overall_development_potential
                ?? system.system.overall_development_potential
                ?? system.system.score
                ?? null;
              void toggleSavedSystem(system.system.id64, {
                name: system.system.name,
                x: system.system.x,
                y: system.system.y,
                z: system.system.z,
                population: system.system.population ?? null,
                is_colonised: !!system.system.is_colonised,
                developmentScore,
                economy_suggestion: system.system.economy_suggestion ?? null,
                primary_archetype: system.archetype?.primary_archetype ?? system.system.primary_archetype ?? null,
                secondary_archetype: system.archetype?.secondary_archetype ?? system.system.secondary_archetype ?? null,
                buildability_score: system.archetype?.buildability_score ?? system.system.buildability_score ?? null,
                purity_score: system.archetype?.purity_score ?? system.system.purity_score ?? null,
              });
            }}
            onStartPlan={startPlanFromSystemDetail}
            renderActions={({ system: sys, archetype }) => (
              <>
                <button
                  type="button"
                  disabled={!sys}
                  onClick={() => sys && pinned.toggle(toPinnedEntry({
                    id64: sys.id64,
                    name: sys.name,
                    coords: { x: sys.x ?? null, y: sys.y ?? null, z: sys.z ?? null },
                    population: sys.population ?? null,
                    is_colonised: !!sys.is_colonised,
                    economy_suggestion: sys.economy_suggestion ?? sys.primary_economy ?? null,
                    archetype_score: archetype?.overall_development_potential ?? sys.overall_development_potential ?? sys.score ?? null,
                    primary_archetype: archetype?.primary_archetype ?? sys.primary_archetype ?? null,
                    secondary_archetype: archetype?.secondary_archetype ?? sys.secondary_archetype ?? null,
                    buildability_score: archetype?.buildability_score ?? sys.buildability_score ?? null,
                    purity_score: archetype?.purity_score ?? sys.purity_score ?? null,
                  }))}
                  data-testid="modal-pin-toggle"
                  className={[
                    'px-2 py-1 rounded font-mono text-[11px] border transition-colors',
                    sys && pinned.has(sys.id64)
                      ? 'bg-orange/20 border-orange text-orange'
                      : 'bg-bg4 border-border text-text-dim hover:text-orange hover:border-orange-dk',
                    !sys && 'opacity-40 cursor-not-allowed',
                  ].filter(Boolean).join(' ')}
                >
                  {sys && pinned.has(sys.id64) ? '📌 Pinned — unpin' : '📍 Pin'}
                </button>

                <button
                  type="button"
                  disabled={!sys}
                  onClick={() => sys && compare.toggle(toCompareSnapshot(sys, archetype))}
                  data-testid="modal-compare-toggle"
                  className={[
                    'px-2 py-1 rounded font-mono text-[11px] border transition-colors',
                    sys && compare.has(sys.id64)
                      ? 'bg-orange/20 border-orange text-orange'
                      : 'bg-bg4 border-border text-text-dim hover:text-orange hover:border-orange-dk',
                    !sys && 'opacity-40 cursor-not-allowed',
                  ].filter(Boolean).join(' ')}
                >
                  {sys && compare.has(sys.id64) ? '⚖️ In comparison — remove' : '⚖️ Add to Compare'}
                </button>
              </>
            )}
          />
        </Suspense>
      )}

      {!plannerWorkspaceRoute && <EliteNewsBar />}
      </main>
    </>
  );
}

function WorkspaceFallback({ label, fullWidth = false }: { label: string; fullWidth?: boolean }) {
  return (
    <section
      className={[
        'panel-thin flex min-h-[240px] items-center justify-center px-4 py-12 text-center font-mono text-xs text-silver-dk',
        fullWidth ? 'w-full' : '',
      ].join(' ')}
      aria-label={label}
    >
      {label}...
    </section>
  );
}

function readPersistedShellContextSystemId(): number | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function persistShellContextSystemId(id64: number | null) {
  if (typeof window === 'undefined') return;
  if (id64 == null) {
    window.localStorage.removeItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SHELL_SELECTED_SYSTEM_STORAGE_KEY, String(id64));
}

function buildShellSelectedSystem(
  id64: number,
  system: SystemDetail | null,
  loading: boolean,
): {
  id64: number;
  name: string | null;
  loading: boolean;
  evidenceLabel: string;
  evidenceTone: SemanticStatusTone;
  evidenceSummary: string;
} {
  if (loading) {
    return {
      id64,
      name: null,
      loading: true,
      evidenceLabel: 'Refreshing context',
      evidenceTone: 'loading',
      evidenceSummary: 'Refreshing the selected-system evidence posture for the current player flow.',
    };
  }

  if (!system) {
    return {
      id64,
      name: null,
      loading: false,
      evidenceLabel: 'Selected context',
      evidenceTone: 'unknown',
      evidenceSummary: 'This system remains selected across Explore, Inspect, Plan, and Review until you choose another one.',
    };
  }

  const status = systemStatusLabel(system);
  const confidence = typeof system.archetype_confidence === 'number' ? Math.round(system.archetype_confidence * 100) : null;
  const primaryContext = system.primary_archetype ?? system.primary_economy ?? 'system context';

  if (status === 'Colonised') {
    return {
      id64,
      name: system.name ?? null,
      loading: false,
      evidenceLabel: 'Observed colony state',
      evidenceTone: 'observed',
      evidenceSummary: `${primaryContext} with inhabited or colonised evidence in view. Planner changes remain separate from observed status.`,
    };
  }

  if (status === 'Colonising') {
    return {
      id64,
      name: system.name ?? null,
      loading: false,
      evidenceLabel: 'Needs current review',
      evidenceTone: 'needs_review',
      evidenceSummary: `Colonisation activity is already in motion here. Inspect current evidence before changing or continuing a plan for ${system.name ?? 'this system'}.`,
    };
  }

  return {
    id64,
    name: system.name ?? null,
    loading: false,
    evidenceLabel: confidence != null && confidence < 60 ? 'Candidate needs review' : 'Available candidate',
    evidenceTone: confidence != null && confidence < 60 ? 'needs_review' : 'available',
    evidenceSummary: confidence != null
      ? `${primaryContext} remains a planning candidate with ${confidence}% archetype confidence. Canonical planner truth is still created in Plan, not by this evidence summary.`
      : `${primaryContext} remains a planning candidate. Canonical planner truth is still created in Plan, not by this evidence summary.`,
  };
}


// ─── Detail → SystemResult adapter ─────────────────────────────────────────
//
// Compare stores SystemResult. The detail endpoint returns snake_case, so
// bridge here into the compare snapshot shape.


// ─────────────────────────────────────────────────────────────────────────
// Finder tab — left rail form + right rail results
// ─────────────────────────────────────────────────────────────────────────

