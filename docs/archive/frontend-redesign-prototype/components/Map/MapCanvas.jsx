// Map canvas — visual prototype only. Renders the 4 backend layers we wired up
// in the audit (regions, cluster hulls, heatmap, systems) on a single SVG so
// any reviewer can see the proposed visual hierarchy without WebGL.
import React, { useMemo } from 'react';
import { ratingTier } from '../../lib/mockData';

export function MapCanvas({
  systems, regions, clusters, heatmap, layers, selectedId, onSelect, viewport,
}) {
  // World→screen scale: 1 LY = SCALE px in the SVG viewBox (-VB/2 to VB/2)
  const VB = 800;

  const sysWithScreen = useMemo(() => systems.map((s) => ({
    ...s,
    sx: (s.x / 500) * (VB / 2),
    sz: -(s.z / 500) * (VB / 2),
  })), [systems]);

  return (
    <div className="relative w-full h-full map-canvas-bg overflow-hidden">
      {/* Faint sweep arc — frontier indicator (decorative, hints at meaning) */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox={`-${VB / 2} -${VB / 2} ${VB} ${VB}`}
        preserveAspectRatio="xMidYMid slice"
      >
        {/* ── LAYER 0: Galactic disk hint ──────────────────── */}
        <defs>
          <radialGradient id="diskGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%"  stopColor="rgba(80,60,140,0.18)" />
            <stop offset="55%" stopColor="rgba(40,20,60,0.10)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </radialGradient>
          <radialGradient id="hotCell" cx="50%" cy="50%" r="50%">
            <stop offset="0%"  stopColor="rgba(255,106,0,0.55)" />
            <stop offset="60%" stopColor="rgba(255,106,0,0.10)" />
            <stop offset="100%" stopColor="rgba(255,106,0,0)" />
          </radialGradient>
          <radialGradient id="midCell" cx="50%" cy="50%" r="50%">
            <stop offset="0%"  stopColor="rgba(96,165,250,0.4)" />
            <stop offset="60%" stopColor="rgba(96,165,250,0.08)" />
            <stop offset="100%" stopColor="rgba(96,165,250,0)" />
          </radialGradient>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.025)" strokeWidth="0.5" />
          </pattern>
        </defs>

        <rect x={-VB / 2} y={-VB / 2} width={VB} height={VB} fill="url(#diskGlow)" />
        <rect x={-VB / 2} y={-VB / 2} width={VB} height={VB} fill="url(#grid)" />

        {/* ── LAYER 2: Heatmap voxels ──────────────────────── */}
        {layers.heatmap && heatmap.map((c, i) => {
          const sx = (c.x / 500) * (VB / 2);
          const sz = -(c.z / 500) * (VB / 2);
          const r = 28;
          const fill = c.score >= 65 ? 'url(#hotCell)' : 'url(#midCell)';
          const opacity = Math.max(0.15, c.score / 100);
          return <circle key={i} cx={sx} cy={sz} r={r} fill={fill} opacity={opacity} />;
        })}

        {/* ── LAYER 3: Cluster hulls (translucent zones) ──── */}
        {layers.clusters && clusters.map((cl) => {
          const sx = (cl.x / 500) * (VB / 2);
          const sz = -(cl.z / 500) * (VB / 2);
          const r = (cl.radius / 500) * (VB / 2);
          const econColors = {
            HighTech: '#42a5f5', Tourism: '#ec407a', Refinery: '#ff9133',
            Industrial: '#ffaa33', Agriculture: '#66bb6a', Military: '#ef5350',
          };
          const c = econColors[cl.topEcon] || '#ff6a00';
          return (
            <g key={cl.id}>
              <circle cx={sx} cy={sz} r={r} fill={c} opacity={0.07} />
              <circle cx={sx} cy={sz} r={r} fill="none" stroke={c} strokeOpacity="0.45" strokeWidth="0.6" strokeDasharray="2 3" />
              <text
                x={sx}
                y={sz - r - 4}
                fontFamily="Aldrich, sans-serif"
                fontSize="7"
                letterSpacing="1.2"
                fill={c}
                textAnchor="middle"
                opacity="0.85"
              >
                {cl.name.toUpperCase()} · {cl.topScore}
              </text>
            </g>
          );
        })}

        {/* ── LAYER 1: Region labels ───────────────────────── */}
        {layers.regions && regions.map((r) => {
          const sx = (r.x / 500) * (VB / 2);
          const sz = -(r.z / 500) * (VB / 2);
          return (
            <g key={r.id} opacity="0.6">
              <text
                x={sx} y={sz}
                fontFamily="Aldrich, sans-serif"
                fontSize="9" letterSpacing="2"
                fill="rgba(216,228,248,0.6)" textAnchor="middle"
              >
                {r.name.toUpperCase()}
              </text>
              <text
                x={sx} y={sz + 9}
                fontFamily="JetBrains Mono, monospace" fontSize="6.5"
                fill="rgba(216,228,248,0.35)" textAnchor="middle"
              >
                {(r.count / 1000).toFixed(0)}K · μ {r.avgScore}
              </text>
            </g>
          );
        })}

        {/* ── Sol marker ───────────────────────────────────── */}
        <g>
          <circle cx={0} cy={0} r="2" fill="#ffd54a" />
          <circle cx={0} cy={0} r="6" fill="none" stroke="#ffd54a" strokeOpacity="0.45" strokeWidth="0.5" />
          <text x={4} y={-3} fontFamily="JetBrains Mono, monospace" fontSize="6" fill="#ffd54a" opacity="0.8">SOL</text>
        </g>

        {/* ── LAYER 5+7: Systems + selection halo ─────────── */}
        {layers.systems && sysWithScreen.map((s) => {
          const tier = ratingTier(s.score);
          const isSel = s.id64 === selectedId;
          const r = isSel ? 4 : (s.score >= 80 ? 3 : 2.2);
          return (
            <g key={s.id64} className="cursor-pointer" onClick={() => onSelect(s)} style={{ pointerEvents: 'all' }}>
              {/* Glow halo for high-score systems */}
              {s.score >= 80 && (
                <circle cx={s.sx} cy={s.sz} r={r + 5} fill={tier.color} opacity="0.18" />
              )}
              {isSel && (
                <>
                  <circle cx={s.sx} cy={s.sz} r={r + 8} fill="none" stroke="#ff6a00" strokeWidth="0.8" opacity="0.85" />
                  <circle cx={s.sx} cy={s.sz} r={r + 12} fill="none" stroke="#ff6a00" strokeWidth="0.4" opacity="0.5" className="hud-pulse" />
                </>
              )}
              <circle cx={s.sx} cy={s.sz} r={r} fill={tier.color} />
              {(isSel || s.score >= 80) && (
                <text
                  x={s.sx + r + 3}
                  y={s.sz + 1}
                  fontFamily="JetBrains Mono, monospace"
                  fontSize="5.5"
                  fill={isSel ? '#ff9133' : tier.color}
                  opacity={isSel ? 1 : 0.8}
                >
                  {s.name}
                </text>
              )}
            </g>
          );
        })}

        {/* Reference crosshair (centred on Sol for the prototype) */}
        <g opacity="0.5">
          <line x1={-12} x2={-3} y1={0}   y2={0}   stroke="#ff6a00" strokeWidth="0.6" />
          <line x1={3}   x2={12}  y1={0}   y2={0}   stroke="#ff6a00" strokeWidth="0.6" />
          <line x1={0}   x2={0}   y1={-12} y2={-3}  stroke="#ff6a00" strokeWidth="0.6" />
          <line x1={0}   x2={0}   y1={3}   y2={12}  stroke="#ff6a00" strokeWidth="0.6" />
        </g>
      </svg>

      {/* Vignette */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)',
        }}
      />

      {/* Compass */}
      <div className="absolute top-3 left-3 glass rounded-sm px-2 py-1.5 font-mono text-[9px] text-[var(--steel-300)]">
        <div className="flex items-center gap-2">
          <span className="text-[var(--ed-orange-lt)]">↑ +Z</span>
          <span className="text-[var(--steel-500)]">→ +X</span>
        </div>
        <div className="text-[var(--steel-500)] mt-0.5">VIEW · {viewport}</div>
      </div>
    </div>
  );
}
