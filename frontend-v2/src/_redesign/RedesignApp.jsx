import React, { useState } from 'react';
import './redesign.css';
import { TopBar } from './components/Shell/TopBar';
import { StatusStrip } from './components/Shell/StatusStrip';
import { FinderWorkspace } from './components/Discover/DiscoverWorkspace';
import { MapWorkspace } from './components/Map/MapWorkspace';
import { PlanWorkspace } from './components/Plan/PlanWorkspace';
import { TrackWorkspace } from './components/Track/TrackWorkspace';
import {
  WatchlistTab, PinnedTab, CompareTab, OptimizerTab, AdminTab,
} from './components/Tabs/TabStubs';

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
          {tab === 'finder'    && <FinderWorkspace />}
          {tab === 'watchlist' && <WatchlistTab />}
          {tab === 'pinned'    && <PinnedTab />}
          {tab === 'compare'   && <CompareTab />}
          {tab === 'optimizer' && <OptimizerTab />}
          {tab === 'fc'        && <PlanWorkspace />}
          {tab === 'colony'    && <TrackWorkspace />}
          {tab === 'map'       && <MapWorkspace />}
          {tab === 'admin'     && <AdminTab />}
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
