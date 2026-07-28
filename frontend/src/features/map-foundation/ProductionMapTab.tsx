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
import {
  DEFAULT_CAMERA_PITCH_DEG,
  snapCameraTopDown,
  zoomCamera,
} from './camera';
import './ProductionMapTab.css';

const EMPTY_REGIONS: RegionLayerData = { labels: [], boundaries: [] };
const DEFAULT_VIEWPORT: ViewportSize = { width: 1280, height: 720 };

function emptyProductionScene(reference: { x: number; z: number }): MapSceneState {
  return {
    sceneRevision: 1,
    oneTimeFitIntent: null,
    cameraIntent: 'user',
    camera: {
      center: { ...reference },
      zoom: 64,
      pitchDeg: DEFAULT_CAMERA_PITCH_DEG,
      bearingDeg: 0,
    },
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
    setScene(applyViewPreset(handoff.scene, 'results', referenceCoords, DEFAULT_VIEWPORT));
    setViewPreset('results');
  }, [boundedSystems, initialSelectedSystemId, referenceCoords, systems.length]);

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
  }, [scene.systems.length, viewPreset]);

  const layers = useMapLayers({
    heatmap: { enabled: showHeatmap, max_cells: PRODUCTION_PARITY_LIMITS.heatmapCells },
    clusters: { enabled: showClusters, max_hulls: PRODUCTION_PARITY_LIMITS.aggregateHulls },
    timeline: { enabled: showTimeline, bucket: timelineBucket },
  });
  const regionLayer = useAuthoritativeRegionLayer();
  const galaxyBounds = useMemo(() => {
    const boundaries = regionLayer.data?.boundaries;
    if (!boundaries?.length) return undefined;
    let minX = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let minZ = Number.POSITIVE_INFINITY;
    let maxZ = Number.NEGATIVE_INFINITY;
    boundaries.forEach(({ source, target }) => {
      minX = Math.min(minX, source[0], target[0]);
      maxX = Math.max(maxX, source[0], target[0]);
      minZ = Math.min(minZ, source[1], target[1]);
      maxZ = Math.max(maxZ, source[1], target[1]);
    });
    return { minX, maxX, minZ, maxZ };
  }, [regionLayer.data]);
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

  useEffect(() => {
    setScene((current) => current.cameraIntent === 'user'
      ? current
      : applyViewPreset(
        current,
        viewPreset,
        referenceCoords,
        viewport,
        galaxyBounds,
      ));
  }, [galaxyBounds, referenceCoords, viewPreset, viewport]);

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
    setScene((current) => applyViewPreset(
      current,
      preset,
      referenceCoords,
      viewport,
      galaxyBounds,
    ));
  }, [galaxyBounds, referenceCoords, viewport]);

  const snapTopDown = useCallback(() => {
    setScene((current) => ({
      ...current,
      cameraIntent: 'user',
      camera: snapCameraTopDown(current.camera),
    }));
  }, []);
  const stepZoom = useCallback((deltaY: number) => {
    setScene((current) => ({
      ...current,
      cameraIntent: 'user',
      camera: zoomCamera(current.camera, deltaY, viewport, galaxyBounds),
    }));
  }, [galaxyBounds, viewport]);

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
    <section data-testid="stage26e-production-map" aria-label="ED-Finder galaxy map" className="map-workspace panel">
      <header className="map-workspace__header">
        <div className="map-workspace__title">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-orange tracking-[0.12em] text-xl">Galactic Map</h2>
            <span data-testid="stage26e-route-flag-state" className="rounded-full border border-orange/30 bg-orange/8 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange-lt">
              Live map
            </span>
            <span className="font-mono text-xs text-silver-dk">{scene.systems.length} Finder systems shown</span>
          </div>
          <p className="mt-1 text-sm text-silver">
            Plot Finder results and explore their position in the galaxy.
          </p>
        </div>
        <div className="map-workspace__actions">
          <button type="button" data-testid="map-return-to-finder" onClick={onReturnToFinder}>
            Back to Finder
          </button>
          <button
            type="button"
            data-testid="map-open-selected-system"
            disabled={!selected || !onOpenSelectedSystem}
            onClick={() => selected && onOpenSelectedSystem?.(selected.id64)}
            data-accent="true"
          >
            Inspect selected system
          </button>
        </div>
      </header>
      <div className="map-workspace__controls">
        <div role="group" aria-label="Map view mode" className="map-workspace__segmented">
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              data-testid={`map-view-${mode.id}`}
              aria-pressed={viewPreset === mode.id}
              title={mode.description}
              onClick={() => selectViewPreset(mode.id)}
              className={viewPreset === mode.id ? 'is-active' : ''}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <div role="group" aria-label="Camera controls" className="map-workspace__segmented">
          <button
            type="button"
            data-testid="map-snap-top-down"
            title="Snap to a precise overhead view without changing your position or zoom"
            onClick={snapTopDown}
          >
            Top-down view
          </button>
        </div>
        <div role="group" aria-label="Zoom controls" className="map-workspace__zoom-controls">
          <button
            type="button"
            data-testid="map-zoom-out"
            aria-label="Zoom out"
            title="Zoom out"
            onClick={() => stepZoom(220)}
          >
            −
          </button>
          <output aria-live="polite" aria-label="Map zoom">
            {scene.camera.zoom < 1
              ? scene.camera.zoom.toFixed(2)
              : Math.round(scene.camera.zoom).toLocaleString()} LY/px
          </output>
          <button
            type="button"
            data-testid="map-zoom-in"
            aria-label="Zoom in"
            title="Zoom in"
            onClick={() => stepZoom(-220)}
          >
            +
          </button>
        </div>
        <details className="map-workspace__layers">
          <summary>Layers &amp; legend</summary>
          <div className="map-workspace__layers-content">
            <div className="map-workspace__layer-toggles">
              <LayerToggle testId="stage26e-map-regions-toggle" label="Regions" checked={showRegions} onChange={setShowRegions} />
              <LayerToggle testId="stage26e-map-heatmap-toggle" label="Heatmap" checked={showHeatmap} onChange={setShowHeatmap} />
              <LayerToggle testId="stage26e-map-clusters-toggle" label="Clusters" checked={showClusters} onChange={setShowClusters} />
              <LayerToggle testId="stage26e-map-timeline-toggle" label="Timeline" checked={showTimeline} onChange={setShowTimeline} />
              {showTimeline && (
                <label className="flex items-center gap-2 font-mono text-[10px] text-silver-dk">
                  Time range
                  <select value={timelineBucket} onChange={(event) => setTimelineBucket(event.target.value as typeof timelineBucket)} className="rounded border border-border bg-bg3 px-2 py-1">
                    <option value="month">Month</option>
                    <option value="quarter">Quarter</option>
                    <option value="year">Year</option>
                  </select>
                </label>
              )}
            </div>
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
          </div>
        </details>
      </div>
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
      {composition.surface.kind === 'empty' && viewPreset === 'results' ? (
        <div className="map-workspace__empty">
          <strong>No systems to map yet</strong>
          <span>Run a Finder search, or choose Whole galaxy to explore the region chart.</span>
        </div>
      ) : (
        <div className="map-workspace__map-frame">
          <MapErrorBoundary>
            <div ref={viewportRef} data-testid="stage26e-production-map-viewport" className="stage26e-production-map-viewport">
              <R3FMapFoundation
                scene={scene}
                regions={showRegions ? regionLayer.data ?? EMPTY_REGIONS : EMPTY_REGIONS}
                productionOverlays={composition.overlays}
                viewport={viewport}
                viewPreset={viewPreset}
                reference={reference}
                galaxyBounds={galaxyBounds}
                maxBackgroundPoints={PRODUCTION_PARITY_LIMITS.finderSystems}
                onInteraction={onInteraction}
              />
            </div>
          </MapErrorBoundary>
          {(selected || overlapCandidateIds.length > 0) && (
            <div className="map-workspace__selection">
              {selected && <SelectionPanel system={selected} />}
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
          )}
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
