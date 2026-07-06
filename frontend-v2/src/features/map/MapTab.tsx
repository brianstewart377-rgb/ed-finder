import { useState } from 'react';
import { GalacticMap, type MapViewMode } from './GalacticMap';
import { MapErrorBoundary } from './MapErrorBoundary';
import { useMapLayers } from './useMapLayers';
import type { SystemResult } from '@/types/api';
import { formatPopulationForSystem, formatDistance, formatCoords } from '@/lib/format';
import { archetypeTierFromScore, getDevelopmentScore, getFinderArchetypeSummary } from '@/lib/archetypes';

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

const VIEW_MODES: { id: MapViewMode; label: string; description: string }[] = [
  { id: 'results',   label: 'Results',   description: 'Fits the current Finder result dots.' },
  { id: 'galaxy',    label: 'Galaxy',    description: 'Frames the full galactic disc and axes.' },
  { id: 'reference', label: 'Reference', description: 'Centers the chosen reference system.' },
];

export function MapTab({ systems, reference }: MapTabProps) {
  const [selected, setSelected] = useState<SystemResult | null>(null);
  const [viewMode, setViewMode] = useState<MapViewMode>('results');
  const [showFrame, setShowFrame] = useState(true);
  const [showRegions, setShowRegions] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showClusters, setShowClusters] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineBucket, setTimelineBucket] = useState<'month' | 'quarter' | 'year'>('month');

  const layers = useMapLayers({
    regions:  { enabled: showRegions },
    heatmap:  { enabled: showHeatmap },
    clusters: { enabled: showClusters },
    timeline: { enabled: showTimeline, bucket: timelineBucket },
  });

  const activeLayers = [
    showRegions && layers.regions.data ? 'Regions' : null,
    showHeatmap && layers.heatmap.data ? 'Heatmap' : null,
    showClusters && layers.clusters.data ? 'Clusters' : null,
    showTimeline && layers.timeline.data ? 'Timeline' : null,
  ].filter(Boolean);
  const sourceLabel = activeLayers.length === 0
    ? 'Showing Finder results'
    : ['Finder results', ...activeLayers].join(' + ');
  const activeLayerSummary = [
    'Finder dots',
    showFrame ? 'Galactic frame' : null,
    showRegions ? 'Regions' : null,
    showHeatmap ? 'Heatmap' : null,
    showClusters ? 'Clusters' : null,
    showTimeline ? `Timeline (${timelineBucket})` : null,
  ].filter(Boolean).join(' + ');
  const currentViewMode = VIEW_MODES.find((mode) => mode.id === viewMode) ?? VIEW_MODES[0];

  return (
    <section data-testid="map-tab" aria-label="Galactic map tab" className="space-y-5">
      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">
          🗺️ Galactic Map
        </h2>
        <span className="font-mono text-xs text-silver-dk">
          {systems.length} systems plotted from current search
        </span>
        <span className="flex-1" />
        <div
          data-testid="map-view-mode"
          role="group"
          aria-label="Map view mode"
          className="flex items-center rounded-chunk-sm overflow-hidden border border-[hsl(216_10%_24%)]"
        >
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              data-testid={`map-view-${mode.id}`}
              aria-pressed={viewMode === mode.id}
              onClick={() => setViewMode(mode.id)}
              className={`px-2.5 py-1 font-mono text-[10px] tracking-wider transition-colors ${
                viewMode === mode.id
                  ? 'bg-orange/20 text-orange'
                  : 'text-silver-dk hover:text-silver'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="map-frame-toggle"
            checked={showFrame}
            onChange={(e) => setShowFrame(e.target.checked)}
            className="accent-orange"
          />
          Galactic frame
        </label>
        <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="map-regions-toggle"
            checked={showRegions}
            onChange={(e) => setShowRegions(e.target.checked)}
            className="accent-orange"
          />
          Regions
        </label>
        <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="map-heatmap-toggle"
            checked={showHeatmap}
            onChange={(e) => setShowHeatmap(e.target.checked)}
            className="accent-orange"
          />
          Heatmap
        </label>
        <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="map-clusters-toggle"
            checked={showClusters}
            onChange={(e) => setShowClusters(e.target.checked)}
            className="accent-orange"
          />
          Clusters
        </label>
        <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk cursor-pointer select-none">
          <input
            type="checkbox"
            data-testid="map-timeline-toggle"
            checked={showTimeline}
            onChange={(e) => setShowTimeline(e.target.checked)}
            className="accent-orange"
          />
          Timeline
        </label>
        {showTimeline && (
          <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk">
            Bucket
            <select
              data-testid="map-timeline-bucket"
              value={timelineBucket}
              onChange={(e) => setTimelineBucket(e.target.value as 'month' | 'quarter' | 'year')}
              className="rounded border border-border bg-bg3 px-2 py-1 text-[10px] text-silver"
            >
              <option value="month">Month</option>
              <option value="quarter">Quarter</option>
              <option value="year">Year</option>
            </select>
          </label>
        )}
        <span className="font-mono text-[10px] text-silver-dk">
          Drag to pan · scroll to zoom · click a star to inspect
        </span>
      </header>

      <MapLegend
        activeLayerSummary={activeLayerSummary}
        currentViewLabel={currentViewMode.label}
        currentViewDescription={currentViewMode.description}
      />

      {systems.length === 0 ? (
        <div className="panel-thin text-center py-16 px-4">
          <div className="text-3xl mb-2" aria-hidden>🗺️</div>
          <h3 className="font-display text-orange text-sm tracking-wider mb-1">No systems to plot</h3>
          <p className="text-silver-dk text-xs max-w-sm mx-auto">
            Run a search in the Finder tab and switch back here — results are plotted automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <div
              data-testid="map-source-badge"
              className="inline-flex items-center gap-2 px-3 py-1 rounded-chunk-sm text-[11px] font-mono text-silver-dk"
              style={{
                background: 'linear-gradient(180deg, rgba(28, 31, 36, 0.6), rgba(18, 20, 24, 0.6))',
                border: '1px solid hsl(216 10% 24%)',
              }}
            >
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: '#3ddc84' }}
              />
              <span>{sourceLabel}</span>
            </div>
            {showRegions && layers.regions.isLoading && (
              <span className="font-mono text-[10px] text-silver-dk animate-pulse">
                Loading regions…
              </span>
            )}
            {showRegions && layers.regions.isError && (
              <span className="font-mono text-[10px] text-red">
                Regions failed
              </span>
            )}
            {showHeatmap && layers.heatmap.isLoading && (
              <span className="font-mono text-[10px] text-silver-dk animate-pulse">
                Loading heatmap…
              </span>
            )}
            {showHeatmap && layers.heatmap.isError && (
              <span className="font-mono text-[10px] text-red">
                Heatmap failed
              </span>
            )}
            {showClusters && layers.clusters.isLoading && (
              <span className="font-mono text-[10px] text-silver-dk animate-pulse">
                Loading clusters…
              </span>
            )}
            {showClusters && layers.clusters.isError && (
              <span className="font-mono text-[10px] text-red">
                Clusters failed
              </span>
            )}
            {showTimeline && layers.timeline.isLoading && (
              <span className="font-mono text-[10px] text-silver-dk animate-pulse">
                Loading timeline…
              </span>
            )}
            {showTimeline && layers.timeline.isError && (
              <span className="font-mono text-[10px] text-red">
                Timeline failed
              </span>
            )}
          </div>
          {showTimeline && layers.timeline.data && (
            <TimelineSummary
              bucket={timelineBucket}
              total={layers.timeline.data.total}
              pointCount={layers.timeline.data.points.length}
              latestDate={layers.timeline.data.points.at(-1)?.date ?? null}
            />
          )}
          <div className="grid lg:grid-cols-[1fr_280px] gap-4">
            <MapErrorBoundary>
              <GalacticMap
                systems={systems}
                reference={reference}
                selectedId64={selected?.id64 ?? null}
                onSelect={setSelected}
                regions={layers.regions.data?.regions}
                heatmap={layers.heatmap.data}
                clusters={layers.clusters.data?.clusters}
                showGalacticFrame={showFrame}
                viewMode={viewMode}
              />
            </MapErrorBoundary>
            <SelectionPanel system={selected} />
          </div>
        </div>
      )}
    </section>
  );
}

function MapLegend({
  activeLayerSummary,
  currentViewLabel,
  currentViewDescription,
}: {
  activeLayerSummary: string;
  currentViewLabel: string;
  currentViewDescription: string;
}) {
  return (
    <details
      data-testid="map-legend"
      className="panel-thin px-4 py-2 text-[11px] text-silver-dk"
    >
      <summary className="cursor-pointer select-none font-mono text-orange-lt tracking-wider">
        Map legend · {currentViewLabel}: {currentViewDescription} · Active: {activeLayerSummary}
      </summary>
      <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        <LegendItem label="Results" value="Fits the current Finder result dots." />
        <LegendItem label="Galaxy" value="Frames the full galactic disc and axes." />
        <LegendItem label="Reference" value="Centers the chosen reference system." />
        <LegendItem label="Finder dots" value="Current Finder systems with archetype-led development scores." />
        <LegendItem label="Regions" value="Canonical galaxy region labels." />
        <LegendItem label="Heatmap" value="Voxel cells summarising local development-potential density." />
        <LegendItem label="Clusters" value="Approximate hulls around high-development grouped systems." />
        <LegendItem label="Timeline" value="Discovery-count buckets for the map scrubber foundation." />
      </div>
    </details>
  );
}

function TimelineSummary({
  bucket,
  total,
  pointCount,
  latestDate,
}: {
  bucket: 'month' | 'quarter' | 'year';
  total: number;
  pointCount: number;
  latestDate: string | null;
}) {
  return (
    <section
      data-testid="map-timeline-summary"
      className="panel-thin flex flex-wrap items-center gap-3 px-3 py-2 font-mono text-[11px] text-silver-dk"
    >
      <span className="text-orange-lt uppercase tracking-[0.14em]">Timeline foundation</span>
      <span>{pointCount} buckets</span>
      <span>{total} discoveries tracked</span>
      <span>Bucket: {bucket}</span>
      <span>Latest: {latestDate ?? 'Unknown'}</span>
    </section>
  );
}

function LegendItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] uppercase tracking-wider text-silver">{label}</div>
      <div className="leading-snug">{value}</div>
    </div>
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
  const archetypeScore = getDevelopmentScore(system);
  const tier = system.archetype_tier ?? archetypeTierFromScore(archetypeScore);
  const archetype = getFinderArchetypeSummary(system);
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
            tier === 'S' && 'bg-cyan/20 text-cyan border-cyan/50',
            tier === 'A' && 'bg-green/20 text-green border-green/50',
            tier === 'B' && 'bg-gold/20 text-gold border-gold/50',
            tier === 'C' && 'bg-orange/20 text-orange border-orange/50',
            tier === 'D' && 'bg-red/20 text-red border-red/50',
            tier == null && 'bg-bg4 text-text-dim border-border',
          ].filter(Boolean).join(' ')}
        >
          {tier ?? '—'} {archetypeScore ?? '—'}
        </span>
        <span className="text-text-dim">
          {formatPopulationForSystem(system)}
        </span>
      </div>
      <dl className="space-y-1 text-[11px]">
        {archetype && (
          <Row
            label={archetype.source === 'archetype' ? 'Primary archetype' : 'Suggested archetype'}
            value={archetype.label}
          />
        )}
        {system.buildability_score != null && <Row label="Buildability" value={`${system.buildability_score}/100`} />}
        {system.purity_score != null && <Row label="Purity" value={`${system.purity_score}/100`} />}
        {system.primaryEconomy && (
          <Row label="Economy" value={system.primaryEconomy} />
        )}
        {system.allegiance && <Row label="Allegiance" value={system.allegiance} />}
        {system.security   && <Row label="Security"   value={system.security} />}
        {formatDistance(system.distance) && (
          <Row label="Distance" value={formatDistance(system.distance)!} />
        )}
      </dl>
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
