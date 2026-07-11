import { Suspense, lazy } from 'react';
import { FinderView } from '@/app/FinderView';
import { SavedSystemNotice } from '@/app/SavedSystemNotice';
import type { HashRoute } from '@/hooks/useHashRoute';
import type { UseAdmin } from '@/features/admin/useAdmin';
import type { UseCompare } from '@/features/compare/useCompare';
import type { UseFcPlanner } from '@/features/fc-planner/useFcPlanner';
import type { UsePinned } from '@/features/pinned/usePinned';
import { useSearch } from '@/features/search/useSearch';
import type { UseSearchTuning } from '@/features/search-tuning/useSearchTuning';
import type { UseWatchlist } from '@/features/watchlist/useWatchlist';
import type { SavedSystemActionState, SavedSystemNoticeState } from '@/app/savedSystems';
import type { ShellSelectedSystem } from '@/app/useProductShell';

const LazyCompareTab = lazy(async () => ({ default: (await import('@/features/compare/CompareTab')).CompareTab }));
const LazyAdvancedSearchTuningTab = lazy(async () => ({ default: (await import('@/features/search-tuning/AdvancedSearchTuningTab')).AdvancedSearchTuningTab }));
const LazyFcPlannerTab = lazy(async () => ({ default: (await import('@/features/fc-planner/FcPlannerTab')).FcPlannerTab }));
const LazyAdminTab = lazy(async () => ({ default: (await import('@/features/admin/AdminTab')).AdminTab }));
const LazyOperatorCockpitTab = lazy(async () => ({ default: (await import('@/features/operator/OperatorCockpitTab')).OperatorCockpitTab }));
const LazyMapTab = lazy(async () => ({ default: (await import('@/features/map/MapTab')).MapTab }));
const LazyColonyPlannerWorkspace = lazy(async () => ({ default: (await import('@/features/colony-planner/ColonyPlannerWorkspace')).ColonyPlannerWorkspace }));
const LazyMyWorkWorkspace = lazy(async () => ({ default: (await import('@/features/my-work/MyWorkWorkspace')).MyWorkWorkspace }));

interface AppRoutesProps {
  route: HashRoute['route'];
  routeAlias: HashRoute['routeAlias'];
  selectedSystemId: number | null;
  plannerSystemId: number | null;
  plannerProjectId: string | null;
  plannerMode: HashRoute['plannerMode'];
  search: ReturnType<typeof useSearch>;
  watchlist: UseWatchlist;
  pinned: UsePinned;
  compare: UseCompare;
  searchTuning: UseSearchTuning;
  fc: UseFcPlanner;
  admin: UseAdmin;
  shellSelectedSystem: ShellSelectedSystem | null;
  savedSystemActionState: Record<number, SavedSystemActionState>;
  savedSystemNotice: SavedSystemNoticeState | null;
  setSavedSystemNotice: (notice: SavedSystemNoticeState | null) => void;
  navigate: HashRoute['navigate'];
  openSystemDetail: (id64: number, options?: { focus?: 'colony-planner'; hostRoute?: HashRoute['route'] }) => void;
  openColonyPlanner: HashRoute['openColonyPlanner'];
  openColonyPlannerWorkspace: (id64: number) => void;
  openOperatorDashboard: (sourceRunKey?: string) => void;
  toggleSavedSystem: (
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
  ) => Promise<void>;
}

export function AppRoutes({
  route,
  routeAlias,
  selectedSystemId,
  plannerSystemId,
  plannerProjectId,
  plannerMode,
  search,
  watchlist,
  pinned,
  compare,
  searchTuning,
  fc,
  admin,
  shellSelectedSystem,
  savedSystemActionState,
  savedSystemNotice,
  setSavedSystemNotice,
  navigate,
  openSystemDetail,
  openColonyPlanner,
  openColonyPlannerWorkspace,
  openOperatorDashboard,
  toggleSavedSystem,
}: AppRoutesProps) {
  const plannerWorkspaceRoute = route === 'colony-planner';

  return (
    <>
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
              x: search.filters.refCoords.x,
              z: search.filters.refCoords.z,
            }}
            initialSelectedSystemId={selectedSystemId}
            onReturnToFinder={() => navigate('finder')}
            onOpenSelectedSystem={(id64) => openSystemDetail(id64, { hostRoute: 'map' })}
          />
        )}
      </Suspense>
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
