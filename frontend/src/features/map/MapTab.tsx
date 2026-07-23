import { useEffect, useState } from 'react';
import { ChevronDown, Info, Layers } from 'lucide-react';
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
 *
 * Layout (redesign): the map is the primary surface and fills the viewport
 * beneath the app header. Secondary controls live in compact, collapsible
 * chrome — a slim toolbar, a "Layers" disclosure, an "About this view"
 * disclosure and a floating selection panel — so they stay out of the way
 * until needed. All test hooks, labels and ARIA relationships are preserved.
 */
export interface MapTabProps {
  systems:    SystemResult[];
  reference:  { name: string; x: number; z: number };
  initialSelectedSystemId?: number | null;
  onReturnToFinder?: () => void;
  onOpenSelectedSystem?: (id64: number) => void;
}

const LAYER_TOGGLES = [
  { key: 'frame', testid: 'map-frame-toggle', label: 'Galactic frame' },
  { key: 'regions', testid: 'map-regions-toggle', label: 'Regions' },
  { key: 'heatmap', testid: 'map-heatmap-toggle', label: 'Heatmap' },
  { key: 'clusters', testid: 'map-clusters-toggle', label: 'Clusters' },
  { key: 'timeline', testid: 'map-timeline-toggle', label: 'Timeline' },
] as const;

