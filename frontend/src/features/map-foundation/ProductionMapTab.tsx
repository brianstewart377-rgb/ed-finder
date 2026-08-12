import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
import { useViewportSystems } from '@/features/map/viewportSystems';
import { useExplorationLayers } from '@/features/map/useExplorationLayers';
import { usePowerplayLayer } from '@/features/map/usePowerplayLayer';
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
} from './camera';
import { useSmoothMapZoom } from './useSmoothMapZoom';
import { api } from '@/lib/api';
import type { CommanderPowerplayResponse, ExplorationSystemSummaryResponse, MapViewportSystem } from '@/lib/api';
import type { RouteDetail, RouteSummary, SystemResult } from '@/types/api';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import { useSelectedRouteStore } from '@/store/selectedRouteStore';
import { RouteDetailPanel } from './RouteDetailPanel';
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
  const [viewPreset, setViewPreset] = useState<MapViewPreset>('galaxy');
  const [showRegions, setShowRegions] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showClusters, setShowClusters] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [showVisitedSystems, setShowVisitedSystems] = useState(true);
  const [showTravelTrail, setShowTravelTrail] = useState(false);
  const [showCompleteness, setShowCompleteness] = useState(false);
  const [showPowerplay, setShowPowerplay] = useState(false);
  const [timelineBucket, setTimelineBucket] = useState<'month' | 'quarter' | 'year'>('month');
  const [overlapCandidateIds, setOverlapCandidateIds] = useState<number[]>([]);
  const [routes, setRoutes] = useState<RouteSummary[]>([]);
  const [routeDetail, setRouteDetail] = useState<RouteDetail | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [viewportSelection, setViewportSelection] = useState<SystemResult | null>(null);
  const syncKey = useSyncKeyStore((state) => state.syncKey);
  const selectedRouteId = useSelectedRouteStore((state) => state.selectedRouteId);
  const selectRoute = useSelectedRouteStore((state) => state.selectRoute);
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
    const preset = boundedSystems.length > 0 ? 'results' : 'galaxy';
    setScene(applyViewPreset(handoff.scene, preset, referenceCoords, DEFAULT_VIEWPORT));
    setViewPreset(preset);
  }, [boundedSystems, initialSelectedSystemId, referenceCoords, systems.length]);

  useEffect(() => {
    let active = true;
    void api.listRoutes(syncKey)
      .then((response) => {
        if (!active) return;
        setRoutes(response.routes);
        const persisted = useSelectedRouteStore.getState().selectedRouteId;
        if (persisted && !response.routes.some((route) => route.route_id === persisted)) {
          selectRoute(response.routes[0]?.route_id ?? null);
        } else if (!persisted && response.routes.length > 0) {
          selectRoute(response.routes[0]!.route_id);
        }
      })
      .catch((error: unknown) => {
        if (active) setRouteError(error instanceof Error ? error.message : 'Route list could not be loaded.');
      });
    return () => { active = false; };
  }, [selectRoute, syncKey]);

  useEffect(() => {
    let active = true;
    if (!selectedRouteId) {
      setRouteDetail(null);
      setRouteError(null);
      setRouteLoading(false);
      return () => { active = false; };
    }
    setRouteLoading(true);
    setRouteError(null);
    void api.getRoute(selectedRouteId, syncKey)
      .then((detail) => {
        if (active) setRouteDetail(detail);
      })
      .catch((error: unknown) => {
        if (active) {
          setRouteDetail(null);
          setRouteError(error instanceof Error ? error.message : 'Route detail could not be loaded.');
        }
      })
      .finally(() => {
        if (active) setRouteLoading(false);
      });
    return () => { active = false; };
  }, [selectedRouteId, syncKey]);

  useEffect(() => {
    const finderIds = new Set(boundedSystems.map((system) => system.id64));
    const routeRecords = (routeDetail?.waypoints ?? [])
      .filter((waypoint) => waypoint.x != null && waypoint.y != null && waypoint.z != null)
      .map((waypoint, index) => ({
        id64: Number(waypoint.system_id64 ?? -(index + 1)),
        name: waypoint.system_name,
        coords: { x: waypoint.x!, y: waypoint.y!, z: waypoint.z! },
        developmentScore: null,
        primaryEconomy: null,
        population: null,
      }));
    const uniqueRouteRecords = [...new Map(routeRecords.map((record) => [record.id64, record])).values()];
    const routeIds = uniqueRouteRecords.map((record) => record.id64);
    const routeColor = routeDetail?.type === 'personal'
      ? '#74d8ff'
      : routeDetail?.type === 'expedition'
        ? '#d8a5ff'
        : routeDetail?.type === 'spansh'
          ? '#8ff0a4'
          : '#ffae62';
    setScene((current) => {
      const finderRecords = current.systems.filter((system) => finderIds.has(system.id64));
      const existingIds = new Set(finderRecords.map((system) => system.id64));
      const combined = [...finderRecords, ...uniqueRouteRecords.filter((record) => !existingIds.has(record.id64))];
      return {
        ...current,
        systems: combined,
        routes: routeDetail ? [{
          id: routeDetail.route_id,
          waypoints: uniqueRouteRecords.map((record) => ({ systemId64: record.id64, label: record.name })),
          color: routeColor,
          currentWaypointIndex: routeDetail.current_waypoint_index,
        }] : [],
        guaranteedSystemIds: [...new Set([
          ...current.guaranteedSystemIds.filter((id64) => finderIds.has(id64)),
          ...routeIds,
        ])],
        layers: current.layers.map((layer) => layer.type === 'routes'
          ? { ...layer, visible: routeDetail != null }
          : layer),
      };
    });
  }, [boundedSystems, routeDetail]);

  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const updateViewport = (width: number, height: number) => {
      if (width > 0 && height > 0) {
        const nextWidth = Math.round(width);
        const nextHeight = Math.round(height);
        setViewport((current) => current.width === nextWidth && current.height === nextHeight
          ? current
          : { width: nextWidth, height: nextHeight });
      }
    };
    const initialRect = element.getBoundingClientRect();
    updateViewport(initialRect.width, initialRect.height);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) updateViewport(entry.contentRect.width, entry.contentRect.height);
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
  // Feature #6 detail lane: fetch individual systems for the viewport when
  // zoomed in (null when zoomed out -> the aggregate heatmap carries the view).
  const viewportSystems = useViewportSystems({ camera: scene.camera, viewport });
  const exploration = useExplorationLayers({
    syncKey,
    camera: scene.camera,
    viewport,
    visitsEnabled: showVisitedSystems || showCompleteness,
    trailEnabled: showTravelTrail,
    summarySystemId64: scene.selectedSystemId64,
  });
  const powerplay = usePowerplayLayer(syncKey, showPowerplay);
  const regionLabelSafeArea = useMemo(() => ({
    // The map canvas fills the viewport, while the production navigation,
    // mode controls, and legal footer float above it. Keep labels inside the
    // unobscured interaction area rather than merely inside the canvas box.
    top: Math.min(240, viewport.height * 0.42),
    bottom: Math.min(90, viewport.height * 0.12),
  }), [viewport.height]);
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
  const applyAnimatedCamera = useCallback((camera: MapSceneState['camera']) => {
    setScene((current) => ({
      ...current,
      cameraIntent: 'user',
      camera,
    }));
  }, []);
  const {
    requestDelta: requestZoomDelta,
    cancel: cancelZoom,
  } = useSmoothMapZoom({
    camera: scene.camera,
    onCameraChange: applyAnimatedCamera,
  });

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
    if (event.type === 'cameraChanged') {
      cancelZoom();
    }
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
  }, [cancelZoom]);

  const selectOverlapCandidate = useCallback((systemId64: number) => {
    setScene((current) => reduceScene(current, { type: 'selectSystem', systemId64 }));
    setOverlapCandidateIds([]);
  }, []);

  const selectViewPreset = useCallback((preset: MapViewPreset) => {
    cancelZoom();
    setViewPreset(preset);
    setScene((current) => applyViewPreset(
      current,
      preset,
      referenceCoords,
      viewport,
      galaxyBounds,
    ));
  }, [cancelZoom, galaxyBounds, referenceCoords, viewport]);

  const snapTopDown = useCallback(() => {
    cancelZoom();
    setScene((current) => ({
      ...current,
      cameraIntent: 'user',
      camera: snapCameraTopDown(current.camera),
    }));
  }, [cancelZoom]);
  const stepZoom = useCallback((deltaY: number) => {
    requestZoomDelta(deltaY);
  }, [requestZoomDelta]);

  const selectViewportSystem = useCallback((system: MapViewportSystem) => {
    const result = {
      id64: system.id64,
      name: system.name,
      coords: { x: system.x, y: system.y, z: system.z },
      population: system.populated ? 1 : 0,
      galaxy_region_id: system.galaxy_region_id,
      distance: null,
    } as unknown as SystemResult;
    setViewportSelection(result);
    setScene((current) => ({
      ...reduceScene(current, { type: 'selectSystem', systemId64: system.id64 }),
      systems: current.systems.some((candidate) => candidate.id64 === system.id64)
        ? current.systems
        : [...current.systems, {
            id64: system.id64,
            name: system.name,
            coords: { x: system.x, y: system.y, z: system.z },
            developmentScore: null,
            primaryEconomy: null,
            population: system.populated ? 1 : 0,
          }],
    }));
    setOverlapCandidateIds([]);
  }, []);

  const selected = systems.find((system) => system.id64 === scene.selectedSystemId64)
    ?? (viewportSelection?.id64 === scene.selectedSystemId64 ? viewportSelection : null);
  const currentViewMode = VIEW_MODES.find((mode) => mode.id === viewPreset) ?? VIEW_MODES[0];
  const activeLayerSummary = [
    'Finder dots',
    showRegions ? 'Regions' : null,
    showHeatmap ? 'Heatmap' : null,
    showClusters ? 'Clusters' : null,
    showTimeline ? `Timeline (${timelineBucket})` : null,
    showVisitedSystems ? 'Visited Systems' : null,
    showTravelTrail ? 'Travel Trail' : null,
    showCompleteness ? 'Scanned/Mapped Completeness' : null,
    showPowerplay ? 'Powerplay strategy' : null,
    routeDetail ? `Route (${routeDetail.name})` : null,
  ].filter(Boolean).join(' + ');
  const sourceLabel = [
    `Finder results (${scene.systems.length})`,
    regionLayer.data ? `Authoritative regions (${regionLayer.data.labels.length})` : null,
    showHeatmap && layers.heatmap.data ? 'Heatmap' : null,
    showClusters && layers.clusters.data ? 'Clusters' : null,
    showTimeline && layers.timeline.data ? 'Timeline' : null,
    (showVisitedSystems || showCompleteness) && exploration.viewportVisits.data
      ? `Personal visits (${exploration.viewportVisits.data.count})`
      : null,
    exploration.facts.data ? `Exploration facts (${exploration.facts.data.total_count})` : null,
    showTravelTrail && exploration.trail.data ? `Travel trail (${exploration.trail.data.count})` : null,
    showPowerplay && powerplay.systems.data ? `Personal PP2 observations (${powerplay.systems.data.count})` : null,
    routeDetail ? `${routeDetail.source} route` : null,
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
    <section data-testid="stage26e-production-map" aria-label="ED-Finder galaxy map" className="map-workspace map-workspace--immersive">
      <div className="map-workspace__top-hud">
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
              <LayerToggle testId="map-visited-systems-toggle" label="Visited Systems" checked={showVisitedSystems} onChange={setShowVisitedSystems} />
              <LayerToggle testId="map-travel-trail-toggle" label="Travel Trail" checked={showTravelTrail} onChange={setShowTravelTrail} />
              <LayerToggle testId="map-completeness-toggle" label="Scanned/Mapped Completeness" checked={showCompleteness} onChange={setShowCompleteness} />
              <LayerToggle testId="map-powerplay-toggle" label="Powerplay strategy" checked={showPowerplay} onChange={setShowPowerplay} />
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
      </div>
      <div className="map-workspace__status-overlays">
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
      {(exploration.viewportVisits.isError || exploration.trail.isError) && (
        <p role="alert" className="panel-thin px-4 py-3 font-mono text-xs text-red">
          Personal exploration layers could not be loaded.
        </p>
      )}
      {showPowerplay && (powerplay.systems.isError || powerplay.commander.isError) && (
        <p role="alert" className="panel-thin px-4 py-3 font-mono text-xs text-red">
          Personal Powerplay observations could not be loaded.
        </p>
      )}
      </div>
      <div className="map-workspace__map-frame">
          <MapErrorBoundary>
            <div ref={viewportRef} data-testid="stage26e-production-map-viewport" className="stage26e-production-map-viewport">
              <R3FMapFoundation
                scene={scene}
                regions={showRegions ? regionLayer.data ?? EMPTY_REGIONS : EMPTY_REGIONS}
                productionOverlays={{
                  ...composition.overlays,
                  realStars: viewportSystems.systems,
                  realStarsTruncated: viewportSystems.truncated,
                  explorationVisits: showVisitedSystems || showCompleteness
                    ? exploration.viewportVisits.data?.visits ?? null
                    : null,
                  explorationTrail: showTravelTrail
                    ? exploration.trail.data?.points ?? null
                    : null,
                  showExplorationCompleteness: showCompleteness,
                  powerplay: showPowerplay ? powerplay.systems.data?.systems ?? null : null,
                }}
                viewport={viewport}
                viewPreset={viewPreset}
                reference={reference}
                galaxyBounds={galaxyBounds}
                labelSafeArea={regionLabelSafeArea}
                maxBackgroundPoints={PRODUCTION_PARITY_LIMITS.finderSystems}
                onInteraction={onInteraction}
                onZoomIntent={requestZoomDelta}
                onViewportSystemSelect={selectViewportSystem}
              />
            </div>
          </MapErrorBoundary>
          {composition.surface.kind === 'empty' && viewPreset === 'results' && (
            <div className="map-workspace__empty">
              <strong>No systems to map yet</strong>
              <span>Run a Finder search, or choose Whole galaxy to explore the region chart.</span>
            </div>
          )}
          {(selected || overlapCandidateIds.length > 0) && (
            <div className="map-workspace__selection">
              {selected && <SelectionPanel system={selected} />}
              {selected && exploration.summary.data && (
                <ExplorationSummaryPanel summary={exploration.summary.data} />
              )}
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
          <RouteDetailPanel
            routes={routes}
            selectedRouteId={selectedRouteId}
            detail={routeDetail}
            loading={routeLoading}
            error={routeError}
            onSelect={selectRoute}
          />
          {showPowerplay && (
            <PowerplayCommanderPanel
              commander={powerplay.commander.data ?? null}
              systemCount={powerplay.systems.data?.count ?? 0}
              loading={powerplay.commander.isLoading || powerplay.systems.isLoading}
            />
          )}
      </div>
    </section>
  );
}

function PowerplayCommanderPanel({
  commander,
  systemCount,
  loading,
}: {
  commander: CommanderPowerplayResponse | null;
  systemCount: number;
  loading: boolean;
}) {
  return (
    <aside data-testid="map-powerplay-sidebar" className="map-workspace__powerplay-sidebar panel-thin">
      <h3>Powerplay 2.0</h3>
      {loading ? <p>Loading personal observations...</p> : <>
        <dl>
          <div><dt>Pledge</dt><dd>{String(commander?.pledge ?? 'Unpledged')}</dd></div>
          <div><dt>Rank</dt><dd>{String(commander?.rank ?? 'Unknown')}</dd></div>
          <div><dt>Total merits</dt><dd>{String(commander?.merits ?? 'Unknown')}</dd></div>
          <div><dt>This cycle</dt><dd>{String(commander?.cycle_merits_earned ?? 0)} earned</dd></div>
          <div><dt>Observed control</dt><dd>{systemCount} systems</dd></div>
        </dl>
        <p className="map-workspace__powerplay-note">
          Journal observations only. Colour is power, marker size is control tier, and dimming indicates age or uncertainty.
        </p>
      </>}
    </aside>
  );
}

function ExplorationSummaryPanel({ summary }: { summary: ExplorationSystemSummaryResponse }) {
  return (
    <aside data-testid="map-exploration-summary" className="panel-thin space-y-2 p-3 font-mono text-[11px] text-silver">
      <h3 className="font-display text-xs tracking-wider text-cyan">Personal exploration</h3>
      <div>{summary.visits.visit_count} visit{summary.visits.visit_count === 1 ? '' : 's'}</div>
      <div>
        FSS {summary.bodies.scanned}/{summary.bodies.expected ?? summary.bodies.observed}
        {' · '}DSS {summary.bodies.mapped}/{summary.bodies.observed}
      </div>
      <div>
        Organics {summary.organics.analysed}/{summary.organics.organisms} analysed
        {' · '}{summary.organics.sold} sold
      </div>
      <div>Codex {summary.codex.observed} observed · {summary.codex.sold} sold</div>
    </aside>
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
