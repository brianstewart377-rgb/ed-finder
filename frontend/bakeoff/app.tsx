import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CANDIDATES,
  generateDataset,
  type DatasetSize,
} from '../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import type { RendererCandidateId } from '../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import { runAllFixtures } from './fixture-runner';
import { DeckOrbitCandidate, DeckOrthoCandidate, ThreeCandidate } from './renderers';
import type { HarnessSnapshot, RegionLayerData } from './types';

const EMPTY_REGIONS: RegionLayerData = { labels: [], boundaries: [] };
const HARNESS_STARTED_AT = performance.now();

export function BakeoffApp() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const [candidate, setCandidate] = useState<RendererCandidateId>(
    (params.get('candidate') as RendererCandidateId | null) ?? 'deckgl-orbit',
  );
  const [datasetSize, setDatasetSize] = useState<DatasetSize>(params.get('dataset') === '500000' ? 500_000 : 100_000);
  const [regions, setRegions] = useState<RegionLayerData>(EMPTY_REGIONS);
  const [ready, setReady] = useState(false);
  const [selectedId64, setSelectedId64] = useState<number | null>(null);
  const [selectionCount, setSelectionCount] = useState(0);
  const [initialLoadMs, setInitialLoadMs] = useState<number | null>(null);
  const [clickLatencyMs, setClickLatencyMs] = useState<number | null>(null);
  const startRef = useRef(HARNESS_STARTED_AT);
  const initialSelectionRef = useRef(true);
  const frameTimesRef = useRef<number[]>([]);
  const fixtures = useMemo(runAllFixtures, []);
  const systems = useMemo(() => generateDataset(datasetSize), [datasetSize]);

  useEffect(() => {
    fetch('/__stage26b/regions').then((response) => response.json()).then(setRegions);
  }, []);
  useEffect(() => {
    let previous = performance.now();
    let frame = 0;
    const sample = (now: number) => {
      frameTimesRef.current.push(now - previous);
      if (frameTimesRef.current.length > 300) frameTimesRef.current.shift();
      previous = now;
      frame = requestAnimationFrame(sample);
    };
    frame = requestAnimationFrame(sample);
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (initialSelectionRef.current) {
      initialSelectionRef.current = false;
      return;
    }
    startRef.current = performance.now();
    frameTimesRef.current = [];
    setReady(false);
    setSelectedId64(null);
    setSelectionCount(0);
    setInitialLoadMs(null);
    setClickLatencyMs(null);
  }, [candidate, datasetSize]);

  const onReady = useCallback(() => {
    setReady((wasReady) => {
      if (!wasReady) setInitialLoadMs(performance.now() - startRef.current);
      return true;
    });
  }, []);
  const onSelect = useCallback((id64: number, startedAt: number) => {
    setSelectedId64(id64);
    setSelectionCount((count) => count + 1);
    requestAnimationFrame(() => setClickLatencyMs(performance.now() - startedAt));
  }, []);
  const snapshot = useCallback((): HarnessSnapshot => ({
    candidate, datasetSize, ready, selectedId64, selectionCount, initialLoadMs, clickLatencyMs,
    frameTimesMs: [...frameTimesRef.current], fixtureResults: fixtures.results,
    fixtureFailures: fixtures.failures, regionLabelCount: regions.labels.length,
    regionBoundaryCount: regions.boundaries.length,
  }), [candidate, datasetSize, ready, selectedId64, selectionCount, initialLoadMs, clickLatencyMs, fixtures, regions]);
  useEffect(() => {
    window.__stage26bBakeoff = { snapshot };
    return () => { delete window.__stage26bBakeoff; };
  }, [snapshot]);

  const rendererProps = { systems, regions, onReady, onSelect };
  return <main>
    <header>
      <div><strong>Stage 26B</strong><span>isolated renderer bake-off</span></div>
      <fieldset aria-label="Renderer candidate">
        {CANDIDATES.map((item) => <label key={item.id}>
          <input type="radio" name="candidate" checked={candidate === item.id}
            onChange={() => setCandidate(item.id)} />{item.label}
        </label>)}
      </fieldset>
      <label>Dataset
        <select value={datasetSize} onChange={(event) => setDatasetSize(Number(event.target.value) as DatasetSize)}>
          <option value={100_000}>100,000</option><option value={500_000}>500,000</option>
        </select>
      </label>
    </header>
    <section className="status" aria-live="polite">
      <span data-testid="ready">{ready ? 'ready' : 'loading'}</span>
      <span>{systems.length.toLocaleString()} systems</span>
      <span>{regions.labels.length}/42 regions</span>
      <span>{Object.values(fixtures.results).filter((value) => value === 'pass').length}/17 fixtures</span>
      <span>selected {selectedId64 ?? '—'}</span>
    </section>
    <section className="viewport" data-candidate={candidate}>
      {candidate === 'deckgl-orbit' && <DeckOrbitCandidate {...rendererProps} />}
      {candidate === 'deckgl-ortho' && <DeckOrthoCandidate {...rendererProps} />}
      {candidate === 'threejs-r3f' && <ThreeCandidate {...rendererProps} />}
    </section>
  </main>;
}
