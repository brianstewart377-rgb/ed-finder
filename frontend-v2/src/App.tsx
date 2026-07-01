import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from '@/lib/queryClient';
import { api, ApiError } from '@/lib/api';
import { ResultCard } from '@/components/ResultCard';
import { NavBar } from '@/components/NavBar';
import { SearchForm } from '@/features/search/SearchForm';
import { useSearch } from '@/features/search/useSearch';
import { useWatchlist } from '@/features/watchlist/useWatchlist';
import { usePinned } from '@/features/pinned/usePinned';
import { toPinnedEntry } from '@/features/pinned/pinnedEntry';
import { useCompare } from '@/features/compare/useCompare';
import { CompareTab } from '@/features/compare/CompareTab';
import { useSearchTuning } from '@/features/search-tuning/useSearchTuning';
import { AdvancedSearchTuningTab } from '@/features/search-tuning/AdvancedSearchTuningTab';
import { useColony } from '@/features/colony/useColony';
import { ColonyTab } from '@/features/colony/ColonyTab';
import { useFcPlanner } from '@/features/fc-planner/useFcPlanner';
import { FcPlannerTab } from '@/features/fc-planner/FcPlannerTab';
import { useAdmin } from '@/features/admin/useAdmin';
import { AdminTab } from '@/features/admin/AdminTab';
import { OperatorCockpitTab } from '@/features/operator/OperatorCockpitTab';
import { MapTab } from '@/features/map/MapTab';
import { SystemDetailModal } from '@/features/system-detail/SystemDetailModal';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { ColonyPlannerWorkspace } from '@/features/colony-planner/ColonyPlannerWorkspace';
import { RavenStylePlannerPrototype } from '@/features/colony-planner/prototype/RavenStylePlannerPrototype';
import { useColonyProjectStore } from '@/features/colony-planner/colonyProjectStore';
import {
  defaultDraftProjectName,
  type ColonyProjectObjective,
  type ColonyProjectStartApproach,
} from '@/features/colony-planner/plannerDraftContext';
import { archetypeFromEconomy } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import { MyWorkWorkspace } from '@/features/my-work/MyWorkWorkspace';
import { EddnTicker } from '@/features/eddn/EddnTicker';
import { useHashRoute, type HashRoute } from '@/hooks/useHashRoute';
import './index.css';

const COALSACK_BG_VERSION = 'v=2';
const COALSACK_BG_2560 = 'coalsack-2560.jpg';
const COALSACK_BG_1600 = 'coalsack-1600.jpg';
const DEV_R1_ASSESSMENT_LAB_HASH = '#r1-assessment-lab';
const DevR1AssessmentLabApp = import.meta.env.DEV
  ? lazy(() => import('@/lab/r1-assessment-lab/R1AssessmentLabApp'))
  : null;

type SavedSystemActionState = 'idle' | 'saving' | 'removing';

interface SavedSystemNoticeState {
  tone: 'success' | 'error';
  message: string;
  detail: string;
  actionLabel?: string;
}

function savedSystemFailureDetail(error: unknown, attemptedRemove: boolean): string {
  if (error instanceof ApiError) {
    if (attemptedRemove && error.status === 404) {
      return 'This system was already absent from saved systems, so the view has been refreshed.';
    }
    if (error.status === 404) {
      return 'This system is not available to save right now. Refresh and try again.';
    }
    if (error.status === 410) {
      return 'Saved systems need a current browser sync key. Refresh and try again.';
    }
    return 'Saved systems are unavailable right now. Please try again.';
  }
  return error instanceof Error ? error.message : 'The saved-system request did not complete.';
}

function coalsackBackgroundCandidates(fileName: string): string[] {
  const base = import.meta.env.BASE_URL || '/';
  const normalizedBase = base.endsWith('/') ? base : `${base}/`;
  return Array.from(new Set([
    // Production can serve the app bundle from / while the v2 image assets live under /v2.
    `/v2/bg/${fileName}?${COALSACK_BG_VERSION}`,
    `${normalizedBase}bg/${fileName}?${COALSACK_BG_VERSION}`,
    `/bg/${fileName}?${COALSACK_BG_VERSION}`,
  ]));
}

