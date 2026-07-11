import { Suspense, lazy, useEffect, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppRoutes } from '@/app/AppRoutes';
import { setCoalsackBackgroundVariables } from '@/app/coalsackBackground';
import { SystemDetailOverlay } from '@/app/SystemDetailOverlay';
import { useProductShell } from '@/app/useProductShell';
import { NavBar } from '@/components/NavBar';
import { useAdmin } from '@/features/admin/useAdmin';
import { useCompare } from '@/features/compare/useCompare';
import { useFcPlanner } from '@/features/fc-planner/useFcPlanner';
import { EliteNewsBar } from '@/features/news/EliteNewsBar';
import { usePinned } from '@/features/pinned/usePinned';
import { useSearch } from '@/features/search/useSearch';
import { useSearchTuning } from '@/features/search-tuning/useSearchTuning';
import { useWatchlist } from '@/features/watchlist/useWatchlist';
import { useHashRoute, type HashRoute } from '@/hooks/useHashRoute';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import './index.css';

const LazyReactQueryDevtools = lazy(async () => ({ default: (await import('@tanstack/react-query-devtools')).ReactQueryDevtools }));

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
  const search = useSearch();
  const watchlist = useWatchlist();
  const pinned = usePinned();
  const compare = useCompare();
  const searchTuning = useSearchTuning();
  const fc = useFcPlanner();
  const admin = useAdmin();
  const [health, setHealth] = useState<string>('Checking API');
  const plannerWorkspaceRoute = route === 'colony-planner';
  const shell = useProductShell({
    route,
    selectedSystemId,
    plannerSystemId,
    plannerProjectId,
    plannerMode,
    navigate,
    openSystem,
    openColonyPlanner,
    closeSystem,
    watchlist,
  });

  useEffect(() => {
    api.health()
      .then(() => setHealth('Online'))
      .catch(() => setHealth('API connection issue'));
  }, []);

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
          selectedSystem={shell.shellSelectedSystem}
          onOpenSelectedSystemInPlan={shell.shellSelectedSystem && route !== 'colony-planner' ? shell.openShellContextInPlan : undefined}
        />

        <AppRoutes
          route={route}
          routeAlias={routeAlias}
          selectedSystemId={selectedSystemId}
          plannerSystemId={plannerSystemId}
          plannerProjectId={plannerProjectId}
          plannerMode={plannerMode}
          search={search}
          watchlist={watchlist}
          pinned={pinned}
          compare={compare}
          searchTuning={searchTuning}
          fc={fc}
          admin={admin}
          shellSelectedSystem={shell.shellSelectedSystem}
          savedSystemActionState={shell.savedSystemActionState}
          savedSystemNotice={shell.savedSystemNotice}
          setSavedSystemNotice={shell.setSavedSystemNotice}
          navigate={navigate}
          openSystemDetail={shell.openSystemDetail}
          openColonyPlanner={openColonyPlanner}
          openColonyPlannerWorkspace={shell.openColonyPlannerWorkspace}
          openOperatorDashboard={shell.openOperatorDashboard}
          toggleSavedSystem={shell.toggleSavedSystem}
        />

        <footer className="mt-16 text-center text-[11px] font-mono text-text-dim">
          Vite {import.meta.env.MODE} build · root-served live app
        </footer>

        <SystemDetailOverlay
          selectedSystemId={selectedSystemId}
          detailFocus={shell.detailFocus}
          shellSystemData={shell.shellSystem.data}
          watchlist={watchlist}
          pinned={pinned}
          compare={compare}
          savedSystemActionState={shell.savedSystemActionState}
          toggleSavedSystem={shell.toggleSavedSystem}
          startPlanFromSystemDetail={shell.startPlanFromSystemDetail}
          closeSystemDetail={shell.closeSystemDetail}
        />

        {!plannerWorkspaceRoute && <EliteNewsBar />}
      </main>
    </>
  );
}
