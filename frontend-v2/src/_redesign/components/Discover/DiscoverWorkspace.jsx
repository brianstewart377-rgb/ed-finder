// Finder workspace — responsive layout, briefing collapsible, EDDN docked
// inside the results column so nothing overlaps.
import React, { useState } from 'react';
import { FilterRail } from './FilterRail';
import { ResultRail } from './ResultRail';
import { SystemDrawer } from './SystemDrawer';
import { EDDNFeed } from './EDDNFeed';
import { SYSTEMS, EDDN_FEED } from '../../lib/mockData';

const DEFAULT_BODY = {
  landable: { min: 0, max: 60 },  walkable:  { min: 0, max: 60 },
  blackHole:{ min: 0, max: 5  },  neutron:   { min: 0, max: 5  },
  whiteDwarf:{min: 0, max: 3  },  otherStar: { min: 0, max: 30 },
  elw:      { min: 0, max: 10 },  ww:        { min: 0, max: 20 },
  ammonia:  { min: 0, max: 10 },  gasGiant:  { min: 0, max: 30 },
  hmc:      { min: 0, max: 30 },  metalRich: { min: 0, max: 10 },
  rockyIce: { min: 0, max: 25 },  rocky:     { min: 0, max: 50 },
  icy:      { min: 0, max: 60 },  rings:     { min: 0, max: 30 },
  geo:      { min: 0, max: 30 },  bio:       { min: 0, max: 25 },
};

const DEFAULT_TOGGLES = {
  bio: false, geo: false, terra: false, hideCol: true, noBH: false,
  rings: false, volcanism: false, notTidal: false, popZero: false,
};

export function FinderWorkspace() {
  const [preset,    setPreset]    = useState('tech');
  const [distance,  setDistance]  = useState({ min: 0, max: 500 });
  const [perPage,   setPerPage]   = useState(50);
  const [minRating, setMinRating] = useState(40);
  const [body,      setBody]      = useState(DEFAULT_BODY);
  const [economy,   setEconomy]   = useState('Any');
  const [galaxy,    setGalaxy]    = useState(false);
  const [sortBy,    setSortBy]    = useState('Rating ↓');
  const [toggles,   setToggles]   = useState(DEFAULT_TOGGLES);
  const [selected,  setSelected]  = useState(null);
  const [eddnOpen,  setEddnOpen]  = useState(true);
  const [watched,   setWatched]   = useState(new Set([1004]));

  const setBodyKey = (k, v) => setBody((b) => ({ ...b, [k]: v }));
  const setToggle  = (k, v) => setToggles((t) => ({ ...t, [k]: v }));
  const reset = () => {
    setDistance({ min: 0, max: 500 });
    setPerPage(50);
    setMinRating(40);
    setBody(DEFAULT_BODY);
    setEconomy('Any');
    setGalaxy(false);
    setToggles(DEFAULT_TOGGLES);
  };
  const toggleWatch = (id) => setWatched((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  // Adaptive grid: with briefing → 3-col; without → 2-col (results expand)
  const gridCols = selected
    ? 'grid-cols-[400px_minmax(0,1fr)_380px]'
    : 'grid-cols-[400px_minmax(0,1fr)]';

  return (
    <div className={`flex-1 grid ${gridCols} gap-3 p-3 min-h-0 transition-[grid-template-columns] duration-300 ease-out`}>
      {/* LEFT — filter rail */}
      <FilterRail
        preset={preset} onPreset={setPreset}
        refSystem={{ name: 'Sol', x: 0, y: 0, z: 0 }}
        distance={distance} onDistance={setDistance}
        resultsPerPage={perPage} onResultsPerPage={setPerPage}
        minRating={minRating} onMinRating={setMinRating}
        bodySliders={body} onBodySlider={setBodyKey}
        economy={economy} onEconomy={setEconomy}
        galaxyWide={galaxy} onGalaxyWide={setGalaxy}
        sortBy={sortBy} onSortBy={setSortBy}
        toggles={toggles} onToggle={setToggle}
        onSearch={() => {}}
        onReset={reset}
      />

      {/* CENTER — results column with EDDN docked in its bottom-right */}
      <div className="relative min-w-0">
        <ResultRail
          systems={SYSTEMS}
          selectedId={selected?.id64}
          watched={watched}
          onSelect={setSelected}
          onWatch={toggleWatch}
          onCompare={() => {}}
        />
        {/* EDDN feed — docked inside the results column, never overlaps */}
        {eddnOpen && (
          <div className="absolute bottom-3 right-3 z-20">
            <EDDNFeed feed={EDDN_FEED} onClose={() => setEddnOpen(false)} />
          </div>
        )}
        {!eddnOpen && (
          <button
            onClick={() => setEddnOpen(true)}
            className="absolute bottom-3 right-3 z-20 readout px-3 py-1.5 text-[10px] font-display tracking-[0.16em] hover:text-[var(--ed-orange)]"
          >
            ◉ EDDN LIVE
          </button>
        )}
      </div>

      {/* RIGHT — system briefing (collapsible) */}
      {selected && (
        <SystemDrawer
          system={selected}
          watched={watched.has(selected.id64)}
          onClose={() => setSelected(null)}
          onWatch={toggleWatch}
        />
      )}
    </div>
  );
}