async function resolveCoalsackBackgroundUrl(fileName: string): Promise<string> {
  const candidates = coalsackBackgroundCandidates(fileName);
  if (typeof fetch !== 'function') return candidates[0];

  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, { method: 'HEAD', cache: 'no-cache' });
      const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
      if (response.ok && contentType.startsWith('image/')) {
        return candidate;
      }
    } catch {
      // Try the next known deployment path.
    }
  }

  return candidates[0];
}

function setCoalsackBackgroundVariables(): () => void {
  let cancelled = false;
  const root = document.documentElement;

  void resolveCoalsackBackgroundUrl(COALSACK_BG_2560).then((url) => {
    if (!cancelled) root.style.setProperty('--coalsack-bg-2560', `url("${url}")`);
  });

  void resolveCoalsackBackgroundUrl(COALSACK_BG_1600).then((url) => {
    if (!cancelled) root.style.setProperty('--coalsack-bg-1600', `url("${url}")`);
  });

  return () => {
    cancelled = true;
  };
}

export default function App() {
  if (import.meta.env.DEV) {
    return <DevOnlyEntryBoundary />;
  }

  return <ProductionNormalRoot />;
}

function DevOnlyEntryBoundary() {
  const [hash, setHash] = useState(() => window.location.hash);

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  if (hash === DEV_R1_ASSESSMENT_LAB_HASH && DevR1AssessmentLabApp) {
    return (
      <Suspense fallback={null}>
        <DevR1AssessmentLabApp />
      </Suspense>
    );
  }

  return <ProductionNormalRoot />;
}

