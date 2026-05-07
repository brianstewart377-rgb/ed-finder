import { useEffect, useRef, useState } from 'react';
import { ratingTier } from '@/lib/format';
import type { SystemResult } from '@/types/api';

/**
 * Galactic map — top-down 2-D scatter plot of `systems` on the X/Z plane.
 *
 * Pure-React canvas: pan with drag, zoom with wheel, click to select. We
 * deliberately do NOT port the vanilla v1 map (~500 LoC of imperative
 * canvas code with mutable globals). This is a clean rewrite that
 * fits in <250 LoC and progressively gets more features.
 *
 * Coordinate system:
 *   • Galactic +X is right, +Z is up on screen (north galactic).
 *   • Reference system (Sol or whatever the user picked) is rendered
 *     as a centred orange diamond and is never clipped.
 *   • Each system is drawn as a circle whose color = rating tier.
 */
export interface GalacticMapProps {
  systems:        SystemResult[];
  reference:      { name: string; x: number; z: number };
  selectedId64?:  number | null;
  onSelect?:      (sys: SystemResult | null) => void;
  /** Initial half-extent in LY (default = auto-fit to data + 20%). */
  initialRadius?: number;
}

export function GalacticMap({
  systems, reference, selectedId64, onSelect, initialRadius,
}: GalacticMapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Camera state: centre is in galactic LY coords, scale = pixels per LY.
  const [view, setView] = useState({
    cx: reference.x,
    cz: reference.z,
    scale: 6,                          // px per LY at zoom = 1
  });

  // ── Auto-fit on first render & when systems list size changes a lot ─
  useEffect(() => {
    if (systems.length === 0) return;
    const radius =
      initialRadius ??
      Math.max(
        20,
        ...systems.map((s) =>
          Math.hypot((s.coords?.x ?? 0) - reference.x, (s.coords?.z ?? 0) - reference.z),
        ),
      ) * 1.1;
    const el = canvasRef.current;
    const w = el?.clientWidth  ?? 600;
    const h = el?.clientHeight ?? 400;
    const fit = Math.min(w, h) / (2 * radius);
    setView({ cx: reference.x, cz: reference.z, scale: Math.max(0.5, fit) });
  }, [systems.length, reference.x, reference.z, initialRadius]);

  // ── Render loop. Re-runs on view/systems/selection changes. ────────
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = cvs.clientWidth;
    const h = cvs.clientHeight;
    if (cvs.width !== w * dpr || cvs.height !== h * dpr) {
      cvs.width  = w * dpr;
      cvs.height = h * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // World→screen: x_screen = (x - cx)*scale + w/2 ;  z flipped so +z is up
    const wx = (x: number) => (x - view.cx) * view.scale + w / 2;
    const wz = (z: number) => -(z - view.cz) * view.scale + h / 2;

    // ── Backdrop — gunmetal radial fade ─────────────────────────────
    const grd = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    grd.addColorStop(0,   'hsl(218 11% 14%)');
    grd.addColorStop(0.6, 'hsl(220 12% 8%)');
    grd.addColorStop(1,   'hsl(222 14% 5%)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, w, h);

    // Background grid every 10 LY at scales > 2 px/LY
    if (view.scale >= 2) {
      const step = 10;
      ctx.strokeStyle = 'rgba(200,204,209,0.06)';   // silver-dim
      ctx.lineWidth = 1;
      const left = view.cx - w / 2 / view.scale;
      const right = view.cx + w / 2 / view.scale;
      const top  = view.cz + h / 2 / view.scale;
      const bot  = view.cz - h / 2 / view.scale;
      ctx.beginPath();
      for (let x = Math.ceil(left / step) * step; x < right; x += step) {
        ctx.moveTo(wx(x), 0); ctx.lineTo(wx(x), h);
      }
      for (let z = Math.ceil(bot / step) * step; z < top; z += step) {
        ctx.moveTo(0, wz(z)); ctx.lineTo(w, wz(z));
      }
      ctx.stroke();
    }

    // ── Reference cross-hair (orange glow ring) ─────────────────────
    const rx = wx(reference.x);
    const rz = wz(reference.z);

    // outer pulse ring
    ctx.strokeStyle = 'rgba(255,122,20,0.20)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(rx, rz, 22, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,122,20,0.45)';
    ctx.beginPath();
    ctx.arc(rx, rz, 14, 0, Math.PI * 2);
    ctx.stroke();

    // crosshair
    ctx.strokeStyle = 'rgba(255,122,20,0.6)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(rx - 18, rz); ctx.lineTo(rx - 8, rz);
    ctx.moveTo(rx + 8,  rz); ctx.lineTo(rx + 18, rz);
    ctx.moveTo(rx, rz - 18); ctx.lineTo(rx, rz - 8);
    ctx.moveTo(rx, rz + 8);  ctx.lineTo(rx, rz + 18);
    ctx.stroke();

    // brushed-chrome diamond core
    const diamondGrad = ctx.createLinearGradient(rx - 6, rz - 6, rx + 6, rz + 6);
    diamondGrad.addColorStop(0, '#ffb074');
    diamondGrad.addColorStop(0.5, '#ff7a14');
    diamondGrad.addColorStop(1, '#a13e00');
    ctx.fillStyle = diamondGrad;
    ctx.beginPath();
    ctx.moveTo(rx, rz - 6);
    ctx.lineTo(rx + 6, rz);
    ctx.lineTo(rx, rz + 6);
    ctx.lineTo(rx - 6, rz);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#ffb074';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#ffb074';
    ctx.font = '600 11px Orbitron, ui-monospace, monospace';
    ctx.fillText(reference.name.toUpperCase(), rx + 14, rz - 10);

    // ── Systems ─────────────────────────────────────────────────────
    for (const sys of systems) {
      if (!sys.coords) continue;
      const px = wx(sys.coords.x);
      const py = wz(sys.coords.z);
      if (px < -10 || py < -10 || px > w + 10 || py > h + 10) continue;
      const tier = ratingTier(sys._rating?.score ?? null);
      const isSel = sys.id64 === selectedId64;
      const r = isSel ? 6 : 3;

      // soft halo behind every star
      const haloGrad = ctx.createRadialGradient(px, py, 0, px, py, r * 4);
      haloGrad.addColorStop(0, `${tier.fillColor}66`);
      haloGrad.addColorStop(1, `${tier.fillColor}00`);
      ctx.fillStyle = haloGrad;
      ctx.beginPath();
      ctx.arc(px, py, r * 4, 0, Math.PI * 2);
      ctx.fill();

      // star core
      ctx.fillStyle = tier.fillColor;
      ctx.globalAlpha = 0.95;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();

      if (isSel) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#ff7a14';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(px, py, r + 4, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // ── HUD: scale indicator + scale bar ────────────────────────────
    ctx.fillStyle = 'rgba(200,204,209,0.65)';   // silver-dk
    ctx.font = '600 11px JetBrains Mono, ui-monospace, monospace';
    ctx.fillText(
      `${systems.length} SYSTEMS · ${view.scale.toFixed(1)} PX/LY`,
      10, h - 10,
    );
    // 50-LY scale bar
    const barLy = view.scale > 4 ? 10 : view.scale > 1 ? 50 : 200;
    const barPx = barLy * view.scale;
    if (barPx > 12 && barPx < w * 0.4) {
      const bx = w - 16 - barPx;
      const by = h - 16;
      ctx.strokeStyle = 'rgba(255,255,255,0.5)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(bx, by);          ctx.lineTo(bx + barPx, by);
      ctx.moveTo(bx, by - 4);      ctx.lineTo(bx, by + 4);
      ctx.moveTo(bx + barPx, by - 4); ctx.lineTo(bx + barPx, by + 4);
      ctx.stroke();
      ctx.fillStyle = 'rgba(200,204,209,0.65)';
      ctx.fillText(`${barLy} LY`, bx, by - 8);
    }
  }, [systems, view, reference.x, reference.z, reference.name, selectedId64]);

  // ── Pointer handlers ───────────────────────────────────────────────
  const drag = useRef<{ x: number; y: number; cx: number; cz: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, cx: view.cx, cz: view.cz };
    (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current) return;
    const dx = (e.clientX - drag.current.x) / view.scale;
    const dy = (e.clientY - drag.current.y) / view.scale;
    setView((v) => ({ ...v, cx: drag.current!.cx - dx, cz: drag.current!.cz + dy }));
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const wasDrag = drag.current && (
      Math.abs(e.clientX - drag.current.x) > 3 || Math.abs(e.clientY - drag.current.y) > 3
    );
    drag.current = null;
    if (wasDrag) return;
    // Hit-test for click selection
    const cvs = canvasRef.current; if (!cvs) return;
    const rect = cvs.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const w = cvs.clientWidth, h = cvs.clientHeight;
    const wx = (x: number) => (x - view.cx) * view.scale + w / 2;
    const wz = (z: number) => -(z - view.cz) * view.scale + h / 2;
    let best: { sys: SystemResult; d: number } | null = null;
    for (const sys of systems) {
      if (!sys.coords) continue;
      const dx = wx(sys.coords.x) - px;
      const dy = wz(sys.coords.z) - py;
      const d  = Math.hypot(dx, dy);
      if (d < 8 && (best == null || d < best.d)) best = { sys, d };
    }
    onSelect?.(best ? best.sys : null);
  };
  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * 0.0015);
    setView((v) => ({ ...v, scale: Math.max(0.05, Math.min(60, v.scale * factor)) }));
  };

  return (
    <div
      className="relative h-[calc(100vh-14rem)] min-h-[400px] rounded-chunk-lg overflow-hidden"
      style={{
        border: '1px solid hsl(216 10% 24%)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 14px 40px -16px rgba(0,0,0,0.85)',
      }}
    >
      <canvas
        ref={canvasRef}
        data-testid="galactic-map-canvas"
        className="w-full h-full cursor-grab active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { drag.current = null; }}
        onWheel={onWheel}
      />
      <Legend />
    </div>
  );
}

function Legend() {
  return (
    <div
      className="absolute top-3 right-3 px-3 py-2 rounded-chunk-sm font-mono text-[10px] space-y-0.5"
      style={{
        background: 'linear-gradient(180deg, rgba(28, 31, 36, 0.85), rgba(18, 20, 24, 0.85))',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        border: '1px solid hsl(216 10% 24%)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 8px 24px -16px rgba(0,0,0,0.6)',
      }}
    >
      <div className="font-display text-orange uppercase tracking-[0.18em] text-[10px] mb-1">Score</div>
      <LegendRow label="80+ Excellent" color="#3ddc84" />
      <LegendRow label="60-79 Good"    color="#facc15" />
      <LegendRow label="40-59 OK"      color="#ff7a14" />
      <LegendRow label="< 40 Poor"     color="#ef4444" />
      <LegendRow label="No rating"     color="#8a8f96" />
    </div>
  );
}

function LegendRow({ label, color }: { label: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}aa` }}
      />
      <span className="text-silver-dk">{label}</span>
    </div>
  );
}
