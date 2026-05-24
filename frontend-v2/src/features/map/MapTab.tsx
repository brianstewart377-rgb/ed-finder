import { useState } from 'react';
import { GalacticMap } from './GalacticMap';
import type { SystemResult } from '@/types/api';
import { ratingTier, formatPopulationForSystem, formatDistance, formatCoords } from '@/lib/format';
import { displayRationale } from '@/lib/rationale';

/**
 * Map tab — wraps the GalacticMap with a selection-detail side panel.
 *
 * The systems list comes from the parent (today: search results from the
 * Finder tab; tomorrow: a dedicated `/api/map/heatmap` query that doesn't
 * blow the 50-row search limit). For the POC, plotting search results
 * already gives us a real feedback loop on the rendering pipeline.
 */
export interface MapTabProps {
  systems:    SystemResult[];
  reference:  { name: string; x: number; z: number };
}

export function MapTab({ systems, reference }: MapTabProps) {
  const [selected, setSelected] = useState<SystemResult | null>(null);

  return (
    <section data-testid="map-tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">
          🗺️ Galactic Map
        </h2>
        <span className="font-mono text-xs text-silver-dk">
          {systems.length} systems plotted from current search
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-silver-dk">
          Drag to pan · scroll to zoom · click a star to inspect
        </span>
      </header>

      {systems.length === 0 ? (
        <div className="panel-thin text-center py-16 px-4">
          <div className="text-3xl mb-2" aria-hidden>🗺️</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No systems to plot</h3>
          <p className="text-silver-dk text-xs max-w-sm mx-auto">
            Run a search in the Finder tab — its results are plotted here.
          </p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-[1fr_280px] gap-4">
          <GalacticMap
            systems={systems}
            reference={reference}
            selectedId64={selected?.id64 ?? null}
            onSelect={setSelected}
          />
          <SelectionPanel system={selected} />
        </div>
      )}
    </section>
  );
}

function SelectionPanel({ system }: { system: SystemResult | null }) {
  if (!system) {
    return (
      <aside
        data-testid="map-selection-panel"
        className="panel-thin border-dashed p-4 font-mono text-xs text-silver-dk space-y-2"
      >
        <div className="text-orange-lt text-sm font-display tracking-wider">Select a star</div>
        <p>Click any system on the map to see its details here.</p>
      </aside>
    );
  }
  const tier = ratingTier(system._rating?.score ?? null);
  const rationale = displayRationale(system._rating?.rationale);
  return (
    <aside
      data-testid="map-selection-panel"
      className="panel-thin p-4 font-mono text-xs space-y-3"
    >
      <div>
        <div className="text-orange-lt font-bold text-sm">{system.name}</div>
        <div className="text-text-dim text-[10px]">
          {formatCoords(system.coords, system.id64)}
        </div>
      </div>
      <div className="flex gap-2 items-center">
        <span
          className={[
            'px-2 py-0.5 rounded border font-bold',
            tier.label === 'EXCELLENT' && 'bg-green/20 text-green border-green/50',
            tier.label === 'GOOD'      && 'bg-gold/20 text-gold border-gold/50',
            tier.label === 'OK'        && 'bg-orange/20 text-orange border-orange/50',
            tier.label === 'POOR'      && 'bg-red/20 text-red border-red/50',
            tier.label === 'N/A'       && 'bg-bg4 text-text-dim border-border',
          ].filter(Boolean).join(' ')}
        >
          {tier.label} {system._rating?.score ?? '—'}
        </span>
        <span className="text-text-dim">
          {formatPopulationForSystem(system)}
        </span>
      </div>
      <dl className="space-y-1 text-[11px]">
        {system.primaryEconomy && (
          <Row label="Economy" value={system.primaryEconomy} />
        )}
        {system.allegiance && <Row label="Allegiance" value={system.allegiance} />}
        {system.security   && <Row label="Security"   value={system.security} />}
        {formatDistance(system.distance) && (
          <Row label="Distance" value={formatDistance(system.distance)!} />
        )}
      </dl>
      {rationale && (
        <p className="text-text-dim italic leading-snug border-t border-border pt-2">
          {rationale}
        </p>
      )}
    </aside>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-text-dim">{label}</dt>
      <dd className="text-text">{value}</dd>
    </div>
  );
}