/**
 * v2 root: NavBar + tab content + system-detail modal overlay.
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
function ProductionNormalRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}

function AppInner() {
  const hashRoute = useHashRoute();

  useEffect(() => setCoalsackBackgroundVariables(), []);

  if (hashRoute.route === 'colony-planner-prototype') {
    return <PrototypeAppShell navigate={hashRoute.navigate} />;
  }

  return <LiveAppInner hashRoute={hashRoute} />;
}

function PrototypeAppShell({ navigate }: { navigate: HashRoute['navigate'] }) {
  return (
    <main className="min-h-screen max-w-none px-4 py-6 pb-10 sm:px-6 sm:py-10">
      <NavBar
        current="colony-planner-prototype"
        onNavigate={navigate}
        watchlistCount={0}
        pinnedCount={0}
        compareCount={0}
        colonyCount={0}
        fcCount={0}
        health="Visual"
        fullWidth
      />
      <RavenStylePlannerPrototype />
    </main>
  );
}

function LiveAppInner({ hashRoute }: { hashRoute: HashRoute }) {
  const { route, selectedSystemId, plannerSystemId, plannerProjectId, navigate, openSystem, openColonyPlanner, closeSystem } = hashRoute;
  const search    = useSearch();
  const watchlist = useWatchlist();
  const pinned    = usePinned();
  const compare   = useCompare();
  const searchTuning = useSearchTuning();
  const colony    = useColony();
  const fc        = useFcPlanner();
  const admin     = useAdmin();
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const [health, setHealth] = useState<string>('Checking API');
  const [detailFocus, setDetailFocus] = useState<'colony-planner' | null>(null);
  const [savedSystemActionState, setSavedSystemActionState] = useState<Record<number, SavedSystemActionState>>({});
  const [savedSystemNotice, setSavedSystemNotice] = useState<SavedSystemNoticeState | null>(null);
  const shellSystemId = plannerSystemId ?? selectedSystemId;
  const shellSystem = useSystemDetail(shellSystemId);

  const openSystemDetail = (id64: number, options?: { focus?: 'colony-planner' }) => {
    setDetailFocus(options?.focus ?? null);
    openSystem(id64);
  };

  const openColonyPlannerWorkspace = (id64: number) => {
    const systemId64 = Number(id64);
    if (!Number.isFinite(systemId64) || systemId64 <= 0) return;
    setDetailFocus(null);
    openColonyPlanner(systemId64);
  };

  const closeSystemDetail = () => {
    setDetailFocus(null);
    closeSystem();
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
      score?: number | null;
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
        score: hint.score ?? null,
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
    const targetArchetype = archetypeFromEconomy(system.economy_suggestion ?? system.primary_economy) ?? 'refinery_industrial';
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
    openColonyPlanner(system.id64, { projectId: saved.id });
  }, [openColonyPlanner, saveProject]);

  // First-paint: health + default search.
  useEffect(() => {
    api.health()
      .then(() => setHealth('Online'))
      .catch(() => setHealth('API connection issue'));
    void search.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const plannerWorkspaceRoute = route === 'colony-planner';

  return (
    <main
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
        colonyCount={colony.counts.total}
        fcCount={fc.waypoints.length}
        health={health}
        fullWidth={plannerWorkspaceRoute}
        selectedSystem={shellSystemId != null ? {
          id64: shellSystemId,
          name: shellSystem.data?.name ?? null,
          loading: shellSystem.loading,
        } : null}
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
          onShowOnMap={() => navigate('map')}
          onOpenDetail={openSystemDetail}
        />
      )}

      {(route === 'my-work' || route === 'watchlist' || route === 'pinned') && (
        <MyWorkWorkspace
          initialSection="saved-systems"
          routeSource={route === 'my-work' ? 'my-work' : route}
          watchlist={watchlist}
          pinned={pinned}
          onOpenDetail={openSystemDetail}
          onOpenPlanner={openColonyPlanner}
        />
      )}

      {route === 'compare' && (
        <CompareTab
          compare={compare}
          onOpenDetail={openSystemDetail}
        />
      )}

      {route === 'search-tuning' && (
        <AdvancedSearchTuningTab
          searchTuning={searchTuning}
          search={search}
          onOpenDetail={openSystemDetail}
          onOpenColonyPlanner={openColonyPlannerWorkspace}
        />
      )}

      {route === 'colony-planner' && (
        <ColonyPlannerWorkspace
          id64={plannerSystemId}
          projectId={plannerProjectId}
          onBackToFinder={() => navigate('finder')}
          onOpenSystemDetail={openSystemDetail}
          onOpenMyWork={() => navigate('my-work')}
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
        <FcPlannerTab fc={fc} onOpenDetail={openSystemDetail} />
      )}

      {route === 'colony' && (
        <ColonyTab colony={colony} onOpenDetail={openSystemDetail} />
      )}

      {route === 'admin' && (
        <AdminTab admin={admin} />
      )}

      {route === 'operator' && (
        <OperatorCockpitTab admin={admin} />
      )}

      {route === 'map' && (
        <MapTab
          systems={search.results}
          reference={{
            name: search.filters.refName,
            x:    search.filters.refCoords.x,
            z:    search.filters.refCoords.z,
          }}
        />
      )}

      <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
        Vite {import.meta.env.MODE} build · prototype · not yet production
      </footer>

      {selectedSystemId !== null && (
        <SystemDetailModal
          id64={selectedSystemId}
          focusIntent={detailFocus}
          onClose={closeSystemDetail}
          savedForLater={shellSystem.data ? watchlist.has(shellSystem.data.id64) : false}
          saveForLaterState={shellSystem.data ? savedSystemActionState[shellSystem.data.id64] ?? 'idle' : 'idle'}
          onToggleSaveForLater={(system) => {
            void toggleSavedSystem(system.id64, {
              name: system.name,
              x: system.x,
              y: system.y,
              z: system.z,
              population: system.population ?? null,
              is_colonised: !!system.is_colonised,
              score: system.score ?? null,
            });
          }}
          onStartPlan={startPlanFromSystemDetail}
          renderActions={(sys) => (
            <>
              <button
                type="button"
                disabled={!sys}
                onClick={() => sys && pinned.toggle({
	                  id64:         sys.id64,
	                  name:         sys.name,
	                  x:            sys.x ?? null,
	                  y:            sys.y ?? null,
	                  z:            sys.z ?? null,
                  population:   sys.population ?? null,
                  is_colonised: !!sys.is_colonised,
                  rating:       sys.score ?? null,
                  economy:      sys.economy_suggestion ?? sys.primary_economy ?? null,
                  pinned_at:    new Date().toISOString(),
                  distance:     null,
                })}
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
                onClick={() => sys && compare.toggle(toCompareSnapshot(sys))}
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
      )}

      {!plannerWorkspaceRoute && <EddnTicker onOpenSystem={openSystemDetail} />}
    </main>
  );
}

function SavedSystemNotice({
  notice,
  onDismiss,
  onOpenMyWork,
}: {
  notice: SavedSystemNoticeState | null;
  onDismiss: () => void;
  onOpenMyWork: () => void;
}) {
  if (!notice) return null;
  const isError = notice.tone === 'error';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      data-testid="saved-system-notice"
      className={[
        'fixed right-4 top-4 z-50 max-w-sm rounded-chunk-lg border p-3 font-mono text-xs shadow-metal',
        isError
          ? 'border-red/45 bg-red/15 text-red'
          : 'border-green/40 bg-bg2/95 text-green',
      ].join(' ')}
    >
      <div className="font-bold">{notice.message}</div>
      <p className="mt-1 leading-relaxed text-silver">{notice.detail}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {notice.actionLabel ? (
          <button
            type="button"
            onClick={onOpenMyWork}
            className="rounded-chunk-sm border border-green/40 bg-green/10 px-3 py-1.5 font-bold text-green hover:bg-green/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/80"
          >
            {notice.actionLabel}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-chunk-sm border border-border bg-bg4 px-3 py-1.5 font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

// ─── Detail → SystemResult adapter ─────────────────────────────────────────
//
// Compare stores SystemResult (camelCase rating fields). The detail endpoint
// returns snake_case. Bridge here so adding-to-compare from the modal lands
// the same shape Compare's matrix expects.

function toCompareSnapshot(sys: import('@/types/api').SystemDetail): import('@/types/api').SystemResult {
  return {
    id64:               sys.id64,
    name:               sys.name,
    coords:             { x: sys.x, y: sys.y, z: sys.z },
    distance:           null,
    population:         sys.population ?? null,
    primaryEconomy:     sys.primary_economy ?? null,
    secondaryEconomy:   sys.secondary_economy ?? null,
    security:           sys.security ?? null,
    allegiance:         sys.allegiance ?? null,
    government:         sys.government ?? null,
    is_colonised:       !!sys.is_colonised,
    main_star_type:     sys.main_star_type ?? null,
    main_star_subtype:  sys.main_star_subtype ?? null,
    _rating: {
      score:                  sys.score ?? null,
      scoreAgriculture:       sys.score_agriculture ?? null,
      scoreRefinery:          sys.score_refinery ?? null,
      scoreIndustrial:        sys.score_industrial ?? null,
      scoreHightech:          sys.score_hightech ?? null,
      scoreMilitary:          sys.score_military ?? null,
      scoreTourism:           sys.score_tourism ?? null,
      scoreExtraction:        sys.score_extraction ?? null,
      economySuggestion:      sys.economy_suggestion ?? null,
      terraformingPotential:  sys.terraforming_potential ?? null,
      bodyDiversity:          sys.body_diversity ?? null,
      confidence:             sys.confidence ?? null,
      rationale:              sys.rationale ?? null,
    },
    elw_count:           sys.elw_count ?? null,
    ww_count:            sys.ww_count ?? null,
    ammonia_count:       sys.ammonia_count ?? null,
    gas_giant_count:     sys.gas_giant_count ?? null,
    landable_count:      sys.landable_count ?? null,
    terraformable_count: sys.terraformable_count ?? null,
    bio_signal_total:    sys.bio_signal_total ?? null,
    geo_signal_total:    sys.geo_signal_total ?? null,
    neutron_count:       sys.neutron_count ?? null,
    black_hole_count:    sys.black_hole_count ?? null,
    white_dwarf_count:   sys.white_dwarf_count ?? null,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Finder tab — left rail form + right rail results
// ─────────────────────────────────────────────────────────────────────────

function FinderView({
  search, watchlist, pinned, compare, savedActionStates, onToggleSavedForLater, onShowOnMap, onOpenDetail,
}: {
  search:    ReturnType<typeof useSearch>;
  watchlist: ReturnType<typeof useWatchlist>;
  pinned:    ReturnType<typeof usePinned>;
  compare:   ReturnType<typeof useCompare>;
  savedActionStates: Record<number, SavedSystemActionState>;
  onToggleSavedForLater: (
    id64: number,
    hint: {
      name?: string | null;
      x?: number | null;
      y?: number | null;
      z?: number | null;
      population?: number | null;
      is_colonised?: boolean;
      score?: number | null;
    },
  ) => Promise<void>;
  onShowOnMap:  () => void;
  onOpenDetail: (id64: number, options?: { focus?: 'colony-planner' }) => void;
}) {
  const { filters, setFilters, reset, run, state, results } = search;

  return (
    <div className="space-y-4">
      <header data-testid="finder-page-heading" className="max-w-4xl">
        <h1 className="font-display text-2xl tracking-[0.12em] text-orange sm:text-3xl">
          Finder
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-silver sm:text-base">
          Find promising systems. Save them for later or inspect them before starting a plan.
        </p>
      </header>

      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <aside className="panel overflow-hidden lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-11rem)] flex flex-col">
        <div className="overflow-y-auto flex-1 p-1">
          <SearchForm
            filters={filters}
            onChange={setFilters}
            onSubmit={() => void run()}
            onReset={reset}
            loading={state.kind === 'loading'}
          />
        </div>
      </aside>

      <section data-testid="results-panel">
        {state.kind === 'idle' && (
          <EmptyState
            icon="🔭"
            title="Ready to search"
            hint="Adjust the filters on the left and hit SEARCH."
          />
        )}

        {state.kind === 'loading' && (
          <div className="text-text-dim font-mono text-sm py-12 text-center">
            Scanning systems…
          </div>
        )}

        {state.kind === 'err' && (
          <div className="rounded border border-red/50 bg-red/10 p-4 font-mono text-sm text-red">
            <div className="font-bold mb-1">Search failed</div>
            <div className="text-xs">{state.message}</div>
          </div>
        )}

        {state.kind === 'ok' && (
          <>
            <SummaryBar
              count={state.data.count}
              total={state.data.total}
              queriedAt={state.queriedAt}
            />
            {results.length === 0 ? (
              <EmptyState
                icon="🔍"
                title="No systems found"
                hint="Try expanding the radius or relaxing filters."
              />
            ) : (
              <ul className="space-y-2">
                {results.map((sys, i) => (
                  <li key={sys.id64}>
                    <ResultCard
                      system={sys}
                      index={i}
                      isPinned={pinned.has(sys.id64)}
                      isCompared={compare.has(sys.id64)}
                      isSavedForLater={watchlist.has(sys.id64)}
                      savedActionState={savedActionStates[sys.id64] ?? 'idle'}
                      onToggleSavedForLater={(id) => {
                        void onToggleSavedForLater(id, {
                          name:       sys.name,
                          x:          sys.coords?.x ?? null,
                          y:          sys.coords?.y ?? null,
                          z:          sys.coords?.z ?? null,
                          population: sys.population ?? null,
                          is_colonised: !!sys.is_colonised,
                          score:      sys._rating?.score ?? null,
                        });
                      }}
                      onShowOnMap={onShowOnMap}
                      onPin={() => pinned.toggle(toPinnedEntry(sys))}
                      onCompare={() => compare.toggle(sys)}
                      onOpenDetail={onOpenDetail}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        </section>
      </div>
    </div>
  );
}

function SummaryBar({ count, total, queriedAt }: {
  count: number; total: number; queriedAt: number;
}) {
  const elapsed = ((Date.now() - queriedAt) / 1000).toFixed(1);
  return (
    <div
      data-testid="search-summary"
      className="mb-4 flex flex-wrap items-center gap-3 px-3 py-2 rounded border border-border bg-bg3/40 text-xs font-mono"
    >
      <span className="text-orange font-bold">{count}</span>
      <span className="text-text-dim">shown</span>
      <span className="text-text-dim">·</span>
      <span className="text-text-dim">{total.toLocaleString()} total</span>
      <span className="flex-1" />
      <span className="text-text-dim">queried {elapsed}s ago</span>
    </div>
  );
}

function EmptyState({ icon, title, hint }: {
  icon: string; title: string; hint: string;
}) {
  return (
    <div className="text-center py-16 px-4 rounded border border-dashed border-border">
      <div className="text-3xl mb-2" aria-hidden>{icon}</div>
      <h3 className="font-mono text-orange text-sm mb-1">{title}</h3>
      <p className="text-text-dim text-xs max-w-sm mx-auto">{hint}</p>
    </div>
  );
}
