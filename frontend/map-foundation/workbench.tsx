import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DatasetSize } from '../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import type { ClusterResult } from '../src/features/cluster-search/useClusterSearch';
import {
  initOverlapCycling,
  reduceScene,
  type MapInteractionEvent,
  type MapSceneState,
} from '../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { R3FMapFoundation } from '../src/features/map-foundation/R3FMapFoundation';
import { createFoundationDemoScene } from '../src/features/map-foundation/demo-scene';
import { applyFeatureHandoff, resolveMapInteraction } from '../src/features/map-foundation/feature-handoffs';
import { measureFoundationPerformance } from '../src/features/map-foundation/performance';
import {
  applyViewPreset,
  composeProductionParity,
  type MapViewPreset,
} from '../src/features/map-foundation/production-parity';
import type { MapClusterHull, MapHeatmapResponse, MapTimelineResponse } from '../src/lib/api';
import type { EvidenceSystemSummaryResponse, SystemDetail, SystemResult } from '../src/types/api';
import type {
  FoundationSnapshot,
  RegionLayerData,
  VisibilityMetadata,
  ViewportSize,
} from '../src/features/map-foundation/types';
import { clusterAnchorIdForSystem, highlightedSystemIds } from '../src/features/map-foundation/visibility';

const EMPTY_REGIONS: RegionLayerData = { labels: [], boundaries: [] };
const DEFAULT_VIEWPORT: ViewportSize = { width: 1280, height: 720 };
const EMPTY_VISIBILITY: VisibilityMetadata = {
  totalInViewBackground: 0,
  returnedBackground: 0,
  aggregateRemainder: 0,
  truncated: false,
  guaranteedCount: 0,
};
type HandoffScenario = 'finder' | 'compare' | 'savedSystems' | 'evidenceMap' | 'systemDetail' | 'clusterSearch' | 'planner';

const PRODUCTION_HEATMAP_FIXTURE: MapHeatmapResponse = {
  voxel_size: 2_000,
  voxel_bucket: 1_000,
  economy: null,
  count: 16,
  max_cells: 50_000,
  truncated: false,
  cells: Array.from({ length: 16 }, (_, index) => ({
    cx: (index % 4 - 1.5) * 8_000,
    cy: 0,
    cz: (Math.floor(index / 4) - 1.5) * 8_000,
    n: 5 + index,
    avg_score: 25 + index * 4,
    max_score: 90,
  })),
};

const PRODUCTION_HULL_FIXTURE: MapClusterHull[] = Array.from({ length: 3 }, (_, index) => ({
  anchor_id64: 900_000_000 + index,
  anchor_name: `Aggregate ${index + 1}`,
  x: (index - 1) * 12_000,
  y: 0,
  z: (index % 2 === 0 ? -1 : 1) * 10_000,
  radius_ly: 3_000 + index * 500,
  system_count: 8 + index,
  top_economy: null,
  top_score: 70 + index * 5,
}));

const PRODUCTION_TIMELINE_FIXTURE: MapTimelineResponse = {
  bucket: 'month',
  total: 42,
  points: [
    { date: '2026-05-01', count: 10 },
    { date: '2026-06-01', count: 14 },
    { date: '2026-07-01', count: 18 },
  ],
};

function systemResult(system: MapSceneState['systems'][number]): SystemResult {
  return {
    id64: system.id64, name: system.name, coords: { x: system.coords.x, y: 0, z: system.coords.z },
    population: system.population, primaryEconomy: system.primaryEconomy,
    overall_development_potential: system.developmentScore,
  };
}

function evidenceSummary(systemId64: number): EvidenceSystemSummaryResponse {
  return {
    schema_version: 'evidence_store/v1', system_id64: systemId64,
    observed_fact_count: 1, imported_record_count: 0, derived_feature_count: 0, open_rule_proposal_count: 0,
    focus_areas: [], records: [], derived_features: [], open_rule_proposals: [],
  };
}

