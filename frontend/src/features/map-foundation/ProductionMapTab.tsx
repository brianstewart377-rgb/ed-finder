import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  initOverlapCycling,
  reduceScene,
  type MapInteractionEvent,
  type MapSceneState,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { MapErrorBoundary } from '@/features/map/MapErrorBoundary';
import type { MapTabProps } from '@/features/map/MapTab';
import {
  MapLayerStatusRow,
  MapLegend,
  SelectionPanel,
  TimelineSummary,
  VIEW_MODES,
} from '@/features/map/mapTabPanels';
import { useMapLayers } from '@/features/map/useMapLayers';
import { applyFeatureHandoff, resolveMapInteraction } from './feature-handoffs';
import {
  LIVE_ROUTE_HEAP_BUDGET_BYTES,
  measureLiveRouteHeap,
  type LiveRouteMapSnapshot,
} from './live-route-memory';
import {
  applyViewPreset,
  composeProductionParity,
  PRODUCTION_PARITY_LIMITS,
  type MapViewPreset,
} from './production-parity';
import { useAuthoritativeRegionLayer } from './production-regions';
import { R3FMapFoundation } from './R3FMapFoundation';
import type { RegionLayerData, ViewportSize } from './types';
import './ProductionMapTab.css';

const EMPTY_REGIONS: RegionLayerData = { labels: [], boundaries: [] };
const DEFAULT_VIEWPORT: ViewportSize = { width: 1280, height: 720 };

function emptyProductionScene(reference: { x: number; z: number }): MapSceneState {
  return {
    sceneRevision: 1,
    oneTimeFitIntent: null,
    cameraIntent: 'user',
    camera: { center: { ...reference }, zoom: 64, pitchDeg: 0, bearingDeg: 0 },
    origin: { ...reference },
    systems: [],
    selectedSystemId64: null,
    selectedDetailOverride: null,
    highlights: [],
    clusters: [],
    routes: [],
    annotations: [],
    layers: [
      { type: 'regions', visible: true },
      { type: 'heatmap', visible: false },
      { type: 'timeline', visible: false, bucket: 'month' },
      { type: 'routes', visible: false },
      { type: 'annotations', visible: false },
    ],
    returnWorkflow: null,
    keyboardCompanion: { phase: { type: 'idle' } },
    boundedResponse: { count: 0, truncated: false, continuationToken: null },
    guaranteedSystemIds: [],
  };
}