export function MapTab({
  systems,
  reference,
  initialSelectedSystemId = null,
  onReturnToFinder,
  onOpenSelectedSystem,
}: MapTabProps) {
  const [selected, setSelected] = useState<SystemResult | null>(null);
  const [viewMode, setViewMode] = useState<MapViewMode>('results');
  const [showFrame, setShowFrame] = useState(true);
  const [showRegions, setShowRegions] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showClusters, setShowClusters] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineBucket, setTimelineBucket] = useState<'month' | 'quarter' | 'year'>('month');

  const layerState: Record<string, boolean> = {
    frame: showFrame,
    regions: showRegions,
    heatmap: showHeatmap,
    clusters: showClusters,
    timeline: showTimeline,
  };
  const layerSetters: Record<string, (v: boolean) => void> = {
    frame: setShowFrame,
    regions: setShowRegions,
    heatmap: setShowHeatmap,
    clusters: setShowClusters,
    timeline: setShowTimeline,
  };

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
  const activeOverlayCount = [showRegions, showHeatmap, showClusters, showTimeline].filter(Boolean).length;
  const currentViewMode = VIEW_MODES.find((mode) => mode.id === viewMode) ?? VIEW_MODES[0];

  useEffect(() => {
    if (initialSelectedSystemId == null) return;
    const preselected = systems.find((system) => system.id64 === initialSelectedSystemId) ?? null;
    setSelected(preselected);
  }, [initialSelectedSystemId, systems]);

  return (
    <section
      data-testid="map-tab"
      aria-label="Galactic map tab"
      className="flex min-h-[520px] flex-col gap-2 lg:h-[calc(100vh-8.5rem)]"
    >
      {/* ── Slim toolbar ─────────────────────────────────────────────
       * One compact row: identity + result count, view-mode segmented
       * control, a Layers disclosure, and an About disclosure. Replaces the
       * old full-width wrapping header + separate marketing panel. */}
      <div className="panel flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 sm:px-4">
        <h2 className="flex items-center gap-2 font-display text-sm tracking-[0.14em] text-cyan">
          <span aria-hidden>🗺️</span>
          Galactic Map
        </h2>
        <span className="font-mono text-[11px] text-silver-dk">
          {systems.length} systems plotted from current search
        </span>

        <span className="hidden flex-1 sm:block" />

        {/* View mode segmented control */}
        <div
          data-testid="map-view-mode"
          role="group"
          aria-label="Map view mode"
          className="flex items-center overflow-hidden rounded-chunk-sm border border-border"
        >
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              data-testid={`map-view-${mode.id}`}
              aria-pressed={viewMode === mode.id}
              onClick={() => setViewMode(mode.id)}
              className={`px-2.5 py-1 font-mono text-[10px] tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70 ${
                viewMode === mode.id
                  ? 'bg-cyan/20 text-cyan'
                  : 'text-silver-dk hover:text-silver'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>

        {/* Layers disclosure — folds the five overlay toggles away by default */}
        <details className="group relative" data-testid="map-layers-menu">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver transition-colors hover:border-cyan/50 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70">
            <Layers size={12} aria-hidden />
            Layers
            {activeOverlayCount > 0 && (
              <span className="rounded-full bg-cyan/20 px-1.5 text-[9px] font-bold text-cyan">
                {activeOverlayCount}
              </span>
            )}
            <ChevronDown size={12} aria-hidden className="transition-transform group-open:rotate-180" />
          </summary>
          <div className="absolute right-0 z-20 mt-2 w-56 space-y-2 rounded-chunk border border-border bg-bg2/95 p-3 shadow-metal backdrop-blur-xl">
            {LAYER_TOGGLES.map((toggle) => (
              <label
                key={toggle.key}
                className="flex cursor-pointer select-none items-center gap-2 font-mono text-[11px] text-silver hover:text-text"
              >
                <input
                  type="checkbox"
                  data-testid={toggle.testid}
                  checked={layerState[toggle.key]}
                  onChange={(e) => layerSetters[toggle.key](e.target.checked)}
                  className="accent-cyan"
                />
                {toggle.label}
              </label>
            ))}
            {showTimeline && (
              <label className="flex items-center justify-between gap-2 border-t border-border/60 pt-2 font-mono text-[10px] text-silver-dk">
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
          </div>
        </details>

        {/* About disclosure — carries the product-value context without
         * consuming vertical space above the map. */}
        <details className="group relative" data-testid="map-product-value-panel" aria-labelledby="map-product-value-title">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-chunk-sm border border-border bg-bg3 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver transition-colors hover:border-cyan/50 hover:text-cyan focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70">
            <Info size={12} aria-hidden />
            About this view
            <ChevronDown size={12} aria-hidden className="transition-transform group-open:rotate-180" />
          </summary>
          <div className="absolute right-0 z-20 mt-2 w-[22rem] max-w-[90vw] space-y-3 rounded-chunk border border-border bg-bg2/95 p-4 shadow-metal backdrop-blur-xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-cyan/35 bg-cyan/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
                Secondary Explore surface
              </span>
              <span className="rounded-full border border-gold/35 bg-gold/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-gold">
                Stage 25G decision
              </span>
            </div>
            <div className="space-y-2">
              <h2 id="map-product-value-title" className="font-display text-sm tracking-[0.12em] text-text">
                Use Map for orientation, clustering, and inspect hand-off
              </h2>
              <p className="text-xs leading-relaxed text-silver">
                The map now makes one explicit product promise: it helps you orient the current Finder result set around {reference.name}, spot spread or clustering, and choose what to inspect next. It does not become the planning cockpit, validation surface, or export lane.
              </p>
            </div>
            <div className="grid gap-2">
              <DecisionFact
                title="Best when"
                body={systems.length > 0
                  ? `You want spatial context for ${systems.length} Finder result${systems.length === 1 ? '' : 's'} before deciding what to inspect.`
                  : 'You want a spatial read once Finder has produced a real result set.'}
              />
              <DecisionFact
                title="Current context"
                body={selected
                  ? `${selected.name ?? 'Selected system'} is in focus for inspect hand-off.`
                  : 'No system is selected yet. Click a plotted star to move from orientation into Inspect.'}
              />
              <DecisionFact
                title="Not for"
                body="Build decisions, planner truth, validation judgement, or export closeout. Those remain in Plan and Review."
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="map-return-to-finder"
                onClick={onReturnToFinder}
                className="btn-metal text-[11px] font-mono"
              >
                Back to Finder
              </button>
              <button
                type="button"
                data-testid="map-open-selected-system"
                disabled={!selected || !onOpenSelectedSystem}
                onClick={() => selected && onOpenSelectedSystem?.(selected.id64)}
                className={[
                  'rounded-chunk-sm border px-3 py-1.5 font-mono text-[11px] transition-colors',
                  selected && onOpenSelectedSystem
                    ? 'border-gold/55 bg-gold/15 text-gold hover:border-gold hover:bg-gold/20'
                    : 'cursor-not-allowed border-border/45 bg-bg3/25 text-silver-dk opacity-60',
                ].join(' ')}
              >
                Inspect selected system
              </button>
            </div>
          </div>
        </details>

        <span className="hidden w-full font-mono text-[10px] text-silver-dk md:inline md:w-auto">
          Drag to pan · scroll to zoom · click a star to inspect
        </span>
      </div>

      {/* ── Map surface ──────────────────────────────────────────────
       * The dominant element. Fills the remaining height of the immersive
       * route. Secondary panels (legend, layer status, selection) overlay
       * the map so they never push it down the page. */}
      {systems.length === 0 ? (
        <div className="panel-thin flex flex-1 flex-col items-center justify-center px-4 py-16 text-center">
          <div className="mb-2 text-3xl" aria-hidden>🗺️</div>
          <h3 className="mb-1 font-display text-sm tracking-wider text-cyan">No systems to plot</h3>
          <p className="mx-auto max-w-sm text-xs text-silver-dk">
            Run a search in the Finder tab and switch back here — results are plotted automatically.
          </p>
        </div>
      ) : (
        <div className="relative flex-1 min-h-0">
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

          {/* Floating status + legend, top-left */}
          <div className="pointer-events-none absolute left-3 top-3 z-10 flex max-w-[min(92%,32rem)] flex-col gap-2">
            <div className="pointer-events-auto">
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
                heatmapTruncated={layers.heatmap.data?.truncated ?? false}
                heatmapMaxCells={layers.heatmap.data?.max_cells ?? null}
                clustersLoading={layers.clusters.isLoading}
                clustersError={layers.clusters.isError}
                timelineLoading={layers.timeline.isLoading}
                timelineError={layers.timeline.isError}
              />
            </div>
            <div className="pointer-events-auto">
              <MapLegend
                activeLayerSummary={activeLayerSummary}
                currentViewLabel={currentViewMode.label}
                currentViewDescription={currentViewMode.description}
              />
            </div>
            {showTimeline && layers.timeline.data && (
              <div className="pointer-events-auto">
                <TimelineSummary
                  dataTestId="map-timeline-summary"
                  bucket={timelineBucket}
                  total={layers.timeline.data.total}
                  pointCount={layers.timeline.data.points.length}
                  latestDate={layers.timeline.data.points.at(-1)?.date ?? null}
                />
              </div>
            )}
          </div>

          {/* Floating selection panel, bottom-right on wide screens */}
          <div className="absolute inset-x-3 bottom-3 z-10 sm:inset-x-auto sm:right-3 sm:w-72">
            <div className="max-h-[45vh] overflow-y-auto">
              <SelectionPanel system={selected} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function DecisionFact({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-chunk-lg border border-border/60 bg-bg2/45 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{title}</div>
      <p className="mt-1 text-xs leading-relaxed text-silver">{body}</p>
    </div>
  );
}
