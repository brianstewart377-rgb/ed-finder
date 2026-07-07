// Map workspace — combined 2D + 3D, briefing dismissible, EDDN feed closable.
import React, { useState } from 'react';
import { MapCanvas } from './MapCanvas';
import { LayerToggles } from './LayerToggles';
import { SystemDrawer } from '../Discover/SystemDrawer';
import { EDDNFeed } from '../Discover/EDDNFeed';
import { HudButton } from '../UI/Hud';
import { Box, Square, Maximize2 } from 'lucide-react';
import { SYSTEMS, REGIONS, CLUSTERS, HEATMAP, EDDN_FEED, ECONOMIES } from '../../lib/mockData';

export function MapWorkspace() {
  const [selected,    setSelected]    = useState(null);
  const [watched,     setWatched]     = useState(new Set([1004]));
  const [perspective, setPerspective] = useState('2d');
  const [eddnOpen,    setEddnOpen]    = useState(true);
  const [layersOpen,  setLayersOpen]  = useState(true);
  const [layers, setLayers] = useState({
    regions: true, clusters: true, heatmap: true,
    systems: true, watchlist: true, routes: false,
  });
  const [economy, setEconomy] = useState('overall');

  const toggleLayer = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }));
  const toggleWatch = (id) => setWatched((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const grid = selected ? 'grid-cols-[minmax(0,1fr)_380px]' : 'grid-cols-[minmax(0,1fr)]';

  return (
    <div className={`flex-1 grid ${grid} gap-3 p-3 min-h-0 transition-[grid-template-columns] duration-300 ease-out`}>
      <div className="relative panel overflow-hidden">
        {/* 2D / 3D / FRAME toolbar */}
        <div className="absolute top-3 left-3 z-10 glass rounded-xl flex items-center gap-1 p-1.5">
          <HudButton
            size="sm" icon={Square}
            active={perspective === '2d'}
            onClick={() => setPerspective('2d')}
          >
            2D
          </HudButton>
          <HudButton
            size="sm" icon={Box}
            active={perspective === '3d'}
            onClick={() => setPerspective('3d')}
          >
            3D
          </HudButton>
          <span className="w-px h-4 bg-[hsla(232,22%,60%,0.3)] mx-1" />
          <HudButton size="sm" icon={Maximize2}>FRAME</HudButton>
        </div>

        <MapCanvas
          systems={SYSTEMS} regions={REGIONS}
          clusters={CLUSTERS} heatmap={HEATMAP}
          layers={layers}
          selectedId={selected?.id64}
          onSelect={setSelected}
          viewport={`${perspective.toUpperCase()} · GALACTIC · 500 LY`}
        />

        {/* Layer toggles top-right (closable) */}
        {layersOpen ? (
          <div className="absolute top-3 right-3 z-10">
            <LayerToggles
              layers={layers} onToggle={toggleLayer}
              economy={economy} onEconomy={setEconomy}
              economies={ECONOMIES}
              onClose={() => setLayersOpen(false)}
            />
          </div>
        ) : (
          <button
            onClick={() => setLayersOpen(true)}
            className="absolute top-3 right-3 z-10 readout px-3 py-1.5 text-[10px] font-display tracking-[0.16em] hover:text-[var(--ed-orange)]"
          >
            LAYERS
          </button>
        )}

        {/* EDDN feed bottom-right (closable) */}
        {eddnOpen ? (
          <div className="absolute bottom-3 right-3 z-10">
            <EDDNFeed feed={EDDN_FEED} onClose={() => setEddnOpen(false)} />
          </div>
        ) : (
          <button
            onClick={() => setEddnOpen(true)}
            className="absolute bottom-3 right-3 z-10 readout px-3 py-1.5 text-[10px] font-display tracking-[0.16em] hover:text-[var(--ed-orange)]"
          >
            ◉ EDDN LIVE
          </button>
        )}

        {/* Selection callout bottom-left */}
        {selected && (
          <div className="absolute bottom-3 left-3 z-10 glass rounded-xl px-3.5 py-2.5 max-w-[320px]">
            <div className="font-display text-[11px] tracking-[0.12em] text-[var(--ed-orange-lt)] text-glow-orange mb-1">
              {selected.name}
            </div>
            <div className="font-mono text-[10px] text-[var(--steel-300)] leading-snug">
              {selected.rationale}
            </div>
          </div>
        )}
      </div>

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
