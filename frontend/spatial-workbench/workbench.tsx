import { useEffect, useRef, useState } from 'react';
import { BabylonMapRuntime } from '../src/features/spatial-runtime/babylon/BabylonMapRuntime';
import { createSpatialFixture, fixtureSystemTarget, FIXTURE_TIERS, type FixtureTier } from '../src/features/spatial-runtime/fixtures';
import { measurePickingCandidates, type PickingEvidence } from '../src/features/spatial-runtime/picking';
import type { RuntimeBackend, RuntimeTelemetry } from '../src/features/spatial-runtime/contracts';

export function SpatialWorkbench() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runtimeRef = useRef<BabylonMapRuntime | null>(null);
  const [tier, setTier] = useState<FixtureTier>(20_000);
  const [backend, setBackend] = useState<RuntimeBackend | 'initializing'>('initializing');
  const [telemetry, setTelemetry] = useState<RuntimeTelemetry | null>(null);
  const [evidence, setEvidence] = useState<PickingEvidence[]>([]);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const runtime = new BabylonMapRuntime(); runtimeRef.current = runtime;
    let active = true;
    void runtime.initialize(canvas, { preferWebGpu: true, reducedMotion, onTelemetry: setTelemetry }).then((selected) => {
      if (!active) return; setBackend(selected); runtime.dispatch({ type: 'LOAD_SCENE', scene: createSpatialFixture(tier) }); runtime.dispatch({ type: 'RESIZE', width: canvas.clientWidth, height: canvas.clientHeight, dpr: devicePixelRatio });
    }).catch(() => setBackend('initializing'));
    const observer = new ResizeObserver(([entry]) => { if (entry) runtime.dispatch({ type: 'RESIZE', width: entry.contentRect.width, height: entry.contentRect.height, dpr: devicePixelRatio }); });
    observer.observe(canvas);
    return () => { active = false; observer.disconnect(); runtime.dispose(); runtimeRef.current = null; };
  }, [reducedMotion]);

  const load = (next: FixtureTier) => { setTier(next); runtimeRef.current?.dispatch({ type: 'LOAD_SCENE', scene: createSpatialFixture(next) }); };
  const benchmark = async () => setEvidence(await measurePickingCandidates(['babylon-instance', 'gpu-id-buffer', 'cpu-index-gpu-confirm'], async (strategy) => { await runtimeRef.current?.pick(640, 360, strategy); }, 10));
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
    <canvas ref={canvasRef} aria-label="Isolated Babylon galaxy workbench" />
    <aside aria-live="polite"><h2>Non-personal telemetry</h2><pre data-testid="telemetry">{JSON.stringify(telemetry, null, 2)}</pre><h2>Picking evidence</h2><pre>{JSON.stringify(evidence, null, 2)}</pre><p>GPU timing is reported as null when unavailable. The ID-buffer path is explicitly marked as emulated until hardware evidence exists.</p></aside>
  </main>;
}