export function ProductionMapTab({
  systems,
  reference,
  initialSelectedSystemId = null,
  onReturnToFinder,
  onOpenSelectedSystem,
}: MapTabProps) {
  const boundedSystems = useMemo(
    () => systems.slice(0, PRODUCTION_PARITY_LIMITS.finderSystems),
    [systems],
  );
  const referenceCoords = useMemo(
    () => ({ x: reference.x, z: reference.z }),
    [reference.x, reference.z],
  );
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const [scene, setScene] = useState<MapSceneState>(() => emptyProductionScene(referenceCoords));
  const [viewPreset, setViewPreset] = useState<MapViewPreset>('results');
  const [showRegions, setShowRegions] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showClusters, setShowClusters] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineBucket, setTimelineBucket] = useState<'month' | 'quarter' | 'year'>('month');
  const [overlapCandidateIds, setOverlapCandidateIds] = useState<number[]>([]);
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handoff = applyFeatureHandoff(emptyProductionScene(referenceCoords), {
      type: 'finder',
      systems: boundedSystems,
      selectedSystemId64: initialSelectedSystemId,
      metadata: {
        count: systems.length,
        truncated: systems.length > boundedSystems.length,
        continuationToken: null,
      },
    });
    setScene(applyViewPreset(handoff.scene, 'results', referenceCoords, viewport));
    setViewPreset('results');
  }, [boundedSystems, initialSelectedSystemId, referenceCoords, systems.length, viewport]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
        const width = Math.round(entry.contentRect.width);
        const height = Math.round(entry.contentRect.height);
        setViewport((current) => current.width === width && current.height === height
          ? current
          : { width, height });
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layers = useMapLayers({
    heatmap: { enabled: showHeatmap, max_cells: PRODUCTION_PARITY_LIMITS.heatmapCells },
    clusters: { enabled: showClusters, max_hulls: PRODUCTION_PARITY_LIMITS.aggregateHulls },
    timeline: { enabled: showTimeline, bucket: timelineBucket },
  });
  const regionLayer = useAuthoritativeRegionLayer();
  const layerError = [regionLayer, layers.heatmap, layers.clusters, layers.timeline]
    .find((layer) => layer.isError)?.error?.message ?? null;
  const composition = useMemo(() => composeProductionParity({
    systemCount: scene.systems.length,
    error: layerError,
    heatmap: showHeatmap ? layers.heatmap.data : undefined,
    hulls: showClusters ? layers.clusters.data?.clusters : undefined,
    timeline: showTimeline ? layers.timeline.data : undefined,
    timelineBucket,
  }), [
    layerError,
    layers.clusters.data,
    layers.heatmap.data,
    layers.timeline.data,
    scene.systems.length,
    showClusters,
    showHeatmap,
    showTimeline,
    timelineBucket,
  ]);

  const onInteraction = useCallback((event: MapInteractionEvent) => {
    if (event.type === 'overlapChoiceRequired') {
      setOverlapCandidateIds(event.candidateSystemIds);
      setScene((current) => ({
        ...current,
        keyboardCompanion: {
          phase: initOverlapCycling(event.candidateSystemIds.map((systemId64) => ({ systemId64, distancePx: 0 }))),
        },
      }));
      return;
    }
    if (event.type === 'contextStateChanged') return;
    setScene((current) => resolveMapInteraction(current, event).scene);
    if (event.type === 'selectSystem' || event.type === 'overlapChoice' || event.type === 'deselectSystem') {
      setOverlapCandidateIds([]);
    }
  }, []);

  const selectOverlapCandidate = useCallback((systemId64: number) => {
    setScene((current) => reduceScene(current, { type: 'selectSystem', systemId64 }));
    setOverlapCandidateIds([]);
  }, []);

  const selectViewPreset = useCallback((preset: MapViewPreset) => {
    setViewPreset(preset);
    setScene((current) => applyViewPreset(current, preset, referenceCoords, viewport));
  }, [referenceCoords, viewport]);

  const selected = systems.find((system) => system.id64 === scene.selectedSystemId64) ?? null;
  const currentViewMode = VIEW_MODES.find((mode) => mode.id === viewPreset) ?? VIEW_MODES[0];
  const activeLayerSummary = [
    'Finder dots',
    showRegions ? 'Regions' : null,
    showHeatmap ? 'Heatmap' : null,
    showClusters ? 'Clusters' : null,
    showTimeline ? `Timeline (${timelineBucket})` : null,
  ].filter(Boolean).join(' + ');
  const sourceLabel = [
    `Finder results (${scene.systems.length})`,
    regionLayer.data ? `Authoritative regions (${regionLayer.data.labels.length})` : null,
    showHeatmap && layers.heatmap.data ? 'Heatmap' : null,
    showClusters && layers.clusters.data ? 'Clusters' : null,
    showTimeline && layers.timeline.data ? 'Timeline' : null,
  ].filter(Boolean).join(' + ');

  useEffect(() => {
    const snapshot = (): LiveRouteMapSnapshot => ({
      renderer: 'r3f',
      routeFlagEnabled: true,
      surfaceKind: composition.surface.kind,
      finderSystemCount: scene.systems.length,
      finderResponseTruncated: scene.boundedResponse.truncated,
      heatmapCellCount: composition.overlays.heatmap?.cellCount ?? 0,
      heatmapSourceTruncated: composition.overlays.heatmap?.sourceTruncated ?? false,
      aggregateHullCount: composition.overlays.aggregateHulls?.hullCount ?? 0,
      timelinePointCount: composition.timeline?.pointCount ?? 0,
      estimatedOverlayBufferBytes: composition.estimatedOverlayBufferBytes,
      overlayBufferWithinBudget: composition.withinOverlayBufferBudget,
      regionGeometryExposed: regionLayer.data != null,
      regionGeometryVisible: showRegions && regionLayer.data != null,
      regionLabelCount: regionLayer.data?.labels.length ?? 0,
      regionBoundaryCount: regionLayer.data?.boundaries.length ?? 0,
      regionPositionBytes: (regionLayer.data?.boundaries.length ?? 0) * 6 * Float32Array.BYTES_PER_ELEMENT,
      heapBudgetBytes: LIVE_ROUTE_HEAP_BUDGET_BYTES,
    });
    window.__stage26eProductionMap = { snapshot, measureHeap: measureLiveRouteHeap };
    return () => { delete window.__stage26eProductionMap; };
  }, [composition, regionLayer.data, scene.boundedResponse.truncated, scene.systems.length, showRegions]);

  return (
    <section data-testid="stage26e-production-map" aria-label="Stage 26E production map candidate" className="space-y-4">
      <section className="premium-subpanel space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-cyan/35 bg-cyan/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            Stage 26E measured candidate
          </span>
          <span data-testid="stage26e-route-flag-state" className="rounded-full border border-gold/35 bg-gold/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-gold">
            Explicit route flag enabled
          </span>
        </div>
        <h2 className="font-display text-base tracking-[0.12em] text-text">Production-route R3F composition</h2>
        <p className="max-w-4xl text-sm leading-relaxed text-silver">
          This candidate consumes the current Finder result set, bounded authoritative region geometry, and live aggregate map responses. Normal production still selects the established renderer unless the exact Stage 26E flag is enabled.
        </p>
        <div className="flex flex-wrap gap-2">
          <button type="button" data-testid="map-return-to-finder" onClick={onReturnToFinder} className="btn-metal text-[11px] font-mono">
            Back to Finder
          </button>
          <button
            type="button"
            data-testid="map-open-selected-system"
            disabled={!selected || !onOpenSelectedSystem}
            onClick={() => selected && onOpenSelectedSystem?.(selected.id64)}
            className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[11px] text-orange disabled:cursor-not-allowed disabled:opacity-50"
          >
            Inspect selected system
          </button>
        </div>
      </section>

      <header className="panel flex flex-wrap items-center gap-3 px-5 py-3">
        <h2 className="font-display text-orange tracking-[0.14em] text-lg">Galactic Map</h2>
        <span className="font-mono text-xs text-silver-dk">{scene.systems.length} bounded Finder systems</span>
        <span className="flex-1" />
        <div role="group" aria-label="Map view mode" className="flex overflow-hidden rounded-chunk-sm border border-border">
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              data-testid={`map-view-${mode.id}`}
              aria-pressed={viewPreset === mode.id}
              onClick={() => selectViewPreset(mode.id)}
              className={viewPreset === mode.id ? 'bg-orange/20 px-2.5 py-1 font-mono text-[10px] text-orange' : 'px-2.5 py-1 font-mono text-[10px] text-silver-dk'}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <LayerToggle testId="stage26e-map-regions-toggle" label="Regions" checked={showRegions} onChange={setShowRegions} />
        <LayerToggle testId="stage26e-map-heatmap-toggle" label="Heatmap" checked={showHeatmap} onChange={setShowHeatmap} />
        <LayerToggle testId="stage26e-map-clusters-toggle" label="Clusters" checked={showClusters} onChange={setShowClusters} />
        <LayerToggle testId="stage26e-map-timeline-toggle" label="Timeline" checked={showTimeline} onChange={setShowTimeline} />
        {showTimeline && (
          <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk">
            Bucket
            <select value={timelineBucket} onChange={(event) => setTimelineBucket(event.target.value as typeof timelineBucket)} className="rounded border border-border bg-bg3 px-2 py-1">
              <option value="month">Month</option>
              <option value="quarter">Quarter</option>
              <option value="year">Year</option>
            </select>
          </label>
        )}
      </header>

      <MapLegend
        activeLayerSummary={activeLayerSummary}
        currentViewLabel={currentViewMode.label}
        currentViewDescription={currentViewMode.description}
      />
      <MapLayerStatusRow
        sourceLabel={sourceLabel}
        showRegions={showRegions}
        showHeatmap={showHeatmap}
        showClusters={showClusters}
        showTimeline={showTimeline}
        timelineBucket={timelineBucket}
        regionsLoading={regionLayer.isLoading}
        regionsError={regionLayer.isError}
        heatmapLoading={layers.heatmap.isLoading}
        heatmapError={layers.heatmap.isError}
        heatmapTruncated={layers.heatmap.data?.truncated ?? false}
        heatmapMaxCells={layers.heatmap.data?.max_cells ?? null}
        clustersLoading={layers.clusters.isLoading}
        clustersError={layers.clusters.isError}
        timelineLoading={layers.timeline.isLoading}
        timelineError={layers.timeline.isError}
      />
      {showTimeline && composition.timeline && (
        <TimelineSummary
          dataTestId="stage26e-map-timeline-summary"
          bucket={timelineBucket}
          total={composition.timeline.total}
          pointCount={composition.timeline.pointCount}
          latestDate={composition.timeline.latestDate}
        />
      )}
      {!composition.withinOverlayBufferBudget && (
        <p role="alert" className="font-mono text-xs text-red">Normalized overlay buffer budget exceeded.</p>
      )}
      {composition.surface.kind === 'error' && (
        <p role="alert" className="panel-thin px-4 py-3 font-mono text-xs text-red">{composition.surface.message}</p>
      )}
      {composition.surface.kind === 'empty' ? (
        <div className="panel-thin px-4 py-16 text-center text-sm text-silver-dk">{composition.surface.message}</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <MapErrorBoundary>
            <div ref={viewportRef} data-testid="stage26e-production-map-viewport" className="stage26e-production-map-viewport">
              <R3FMapFoundation
                scene={scene}
                regions={showRegions ? regionLayer.data ?? EMPTY_REGIONS : EMPTY_REGIONS}
                productionOverlays={composition.overlays}
                viewport={viewport}
                maxBackgroundPoints={PRODUCTION_PARITY_LIMITS.finderSystems}
                onInteraction={onInteraction}
              />
            </div>
          </MapErrorBoundary>
          <div className="space-y-3">
            <SelectionPanel system={selected} />
            {overlapCandidateIds.length > 0 && (
              <aside aria-label="Overlapping systems" className="panel-thin space-y-2 p-3">
                <h3 className="font-display text-xs text-orange">Choose overlapping system</h3>
                {overlapCandidateIds.map((id64) => (
                  <button key={id64} type="button" onClick={() => selectOverlapCandidate(id64)} className="block w-full rounded border border-border px-2 py-1 text-left font-mono text-xs text-silver">
                    {systems.find((system) => system.id64 === id64)?.name ?? id64}
                  </button>
                ))}
              </aside>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function LayerToggle({
  testId,
  label,
  checked,
  onChange,
}: {
  testId: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk">
      <input
        type="checkbox"
        data-testid={testId}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-orange"
      />
      {label}
    </label>
  );
}
