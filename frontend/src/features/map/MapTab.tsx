import { useState } from 'react';
import { GalacticMap, type MapViewMode } from './GalacticMap';
import { MapErrorBoundary } from './MapErrorBoundary';
import { MapLayerStatusRow, MapLegend, SelectionPanel, TimelineSummary, VIEW_MODES } from './mapTabPanels';
import { useMapLayers } from './useMapLayers';
import type { SystemResult } from '@/types/api';

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
          <MapLayerStatusRow
            sourceLabel={sourceLabel}
            showRegions={showRegions}
            showHeatmap={showHeatmap}
            showClusters={showClusters}
            showTimeline={showTimeline}
            timelineBucket={timelineBucket}
            regionsLoading={layers.regions.isLoading}
            regionsError={layers.regions.isError}
            heatmapLoading={layers.heatmap.isLoading}
            heatmapError={layers.heatmap.isError}
            clustersLoading={layers.clusters.isLoading}
            clustersError={layers.clusters.isError}
            timelineLoading={layers.timeline.isLoading}
            timelineError={layers.timeline.isError}
          />
          {showTimeline && layers.timeline.data && (
            <TimelineSummary
              dataTestId="map-timeline-summary"
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
