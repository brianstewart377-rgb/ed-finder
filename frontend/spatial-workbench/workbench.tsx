import { useEffect, useRef, useState } from 'react';
import { BabylonMapRuntime } from '../src/features/spatial-runtime/babylon/BabylonMapRuntime';
import { createSpatialFixture, fixtureSystemTarget, FIXTURE_TIERS, type FixtureTier } from '../src/features/spatial-runtime/fixtures';
import { measurePickingCandidates, type PickingEvidence } from '../src/features/spatial-runtime/picking';
import type { RuntimeBackend, RuntimeTelemetry } from '../src/features/spatial-runtime/contracts';

export function SpatialWorkbench() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<BabylonMapRuntime | null>(null);
  const tierRef = useRef<FixtureTier>(20_000);
  const [tier, setTier] = useState<FixtureTier>(20_000);
  const [backend, setBackend] = useState<RuntimeBackend | 'initializing'>('initializing');
  const [telemetry, setTelemetry] = useState<RuntimeTelemetry | null>(null);
  const [evidence, setEvidence] = useState<PickingEvidence[]>([]);
  const [status, setStatus] = useState('Initializing renderer.');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    const canvas = canvasRef.current; const canvasHost = canvasHostRef.current; if (!canvas || !canvasHost) return;
    const runtime = new BabylonMapRuntime(); runtimeRef.current = runtime;
    let active = true;
    const observer = new ResizeObserver(([entry]) => { if (entry) runtime.dispatch({ type: 'RESIZE', width: entry.contentRect.width, height: entry.contentRect.height, dpr: devicePixelRatio }); });
    void runtime.initialize(canvas, { preferWebGpu: true, reducedMotion, onTelemetry: setTelemetry }).then((selected) => {
      if (!active) return;
      const selectedTier = tierRef.current;
      setBackend(selected); runtime.dispatch({ type: 'LOAD_SCENE', scene: createSpatialFixture(selectedTier) }); runtime.dispatch({ type: 'RESIZE', width: canvasHost.clientWidth, height: canvasHost.clientHeight, dpr: devicePixelRatio }); setStatus(`${selected} renderer ready with ${selectedTier.toLocaleString()} fixture stars.`);
    }).catch(() => { if (active) setStatus('Renderer initialization failed.'); });
    observer.observe(canvasHost);
    return () => { active = false; observer.disconnect(); runtime.dispose(); runtimeRef.current = null; };
  }, [reducedMotion]);

  const load = (next: FixtureTier) => { tierRef.current = next; setTier(next); runtimeRef.current?.dispatch({ type: 'LOAD_SCENE', scene: createSpatialFixture(next) }); setStatus(`Loaded ${next.toLocaleString()} fixture stars.`); };
  const benchmark = async () => { setStatus('Picking comparison running.'); setEvidence(await measurePickingCandidates(['cpu-screen-projection', 'cpu-spatial-index'], async (strategy) => { await runtimeRef.current?.pick(640, 360, strategy); }, 10)); setStatus('Picking comparison complete.'); };
  return <main>
    <header><p>Development-only · no production route wiring</p><h1>Stage 27B Babylon 9 Runtime Workbench</h1><output data-testid="backend">Backend: {backend}</output></header>
    <section className="controls" aria-label="Workbench controls">
      <label>Fixture <select value={tier} onChange={(event) => load(Number(event.target.value) as FixtureTier)}>{FIXTURE_TIERS.map((count) => <option key={count} value={count}>{count.toLocaleString()}</option>)}</select></label>
      <button onClick={() => { const camera = runtimeRef.current?.snapshot().camera; if (camera && 'focusLy' in camera) runtimeRef.current?.dispatch({ type: 'SET_CAMERA', camera: { ...camera, projection: 'orthographic', pitchRad: Math.PI / 2, revision: camera.revision + 1 } }); }}>Top-down</button>
      <button onClick={() => { const camera = runtimeRef.current?.snapshot().camera; if (camera && 'focusLy' in camera) runtimeRef.current?.dispatch({ type: 'SET_CAMERA', camera: { ...camera, projection: 'perspective', pitchRad: .75, revision: camera.revision + 1 } }); }}>Restrained pitch</button>
      <button onClick={() => void runtimeRef.current?.dispatch({ type: 'FLY_TO', target: fixtureSystemTarget(0), reducedMotion })}>Fly to selected</button>
      <button onClick={() => runtimeRef.current?.cancelFlyTo()}>Cancel fly-to</button>
      <button onClick={() => runtimeRef.current?.suspend()}>Suspend</button><button onClick={() => runtimeRef.current?.resume()}>Resume</button>
      <button onClick={() => void runtimeRef.current?.dispatch({ type: 'REBUILD_RESOURCES', reason: 'backend-change' })}>Rebuild retained CPU state</button>
      <button onClick={() => void benchmark()}>Compare picking candidates</button>
    </section>
    <div ref={canvasHostRef} className="canvas-host"><canvas ref={canvasRef} aria-label="Isolated Babylon galaxy workbench" /></div>
    <aside><p className="workbench-status" role="status" data-testid="workbench-status">{status}</p><h2>Non-personal telemetry</h2><pre data-testid="telemetry">{JSON.stringify(telemetry, null, 2)}</pre><h2>Picking evidence</h2><pre>{JSON.stringify(evidence, null, 2)}</pre><p>GPU timing is reported as null when unavailable. Candidate limitations are recorded in the evidence output.</p></aside>
  </main>;
}
