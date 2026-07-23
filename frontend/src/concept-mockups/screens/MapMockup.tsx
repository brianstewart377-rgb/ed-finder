import { useEffect, useRef, useState } from 'react';
import { useGalleryEnv, motion } from '../env';
import { StatusPill } from '../primitives';

const VIEWS = ['Results', 'Galaxy', 'Reference'] as const;
const LAYERS = ['Regions', 'Heatmap', 'Clusters', 'Timeline'] as const;

/**
 * Mockup 3 — Map as a full remaining-viewport workspace.
 * A synthetic starfield stands in for the production R3F renderer and starts at
 * the top (map-first). Compact edge-mounted controls; legend/selection/timeline
 * float over the renderer only when needed. No planning canvas.
 */
export function MapMockup() {
  const { reducedMotion } = useGalleryEnv();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [view, setView] = useState<typeof VIEWS[number]>('Results');
  const [proj, setProj] = useState<'2D' | '3D'>('3D');
  const [layers, setLayers] = useState<Record<string, boolean>>({ Regions: false, Heatmap: false, Clusters: true, Timeline: false });
  const [selected, setSelected] = useState(true);

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    let raf = 0;
    const stars = Array.from({ length: 220 }, () => ({
      x: Math.random(), y: Math.random(), r: Math.random() * 1.6 + 0.3, s: Math.random() * 0.02 + 0.003,
    }));
    const draw = (t: number) => {
      const w = cvs.clientWidth; const h = cvs.clientHeight;
      if (cvs.width !== w) cvs.width = w;
      if (cvs.height !== h) cvs.height = h;
      ctx.clearRect(0, 0, w, h);
      const g = ctx.createRadialGradient(w * 0.7, h * 0.2, 0, w * 0.7, h * 0.2, Math.max(w, h) * 0.8);
      g.addColorStop(0, 'rgba(255,122,20,0.10)');
      g.addColorStop(0.5, 'rgba(20,26,34,0.0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
      for (const st of stars) {
        const drift = reducedMotion ? 0 : Math.sin(t * st.s) * 0.004;
        const px = ((st.x + drift) % 1) * w; const py = st.y * h;
        ctx.beginPath(); ctx.arc(px, py, st.r, 0, Math.PI * 2);
        ctx.fillStyle = st.r > 1.2 ? 'rgba(125,211,252,0.8)' : 'rgba(220,225,232,0.65)';
        ctx.fill();
      }
      const marks = [[0.42, 0.55], [0.55, 0.4], [0.6, 0.62], [0.35, 0.38]];
      marks.forEach(([mx, my], i) => {
        ctx.beginPath(); ctx.arc(mx * w, my * h, i === 0 && selected ? 6 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = i === 0 && selected ? '#ff7a14' : '#7dd3fc'; ctx.fill();
        if (i === 0 && selected) { ctx.strokeStyle = 'rgba(255,122,20,0.6)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(mx * w, my * h, 11, 0, Math.PI * 2); ctx.stroke(); }
      });
      if (!reducedMotion) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [reducedMotion, selected]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg1">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-label="Concept galactic map renderer" />

      <div className="absolute left-3 top-3 flex flex-col gap-2">
        <div role="group" aria-label="Map view" className="flex overflow-hidden rounded-chunk-sm border border-border bg-bg2/90 backdrop-blur">
          {VIEWS.map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)} className={['px-2.5 py-1 font-mono text-[10px] tracking-wider focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70', motion(reducedMotion, 'transition-colors'), view === v ? 'bg-orange/20 text-orange' : 'text-silver-dk hover:text-silver'].join(' ')}>{v}</button>
          ))}
        </div>
        <div role="group" aria-label="Projection" className="flex w-fit overflow-hidden rounded-chunk-sm border border-border bg-bg2/90 backdrop-blur">
          {(['2D', '3D'] as const).map((p) => (
            <button key={p} type="button" aria-pressed={proj === p} onClick={() => setProj(p)} className={['px-2.5 py-1 font-mono text-[10px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/70', proj === p ? 'bg-cyan/20 text-cyan' : 'text-silver-dk hover:text-silver'].join(' ')}>{p}</button>
          ))}
        </div>
      </div>

      <div className="absolute right-3 top-3 flex items-center gap-1.5">
        <button type="button" className="btn-metal font-mono text-[10px]">Back to Finder</button>
        <button type="button" className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-1.5 font-mono text-[10px] text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/70">Inspect</button>
        <button type="button" className="rounded-chunk-sm border border-border bg-bg2/90 px-2.5 py-1.5 font-mono text-[10px] text-silver hover:text-orange">About</button>
        <button type="button" className="rounded-chunk-sm border border-border bg-bg2/90 px-2.5 py-1.5 font-mono text-[10px] text-silver hover:text-orange">Legal</button>
      </div>

      <div className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-chunk border border-border bg-bg2/90 p-2 backdrop-blur">
        <span className="px-1 font-mono text-[9px] uppercase tracking-[0.16em] text-silver-2">Layers</span>
        {LAYERS.map((l) => (
          <label key={l} className="flex cursor-pointer items-center gap-2 px-1 py-0.5 font-mono text-[10px] text-silver">
            <input type="checkbox" className="accent-cyan" checked={layers[l]} onChange={(e) => setLayers((s) => ({ ...s, [l]: e.target.checked }))} />
            {l}
          </label>
        ))}
      </div>

      <div className="absolute right-3 top-16 rounded-chunk border border-border bg-bg2/85 p-2.5 font-mono text-[10px] text-silver-dk backdrop-blur">
        <div className="mb-1 flex items-center gap-1.5 text-silver"><span className="h-2 w-2 rounded-full bg-orange" />Selected candidate</div>
        <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan" />Finder result</div>
      </div>

      {selected && (
        <div className="absolute bottom-3 right-3 w-64 rounded-chunk border border-border bg-bg2/92 p-3 font-mono text-[11px] backdrop-blur">
          <div className="flex items-center justify-between">
            <span className="text-orange">HIP 21991</span>
            <button type="button" onClick={() => setSelected(false)} aria-label="Clear selection" className="text-silver-dk hover:text-orange">×</button>
          </div>
          <div className="mt-1 text-silver-dk">Refinery · Dev 91 · 42.6 LY</div>
          <StatusPill tone="info" label="Inspect ready" className="mt-2" />
        </div>
      )}

      {layers.Timeline && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-chunk border border-border bg-bg2/90 px-4 py-2 font-mono text-[10px] text-silver-dk backdrop-blur">
          Timeline · 12 buckets · latest 3305-07 · discovery density
        </div>
      )}
    </div>
  );
}
