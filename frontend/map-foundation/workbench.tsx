import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DatasetSize } from '../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import {
  initOverlapCycling,
  reduceScene,
  type MapInteractionEvent,
  type MapSceneState,
} from '../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { R3FMapFoundation } from '../src/features/map-foundation/R3FMapFoundation';
import { createFoundationDemoScene } from '../src/features/map-foundation/demo-scene';
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

export function MapFoundationWorkbench() {
  const [datasetSize, setDatasetSize] = useState<DatasetSize>(500_000);
  const [scene, setScene] = useState<MapSceneState>(() => createFoundationDemoScene(datasetSize));
  const [regions, setRegions] = useState<RegionLayerData>(EMPTY_REGIONS);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const [ready, setReady] = useState(false);
  const [overlapCandidateIds, setOverlapCandidateIds] = useState<number[]>([]);
  const [contextState, setContextState] = useState<FoundationSnapshot['contextState']>('ready');
  const [lastInteraction, setLastInteraction] = useState<MapInteractionEvent | null>(null);
  const [visibility, setVisibility] = useState<VisibilityMetadata>(EMPTY_VISIBILITY);
  const viewportRef = useRef<HTMLDivElement>(null);
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

  const highlightIds = useMemo(() => highlightedSystemIds(scene.highlights), [scene.highlights]);
  const systemsById = useMemo(() => new Map(scene.systems.map((system) => [system.id64, system])), [scene.systems]);
  const regionVisible = scene.layers.find((layer) => layer.type === 'regions')?.visible ?? false;

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
  }), [contextState, datasetSize, highlightIds.size, lastInteraction, overlapCandidateIds, ready, regions, scene, visibility]);

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
        <p className="eyebrow">Development-only · Stage 26C</p>
        <h1>Region-first R3F foundation</h1>
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
    </header>

    <section className="foundation-status" aria-live="polite">
      <span data-testid="foundation-ready">{ready && regions.labels.length === 42 ? 'ready' : 'loading'}</span>
      <span data-testid="region-count">{regions.labels.length}/42 regions</span>
      <span data-testid="lod-count">{visibility.returnedBackground.toLocaleString()} / {visibility.totalInViewBackground.toLocaleString()} background</span>
      <span>{visibility.aggregateRemainder.toLocaleString()} aggregated</span>
      <span>{visibility.guaranteedCount} guaranteed</span>
      <span>{highlightIds.size} highlighted · {scene.clusters.length} cluster</span>
      <span data-testid="context-state">context {contextState}</span>
    </section>

    <div className="foundation-layout">
      <div className="foundation-viewport" ref={viewportRef}>
        <R3FMapFoundation scene={scene} regions={regionVisible ? regions : EMPTY_REGIONS} viewport={viewport}
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
          {lastInteraction?.type === 'navigateToPlanner' && <p>No plan mutation occurred.</p>}
        </section>
      </aside>
    </div>
  </main>;
}
