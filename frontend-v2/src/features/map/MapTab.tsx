import { useState } from 'react';
import { GalacticMap } from './GalacticMap';
import type { SystemResult } from '@/types/api';
import { ratingTier, formatPopulation } from '@/lib/format';

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
    <section data-testid="map-tab" className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">
          🗺️ Galactic Map
        </h2>
        <span className="font-mono text-xs text-text-dim">
          {systems.length} systems plotted from current search
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-text-dim">
          Drag to pan · scroll to zoom · click a star to inspect
        </span>
      </header>

      {systems.length === 0 ? (
        <div className="text-center py-16 px-4 rounded border border-dashed border-border">
          <div className="text-3xl mb-2" aria-hidden>🗺️</div>
          <h3 className="font-mono text-orange text-sm mb-1">No systems to plot</h3>
          <p className="text-text-dim text-xs max-w-sm mx-auto">
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
        className="rounded-md border border-dashed border-border p-4 font-mono text-xs text-text-dim space-y-2"
      >
        <div className="text-orange text-sm">Select a star</div>
        <p>Click any system on the map to see its details here.</p>
      </aside>
    );
  }
  const tier = ratingTier(system._rating?.score ?? null);
  return (
    <aside
      data-testid="map-selection-panel"
      className="rounded-md border border-border p-4 font-mono text-xs space-y-3 bg-bg3/40"
    >
      <div>
        <div className="text-orange font-bold text-sm">{system.name}</div>
        {system.coords && (
          <div className="text-text-dim text-[10px]">
            {system.coords.x.toFixed(2)}, {system.coords.y.toFixed(2)}, {system.coords.z.toFixed(2)}
          </div>
        )}
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
          {formatPopulation(system.population)}
        </span>
      </div>
      <dl className="space-y-1 text-[11px]">
        {system.primaryEconomy && (
          <Row label="Economy" value={system.primaryEconomy} />
        )}
        {system.allegiance && <Row label="Allegiance" value={system.allegiance} />}
        {system.security   && <Row label="Security"   value={system.security} />}
        {system.distance != null && (
          <Row label="Distance" value={`${system.distance.toFixed(2)} LY`} />
        )}
      </dl>
      {system._rating?.rationale && (
        <p className="text-text-dim italic leading-snug border-t border-border pt-2">
          {system._rating.rationale}
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
