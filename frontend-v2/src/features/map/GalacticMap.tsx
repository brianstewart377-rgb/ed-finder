import { useEffect, useMemo, useRef, useState } from 'react';
import { hasKnownCoords } from '@/lib/format';
import { archetypeTierFromScore, getDevelopmentScore } from '@/lib/archetypes';
import type { SystemResult } from '@/types/api';
import type { MapRegion, MapHeatmapResponse, MapClusterHull } from '@/lib/api';

interface MapViewState {
  cx: number;
  cz: number;
  scale: number;
}

const MIN_MAP_SCALE = 0.05;
const MAX_MAP_SCALE = 60;
const DEFAULT_MAP_SCALE = 6;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function clampScale(scale: number): number {
  if (!isFiniteNumber(scale)) return DEFAULT_MAP_SCALE;
  return Math.max(MIN_MAP_SCALE, Math.min(MAX_MAP_SCALE, scale));
}

function sanitizeView(view: MapViewState, fallback: MapViewState): MapViewState {
  return {
    cx: isFiniteNumber(view.cx) ? view.cx : fallback.cx,
    cz: isFiniteNumber(view.cz) ? view.cz : fallback.cz,
    scale: clampScale(view.scale),
  };
}

function normalizeWheelDelta(deltaY: number, deltaMode: number, viewportHeight: number): number {
  if (!isFiniteNumber(deltaY)) return 0;
  if (deltaMode === WheelEvent.DOM_DELTA_LINE) return deltaY * 16;
  if (deltaMode === WheelEvent.DOM_DELTA_PAGE) return deltaY * Math.max(viewportHeight, 1);
  return deltaY;
}

/**
 * Galaxy frame geometry (ED-Finder-native context, NOT copied in-game art).
 *
 * In ED galactic coordinates Sol sits at the origin and the galactic centre
 * (Sagittarius A*) lies ~25,900 LY toward +Z. The Milky Way disc is ~100k LY
 * across, so a conservative drawing radius of 50,000 LY frames the populated
 * bubble inside a much larger galaxy. These are only used for the subtle
 * context disc / rings; nothing here drives data fetching or auto-fit.
 */
const GALAXY_CENTER = { x: 25.2, z: 25899.9 } as const;
const GALAXY_RADIUS_LY = 50_000;

function developmentColor(score: number | null | undefined): string {
  switch (archetypeTierFromScore(score)) {
    case 'S':
      return '#22d3ee';
    case 'A':
      return '#4ade80';
    case 'B':
      return '#facc15';
    case 'C':
      return '#ff7a14';
    case 'D':
      return '#ef4444';
    default:
      return '#8a8f96';
  }
}

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
 *   • Each system is drawn as a circle whose color = development tier.
 */
export interface GalacticMapProps {
  systems:        SystemResult[];
  reference:      { name: string; x: number; z: number };
  selectedId64?:  number | null;
  onSelect?:      (sys: SystemResult | null) => void;
  /** Initial half-extent in LY (default = auto-fit to data + 20%). */
  initialRadius?: number;
  /** Optional canonical galaxy region labels to draw behind stars. */
  regions?:       MapRegion[];
  /** Optional voxel-aggregated density heatmap to draw behind everything. */
  heatmap?:       MapHeatmapResponse;
  /** Optional cluster-anchor hulls (translucent circles) to draw behind stars. */
  clusters?:      MapClusterHull[];
  /** Draw the subtle ED-native galaxy disc / axes context. Default true. */
  showGalacticFrame?: boolean;
  /**
   * Viewport preset. Changing it resets pan/zoom:
   *   • 'results'   — auto-fit Finder result dots (default)
   *   • 'galaxy'    — zoom out to frame the whole galaxy disc/rings
   *   • 'reference' — centre on the reference point at a local scale
   */
  viewMode?:      MapViewMode;
}

export type MapViewMode = 'results' | 'galaxy' | 'reference';

