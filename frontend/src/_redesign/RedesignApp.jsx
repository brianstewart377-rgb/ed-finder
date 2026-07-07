import React, { Suspense, lazy, useState } from 'react';
import './redesign.css';
import { TopBar } from './components/Shell/TopBar';
import { StatusStrip } from './components/Shell/StatusStrip';
import { FinderWorkspace } from './components/Discover/DiscoverWorkspace';

const LazyMapWorkspace = lazy(async () => ({ default: (await import('./components/Map/MapWorkspace')).MapWorkspace }));
const LazyPlanWorkspace = lazy(async () => ({ default: (await import('./components/Plan/PlanWorkspace')).PlanWorkspace }));
const LazyTrackWorkspace = lazy(async () => ({ default: (await import('./components/Track/TrackWorkspace')).TrackWorkspace }));
const LazyWatchlistTab = lazy(async () => ({ default: (await import('./components/Tabs/TabStubs')).WatchlistTab }));
const LazyPinnedTab = lazy(async () => ({ default: (await import('./components/Tabs/TabStubs')).PinnedTab }));
const LazyCompareTab = lazy(async () => ({ default: (await import('./components/Tabs/TabStubs')).CompareTab }));
const LazySearchTuningTab = lazy(async () => ({ default: (await import('./components/Tabs/TabStubs')).SearchTuningTab }));
const LazyAdminTab = lazy(async () => ({ default: (await import('./components/Tabs/TabStubs')).AdminTab }));

function App() {
  const [tab, setTab] = useState('finder');

  return (
    <>
      {/* Nebula parallax layer 2 (between background and starfield) */}
      <div className="nebula-layer-2" />
      <div className="nebula-layer-3" />
      {/* Starfield sits above the nebula but below the UI */}
      <div className="starfield-overlay" />

      <div className="h-screen flex flex-col overflow-hidden" data-testid="app-shell">
        <TopBar tab={tab} onTab={setTab} />

        <main className="flex-1 flex flex-col min-h-0">
          {tab === 'finder' && <FinderWorkspace />}
          {tab !== 'finder' && (
            <Suspense fallback={<WorkspaceFallback label="Loading redesign workspace" />}>
              {tab === 'watchlist' && <LazyWatchlistTab />}
              {tab === 'pinned' && <LazyPinnedTab />}
              {tab === 'compare' && <LazyCompareTab />}
              {tab === 'search-tuning' && <LazySearchTuningTab />}
              {tab === 'fc' && <LazyPlanWorkspace />}
              {tab === 'colony' && <LazyTrackWorkspace />}
              {tab === 'map' && <LazyMapWorkspace />}
              {tab === 'admin' && <LazyAdminTab />}
            </Suspense>
          )}
        </main>

        <StatusStrip
          visible={6}
          watched={1}
          topScore={89}
          topName="Wregoe XX-1 b48-2"
        />
      </div>
    </>
  );
}

export default App;

function WorkspaceFallback({ label }) {
  return (
    <section className="flex min-h-0 flex-1 items-center justify-center p-6 text-center">
      <div className="panel glass text-[11px] uppercase tracking-[0.18em] text-slate-300">
        {label}...
      </div>
    </section>
  );
}