export function MapFoundationWorkbench() {
  const [datasetSize, setDatasetSize] = useState<DatasetSize>(500_000);
  const [scene, setScene] = useState<MapSceneState>(() => createFoundationDemoScene(datasetSize));
  const [regions, setRegions] = useState<RegionLayerData>(EMPTY_REGIONS);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const [ready, setReady] = useState(false);
  const [overlapCandidateIds, setOverlapCandidateIds] = useState<number[]>([]);
  const [contextState, setContextState] = useState<FoundationSnapshot['contextState']>('ready');
  const [lastInteraction, setLastInteraction] = useState<MapInteractionEvent | null>(null);
  const [lastHostCommand, setLastHostCommand] = useState('none');
  const [omittedHandoffSystemIds, setOmittedHandoffSystemIds] = useState<number[]>([]);
  const [visibility, setVisibility] = useState<VisibilityMetadata>(EMPTY_VISIBILITY);
  const [viewPreset, setViewPreset] = useState<MapViewPreset>('results');
  const viewportRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const contextStateRef = useRef(contextState);
  contextStateRef.current = contextState;

  useEffect(() => {
    fetch('/__stage26c/regions').then((response) => {
      if (!response.ok) throw new Error(`Region layer request failed: ${response.status}`);
      return response.json() as Promise<RegionLayerData>;
    }).then(setRegions);
  }, []);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setViewport({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const onInteraction = useCallback((event: MapInteractionEvent) => {
    setLastInteraction(event);
    setLastHostCommand(resolveMapInteraction(sceneRef.current, event).command.type);
    if (contextStateRef.current === 'restored' && (
      event.type === 'selectSystem' || event.type === 'overlapChoiceRequired'
    )) {
      setContextState('usable');
    }
    switch (event.type) {
      case 'cameraChanged':
        setScene((current) => ({ ...current, camera: event.camera, cameraIntent: 'user' }));
        break;
      case 'selectSystem':
        setScene((current) => reduceScene(current, { type: 'selectSystem', systemId64: event.systemId64 }));
        setOverlapCandidateIds([]);
        break;
      case 'deselectSystem':
        setScene((current) => ({ ...current, selectedSystemId64: null }));
        setOverlapCandidateIds([]);
        break;
      case 'overlapChoiceRequired':
        setOverlapCandidateIds(event.candidateSystemIds);
        setScene((current) => ({
          ...current,
          keyboardCompanion: {
            phase: initOverlapCycling(event.candidateSystemIds.map((systemId64) => ({ systemId64, distancePx: 0 }))),
          },
        }));
        break;
      case 'overlapChoice':
        setScene((current) => reduceScene(current, { type: 'selectSystem', systemId64: event.systemId64 }));
        setOverlapCandidateIds([]);
        break;
      case 'layerChanged':
        setScene((current) => ({ ...current, layers: event.layers }));
        break;
      case 'contextStateChanged':
        setContextState(event.state);
        break;
      default:
        break;
    }
  }, []);

  const applyScenario = (scenario: HandoffScenario) => {
    setScene((current) => {
      const [anchor, memberA, memberB, compareLeft, compareRight] = current.systems;
      if (!anchor || !memberA || !memberB || !compareLeft || !compareRight) return current;
      const systems = [anchor, memberA, memberB, compareLeft, compareRight].map(systemResult);
      let result;
      switch (scenario) {
        case 'finder':
          result = applyFeatureHandoff(current, {
            type: 'finder', systems, selectedSystemId64: anchor.id64,
            metadata: { count: systems.length, truncated: false, continuationToken: null },
          });
          break;
        case 'compare':
          result = applyFeatureHandoff(current, {
            type: 'compare', systems: [systems[3]!, systems[4]!],
            leftId64: compareLeft.id64, rightId64: compareRight.id64,
          });
          break;
        case 'savedSystems':
          result = applyFeatureHandoff(current, { type: 'savedSystems', systems: [
            { id64: anchor.id64, name: anchor.name, x: anchor.coords.x, y: 0, z: anchor.coords.z,
              population: anchor.population, is_colonised: false, economy: anchor.primaryEconomy,
              pinned_at: '2026-07-22T00:00:00Z' },
            { system_id64: memberA.id64, name: memberA.name, x: memberA.coords.x, y: 0, z: memberA.coords.z,
              population: memberA.population, is_colonised: false, added_at: '2026-07-22T00:00:00Z' },
          ] });
          break;
        case 'evidenceMap':
          result = applyFeatureHandoff(current, { type: 'evidenceMap', entries: [
            { system: systems[1]!, summary: evidenceSummary(memberA.id64) },
            { system: systems[2]!, summary: evidenceSummary(memberB.id64) },
          ] });
          break;
        case 'systemDetail': {
          const system: SystemDetail = {
            id64: anchor.id64, name: anchor.name, x: anchor.coords.x, y: 0, z: anchor.coords.z,
            population: anchor.population, primary_economy: anchor.primaryEconomy,
          };
          result = applyFeatureHandoff(current, { type: 'systemDetail', system });
          break;
        }
        case 'clusterSearch': {
          const cluster: ClusterResult = {
            anchor_id64: anchor.id64, anchor_name: anchor.name,
            anchor_coords: { x: anchor.coords.x, y: 0, z: anchor.coords.z }, galaxy_region: 'Inner Orion Spur',
            coverage_score: 80, economy_diversity: 2, total_viable: 3,
            agriculture_count: 0, agriculture_best: 0, refinery_count: 1, refinery_best: 80,
            industrial_count: 1, industrial_best: 70, hightech_count: 0, hightech_best: 0,
            military_count: 0, military_best: 0, tourism_count: 0, tourism_best: 0,
            distance_ly: 0, cluster_radius_ly: 1_800,
            slots: [{ slot_index: 0, label: 'Members', economies: ['Industrial'], matches: [
              { system_id64: memberA.id64, system_name: memberA.name, scores: {}, distance_from_anchor_ly: 10 },
              { system_id64: memberB.id64, system_name: memberB.name, scores: {}, distance_from_anchor_ly: 20 },
            ] }],
          };
          result = applyFeatureHandoff(current, {
            type: 'clusterSearch', cluster,
            systemsById: new Map(systems.map((system) => [system.id64, system])),
          });
          break;
        }
        case 'planner':
          result = applyFeatureHandoff(current, {
            type: 'planner', systems, highlights: current.highlights, layers: current.layers,
            clusters: current.clusters, workflowPayload: { mode: 'map', readOnly: true },
          });
          break;
      }
      setOmittedHandoffSystemIds(result.omittedSystemIds);
      return result.scene;
    });
  };

  const highlightIds = useMemo(() => highlightedSystemIds(scene.highlights), [scene.highlights]);
  const systemsById = useMemo(() => new Map(scene.systems.map((system) => [system.id64, system])), [scene.systems]);
  const regionVisible = scene.layers.find((layer) => layer.type === 'regions')?.visible ?? false;
  const productionParity = useMemo(() => composeProductionParity({
    systemCount: Math.min(scene.systems.length, 500),
    heatmap: PRODUCTION_HEATMAP_FIXTURE,
    hulls: PRODUCTION_HULL_FIXTURE,
    timeline: PRODUCTION_TIMELINE_FIXTURE,
    timelineBucket: 'month',
  }), [scene.systems.length]);

  const snapshot = useCallback((): FoundationSnapshot => ({
    ready,
    datasetSize,
    camera: scene.camera,
    selectedSystemId64: scene.selectedSystemId64,
    regionLabelCount: regions.labels.length,
    regionBoundaryCount: regions.boundaries.length,
    visible: visibility,
    highlightCount: highlightIds.size,
    clusterCount: scene.clusters.length,
    overlapCandidateIds,
    contextState,
    lastInteraction,
    returnWorkflowType: scene.returnWorkflow?.type ?? null,
    lastHostCommand,
    omittedHandoffSystemIds,
    productionHeatmapCellCount: productionParity.overlays.heatmap?.cellCount ?? 0,
    productionAggregateHullCount: productionParity.overlays.aggregateHulls?.hullCount ?? 0,
    productionTimelinePointCount: productionParity.timeline?.pointCount ?? 0,
    productionViewPreset: viewPreset,
    productionSurfaceKind: productionParity.surface.kind,
    estimatedOverlayBufferBytes: productionParity.estimatedOverlayBufferBytes,
  }), [contextState, datasetSize, highlightIds.size, lastHostCommand, lastInteraction, omittedHandoffSystemIds, overlapCandidateIds, productionParity, ready, regions, scene, viewPreset, visibility]);

  useEffect(() => {
    window.__stage26cFoundation = {
      snapshot,
      loseContext: () => {
        const canvas = viewportRef.current?.querySelector('canvas');
        const gl = canvas?.getContext('webgl2') ?? canvas?.getContext('webgl');
        const extension = gl?.getExtension('WEBGL_lose_context');
        if (!extension) return false;
        extension.loseContext();
        window.setTimeout(() => extension.restoreContext(), 100);
        return true;
      },
      measurePerformance: async () => {
        const canvas = viewportRef.current?.querySelector('canvas');
        if (!canvas) throw new Error('Map foundation canvas is unavailable');
        const measurement = await measureFoundationPerformance(canvas);
        setScene((current) => ({ ...current, camera: { ...current.camera } }));
        return measurement;
      },
    };
    return () => { delete window.__stage26cFoundation; };
  }, [snapshot]);

  const chooseOverlap = (systemId64: number) => onInteraction({
    type: 'overlapChoice',
    systemId64,
    candidateSystemIds: overlapCandidateIds,
    clusterAnchorId64: clusterAnchorIdForSystem(scene, systemId64),
  });

  return <main className="foundation-shell">
    <header className="foundation-header">
      <div>
        <p className="eyebrow">Development-only · Stage 26D</p>
        <h1>Typed feature hand-offs</h1>
      </div>
      <label>Dataset
        <select value={datasetSize} onChange={(event) => {
          const size = Number(event.target.value) as DatasetSize;
          setDatasetSize(size);
          setScene(createFoundationDemoScene(size));
          setReady(false);
          setOverlapCandidateIds([]);
        }}>
          <option value={100_000}>100,000 systems</option>
          <option value={500_000}>500,000 systems</option>
        </select>
      </label>
      <label>View preset
        <select aria-label="View preset" value={viewPreset} onChange={(event) => {
          const preset = event.target.value as MapViewPreset;
          setViewPreset(preset);
          setScene((current) => applyViewPreset(current, preset, { x: 0, z: 0 }, viewport));
        }}>
          <option value="results">Results</option>
          <option value="galaxy">Galaxy</option>
          <option value="reference">Reference</option>
        </select>
      </label>
      <button type="button" onClick={() => {
        setScene((current) => {
          const armed = reduceScene(current, { type: 'enableOneTimeFit', center: { x: 0, z: 0 }, zoom: 64 });
          return reduceScene(armed, { type: 'advanceSceneRevision', revision: current.sceneRevision + 1 });
        });
      }}>New scene auto-fit</button>
      <button type="button" onClick={() => {
        const layers = scene.layers.map((layer) => layer.type === 'regions'
          ? { ...layer, visible: !layer.visible }
          : layer);
        onInteraction({ type: 'layerChanged', layers });
      }}>{regionVisible ? 'Hide' : 'Show'} regions</button>
      <button type="button" onClick={() => onInteraction({ type: 'navigateToPlanner' })}>Request Plan hand-off</button>
      <label>Return from
        <select aria-label="Return from feature" defaultValue="finder" onChange={(event) => applyScenario(event.target.value as HandoffScenario)}>
          <option value="finder">Finder</option>
          <option value="compare">Compare</option>
          <option value="savedSystems">Saved Systems</option>
          <option value="evidenceMap">Evidence Map</option>
          <option value="systemDetail">System Detail</option>
          <option value="clusterSearch">Cluster Search</option>
          <option value="planner">Planner</option>
        </select>
      </label>
    </header>

    <section className="foundation-status" aria-live="polite">
      <span data-testid="foundation-ready">{ready && regions.labels.length === 42 ? 'ready' : 'loading'}</span>
      <span data-testid="region-count">{regions.labels.length}/42 regions</span>
      <span data-testid="lod-count">{visibility.returnedBackground.toLocaleString()} / {visibility.totalInViewBackground.toLocaleString()} background</span>
      <span>{visibility.aggregateRemainder.toLocaleString()} aggregated</span>
      <span>{visibility.guaranteedCount} guaranteed</span>
      <span>{highlightIds.size} highlighted · {scene.clusters.length} cluster</span>
      <span data-testid="production-parity-counts">
        {productionParity.overlays.heatmap?.cellCount ?? 0} heatmap · {productionParity.overlays.aggregateHulls?.hullCount ?? 0} aggregate hulls · {productionParity.timeline?.pointCount ?? 0} timeline
      </span>
      <span data-testid="context-state">context {contextState}</span>
    </section>

    <div className="foundation-layout">
      <div className="foundation-viewport" ref={viewportRef}>
        <R3FMapFoundation scene={scene} regions={regionVisible ? regions : EMPTY_REGIONS}
          productionOverlays={productionParity.overlays} viewport={viewport}
          onReady={() => setReady(true)} onInteraction={onInteraction} onVisibilityChange={setVisibility} />
      </div>
      <aside className="foundation-companion" aria-label="Map keyboard companion">
        <h2>Context companion</h2>
        <p>Tab to any system and press Enter. Shift-drag rotates/tilts; drag pans; wheel zooms.</p>
        {overlapCandidateIds.length > 0 && <section data-testid="overlap-choices">
          <h3>Choose overlapping system</h3>
          {overlapCandidateIds.map((id) => <button type="button" key={id} onClick={() => chooseOverlap(id)}>
            {systemsById.get(id)?.name ?? id}
          </button>)}
        </section>}
        <section>
          <h3>Guaranteed systems</h3>
          {[...highlightIds].map((id) => <button type="button" key={id}
            aria-pressed={scene.selectedSystemId64 === id}
            onClick={() => onInteraction({
              type: 'selectSystem',
              systemId64: id,
              clusterAnchorId64: clusterAnchorIdForSystem(scene, id),
            })}>
            {systemsById.get(id)?.name ?? id}
          </button>)}
        </section>
        <section>
          <h3>Visible layers</h3>
          <ul>{scene.layers.map((layer) => <li key={layer.type}>{layer.type}: {layer.visible ? 'on' : 'off'}</li>)}</ul>
        </section>
        <section className="event-log">
          <h3>Last typed interaction</h3>
          <code data-testid="last-interaction">{lastInteraction?.type ?? 'none'}</code>
          <p>Host command: <code data-testid="last-host-command">{lastHostCommand}</code></p>
          <p>Return workflow: <code data-testid="return-workflow">{scene.returnWorkflow?.type ?? 'none'}</code></p>
          <p>{omittedHandoffSystemIds.length} coordinate omissions</p>
          {lastInteraction?.type === 'navigateToPlanner' && <p>No plan mutation occurred.</p>}
        </section>
      </aside>
    </div>
  </main>;
}