export function GalacticMap({
  systems, reference, selectedId64, onSelect, initialRadius, regions, heatmap, clusters,
  showGalacticFrame = true, viewMode = 'results',
}: GalacticMapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fallbackView = useMemo<MapViewState>(
    () => ({ cx: reference.x, cz: reference.z, scale: DEFAULT_MAP_SCALE }),
    [reference.x, reference.z],
  );
  // Camera state: centre is in galactic LY coords, scale = pixels per LY.
  const [view, setView] = useState<MapViewState>({
    cx: reference.x,
    cz: reference.z,
    scale: DEFAULT_MAP_SCALE,           // px per LY at zoom = 1
  });
  const viewRef = useRef(view);
  const fallbackViewRef = useRef(fallbackView);
  const autoFitSignature = useMemo(
    () => systems
      .map((system) => `${system.id64}:${system.coords?.x ?? ''}:${system.coords?.y ?? ''}:${system.coords?.z ?? ''}`)
      .join('|'),
    [systems],
  );

  const plottableSystems = useMemo(
    () => systems.filter((system) => hasKnownCoords(system.coords, system.id64)),
    [systems],
  );

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  useEffect(() => {
    fallbackViewRef.current = fallbackView;
  }, [fallbackView]);

  // ── Viewport presets. Re-applied when the mode or data changes. ─────
  // Each mode resets pan/zoom to a sensible framing; the user can still
  // freely pan/zoom afterwards (state lives in `view`).
  useEffect(() => {
    const el = canvasRef.current;
    const w = Math.max(el?.clientWidth ?? 600, 1);
    const h = Math.max(el?.clientHeight ?? 400, 1);
    const fitScale = (radiusLy: number) => {
      const safeRadius = isFiniteNumber(radiusLy) && radiusLy > 0 ? radiusLy : 50;
      return clampScale(Math.min(w, h) / (2 * safeRadius));
    };

    if (viewMode === 'galaxy') {
      // Frame the whole galaxy disc + a little margin around the rings.
      setView({
        cx: GALAXY_CENTER.x,
        cz: GALAXY_CENTER.z,
        scale: fitScale(GALAXY_RADIUS_LY * 1.1),
      });
      return;
    }

    if (viewMode === 'reference') {
      // Centre on the reference point at a comfortable local scale.
      setView({ cx: reference.x, cz: reference.z, scale: fitScale(initialRadius ?? 50) });
      return;
    }

    // 'results' — auto-fit Finder result dots around the reference.
    if (plottableSystems.length === 0) return;
    const radius =
      initialRadius ??
      Math.max(
        20,
        ...plottableSystems.map((s) =>
          Math.hypot(s.coords!.x! - reference.x, s.coords!.z! - reference.z),
        ),
      ) * 1.1;
    setView({ cx: reference.x, cz: reference.z, scale: fitScale(radius) });
  }, [viewMode, autoFitSignature, plottableSystems, reference.x, reference.z, initialRadius]);

  // ── Render loop. Re-runs on view/systems/selection changes. ────────
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    const safeView = sanitizeView(view, fallbackView);
    if (
      safeView.cx !== view.cx
      || safeView.cz !== view.cz
      || safeView.scale !== view.scale
    ) {
      setView(safeView);
      return;
    }
    const dpr = Math.max(1, Math.min(isFiniteNumber(window.devicePixelRatio) ? window.devicePixelRatio : 1, 2));
    const w = Math.max(cvs.clientWidth, 1);
    const h = Math.max(cvs.clientHeight, 1);
    if (cvs.width !== w * dpr || cvs.height !== h * dpr) {
      cvs.width  = w * dpr;
      cvs.height = h * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // World→screen: x_screen = (x - cx)*scale + w/2 ;  z flipped so +z is up
    const wx = (x: number) => (x - safeView.cx) * safeView.scale + w / 2;
    const wz = (z: number) => -(z - safeView.cz) * safeView.scale + h / 2;

    // ── Backdrop — gunmetal radial fade ─────────────────────────────
    const grd = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    grd.addColorStop(0,   'hsl(218 11% 14%)');
    grd.addColorStop(0.6, 'hsl(220 12% 8%)');
    grd.addColorStop(1,   'hsl(222 14% 5%)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, w, h);

    // ── Galactic frame (subtle ED-native context, behind everything) ─
    if (showGalacticFrame) {
      const gcx = wx(GALAXY_CENTER.x);
      const gcz = wz(GALAXY_CENTER.z);
      const discR = GALAXY_RADIUS_LY * safeView.scale;

      ctx.save();
      // Faint disc glow toward the galactic centre.
      const discGrad = ctx.createRadialGradient(gcx, gcz, 0, gcx, gcz, discR);
      discGrad.addColorStop(0,    'rgba(255,122,20,0.05)');   // orange core haze
      discGrad.addColorStop(0.55, 'rgba(120,140,170,0.035)'); // steel mid
      discGrad.addColorStop(1,    'rgba(120,140,170,0)');     // fade to space
      ctx.beginPath();
      ctx.arc(gcx, gcz, discR, 0, Math.PI * 2);
      ctx.fillStyle = discGrad;
      ctx.fill();

      // Outer boundary ring + concentric context rings (25/50/75/100%).
      ctx.strokeStyle = 'rgba(160,176,196,0.16)';   // steel
      ctx.lineWidth = 1;
      for (const frac of [0.25, 0.5, 0.75, 1]) {
        ctx.beginPath();
        ctx.arc(gcx, gcz, discR * frac, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Galactic centre marker (small steel cross) when on screen.
      if (gcx > -20 && gcx < w + 20 && gcz > -20 && gcz < h + 20) {
        ctx.strokeStyle = 'rgba(255,122,20,0.5)';
        ctx.beginPath();
        ctx.moveTo(gcx - 6, gcz); ctx.lineTo(gcx + 6, gcz);
        ctx.moveTo(gcx, gcz - 6); ctx.lineTo(gcx, gcz + 6);
        ctx.stroke();
      }

      // Galactic axis lines through the origin (Sol) — x=0 and z=0.
      ctx.strokeStyle = 'rgba(160,176,196,0.10)';
      ctx.beginPath();
      ctx.moveTo(wx(0), 0); ctx.lineTo(wx(0), h);   // z-axis (x = 0)
      ctx.moveTo(0, wz(0)); ctx.lineTo(w, wz(0));   // x-axis (z = 0)
      ctx.stroke();
      ctx.restore();
    }

    // Background grid every 10 LY at scales > 2 px/LY
    if (safeView.scale >= 2) {
      const step = 10;
      ctx.strokeStyle = 'rgba(200,204,209,0.06)';   // silver-dim
      ctx.lineWidth = 1;
      const left = safeView.cx - w / 2 / safeView.scale;
      const right = safeView.cx + w / 2 / safeView.scale;
      const top  = safeView.cz + h / 2 / safeView.scale;
      const bot  = safeView.cz - h / 2 / safeView.scale;
      ctx.beginPath();
      for (let x = Math.ceil(left / step) * step; x < right; x += step) {
        ctx.moveTo(wx(x), 0); ctx.lineTo(wx(x), h);
      }
      for (let z = Math.ceil(bot / step) * step; z < top; z += step) {
        ctx.moveTo(0, wz(z)); ctx.lineTo(w, wz(z));
      }
      ctx.stroke();
    }

    // ── Heatmap voxels (behind everything except backdrop/grid) ─────
    if (heatmap && heatmap.cells.length > 0) {
      const cell = heatmap.voxel_size * safeView.scale;
      // Half-cell offset: backend cx/cz are voxel CENTRES.
      const half = cell / 2;
      if (!isFiniteNumber(cell) || cell <= 0) return;
      ctx.save();
      for (const c of heatmap.cells) {
        if (!isFiniteNumber(c.cx) || !isFiniteNumber(c.cz)) continue;
        const px = wx(c.cx);
        const py = wz(c.cz);
        if (px + half < 0 || py + half < 0 || px - half > w || py - half > h) continue;
        const score = c.avg_score ?? 0;
        const fillColor = developmentColor(score);
        // Subtle fill; never strong enough to swamp star dots above it.
        ctx.globalAlpha = 0.16;
        ctx.fillStyle = fillColor;
        ctx.fillRect(px - half, py - half, cell, cell);
      }
      ctx.restore();
      ctx.globalAlpha = 1;
    }

    // ── Cluster hulls (translucent circles, above heatmap) ──────────
    if (clusters && clusters.length > 0) {
      ctx.save();
      for (const c of clusters) {
        if (c.x == null || c.z == null) continue;
        const px = wx(c.x);
        const py = wz(c.z);
        const rad = c.radius_ly * safeView.scale;
        if (!isFiniteNumber(rad) || rad <= 0) continue;
        if (px + rad < 0 || py + rad < 0 || px - rad > w || py - rad > h) continue;
        const fillColor = developmentColor(c.top_score ?? null);
        // subtle translucent fill + slightly stronger ring
        ctx.beginPath();
        ctx.arc(px, py, rad, 0, Math.PI * 2);
        ctx.globalAlpha = 0.08;
        ctx.fillStyle = fillColor;
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.lineWidth = 1;
        ctx.strokeStyle = fillColor;
        ctx.stroke();
      }
      ctx.restore();
      ctx.globalAlpha = 1;
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
    for (const sys of plottableSystems) {
      const coords = sys.coords!;
      if (!isFiniteNumber(coords.x) || !isFiniteNumber(coords.z)) continue;
      const px = wx(coords.x!);
      const py = wz(coords.z!);
      if (px < -10 || py < -10 || px > w + 10 || py > h + 10) continue;
      const fillColor = developmentColor(getDevelopmentScore(sys));
      const isSel = sys.id64 === selectedId64;
      const r = isSel ? 6 : 3;

      // soft halo behind every star
      const haloGrad = ctx.createRadialGradient(px, py, 0, px, py, r * 4);
      haloGrad.addColorStop(0, `${fillColor}66`);
      haloGrad.addColorStop(1, `${fillColor}00`);
      ctx.fillStyle = haloGrad;
      ctx.beginPath();
      ctx.arc(px, py, r * 4, 0, Math.PI * 2);
      ctx.fill();

      // star core
      ctx.fillStyle = fillColor;
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

    // ── Region labels (dim, behind HUD) ─────────────────────────────
    if (regions && regions.length > 0) {
      ctx.fillStyle = 'rgba(200,204,209,0.18)';
      ctx.font = '600 10px JetBrains Mono, ui-monospace, monospace';
      for (const reg of regions) {
        if (reg.x == null || reg.z == null) continue;
        const rpx = wx(reg.x);
        const rpy = wz(reg.z);
        if (rpx < -50 || rpy < -10 || rpx > w + 50 || rpy > h + 10) continue;
        ctx.fillText(reg.name, rpx, rpy);
      }
    }

    // ── HUD: scale indicator + scale bar ────────────────────────────
    ctx.fillStyle = 'rgba(200,204,209,0.65)';   // silver-dk
    ctx.font = '600 11px JetBrains Mono, ui-monospace, monospace';
    ctx.fillText(
      `${plottableSystems.length} SYSTEMS · ${safeView.scale.toFixed(1)} PX/LY`,
      10, h - 10,
    );
    // 50-LY scale bar
    const barLy = safeView.scale > 4 ? 10 : safeView.scale > 1 ? 50 : 200;
    const barPx = barLy * safeView.scale;
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
  }, [plottableSystems, view, fallbackView, reference.x, reference.z, reference.name, selectedId64, regions, heatmap, clusters, showGalacticFrame]);

  // ── Pointer handlers ───────────────────────────────────────────────
  const drag = useRef<{ x: number; y: number; cx: number; cz: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const currentView = sanitizeView(viewRef.current, fallbackViewRef.current);
    drag.current = { x: e.clientX, y: e.clientY, cx: currentView.cx, cz: currentView.cz };
    (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current) return;
    setView((prev) => {
      const safePrev = sanitizeView(prev, fallbackViewRef.current);
      const dx = (e.clientX - drag.current!.x) / safePrev.scale;
      const dy = (e.clientY - drag.current!.y) / safePrev.scale;
      if (!isFiniteNumber(dx) || !isFiniteNumber(dy)) return safePrev;
      return sanitizeView({ ...safePrev, cx: drag.current!.cx - dx, cz: drag.current!.cz + dy }, fallbackViewRef.current);
    });
  };
  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const target = e.target as HTMLCanvasElement;
    if (
      typeof target.hasPointerCapture === 'function'
      && typeof target.releasePointerCapture === 'function'
      && target.hasPointerCapture(e.pointerId)
    ) {
      target.releasePointerCapture(e.pointerId);
    }
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
    const w = Math.max(cvs.clientWidth, 1);
    const h = Math.max(cvs.clientHeight, 1);
    if (!isFiniteNumber(px) || !isFiniteNumber(py)) return;
    const currentView = sanitizeView(viewRef.current, fallbackViewRef.current);
    const wx = (x: number) => (x - currentView.cx) * currentView.scale + w / 2;
    const wz = (z: number) => -(z - currentView.cz) * currentView.scale + h / 2;
    let best: { sys: SystemResult; d: number } | null = null;
    for (const sys of plottableSystems) {
      const coords = sys.coords!;
      if (!isFiniteNumber(coords.x) || !isFiniteNumber(coords.z)) continue;
      const dx = wx(coords.x!) - px;
      const dy = wz(coords.z!) - py;
      const d  = Math.hypot(dx, dy);
      if (d < 8 && (best == null || d < best.d)) best = { sys, d };
    }
    onSelect?.(best ? best.sys : null);
  };

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = normalizeWheelDelta(event.deltaY, event.deltaMode, cvs.clientHeight);
      if (delta === 0) return;
      const clampedDelta = Math.max(-4000, Math.min(4000, delta));
      setView((prev) => {
        const safePrev = sanitizeView(prev, fallbackViewRef.current);
        const factor = Math.exp(-clampedDelta * 0.0015);
        if (!isFiniteNumber(factor)) return safePrev;
        return { ...safePrev, scale: clampScale(safePrev.scale * factor) };
      });
    };
    cvs.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      cvs.removeEventListener('wheel', handleWheel);
    };
  }, []);

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
        aria-label="Galactic map canvas. Drag to pan, scroll to zoom, click a star to select."
        className="w-full h-full cursor-grab active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { drag.current = null; }}
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
      <div className="font-display text-orange uppercase tracking-[0.18em] text-[10px] mb-1">Development</div>
      <LegendRow label="S 88+"         color="#22d3ee" />
      <LegendRow label="A 76-87"       color="#4ade80" />
      <LegendRow label="B 60-75"       color="#facc15" />
      <LegendRow label="C 45-59"       color="#ff7a14" />
      <LegendRow label="D < 45"        color="#ef4444" />
      <LegendRow label="No development data" color="#8a8f96" />
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
