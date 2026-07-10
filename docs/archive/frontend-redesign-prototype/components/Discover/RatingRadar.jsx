// Rating radar — the headline graphic of the rating engine.
// Recharts radar showing all 7 economy axes for a single system.
import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts';

export function RatingRadar({ breakdown, suggested, size = 200 }) {
  const data = Object.entries(breakdown).map(([k, v]) => ({
    axis: k.length > 7 ? k.slice(0, 7) : k,
    full: k,
    val: v,
    isSuggested: k === suggested?.replace(' ', ''),
  }));

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="76%">
          <PolarGrid gridType="polygon" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 9 }} />
          <Radar
            dataKey="val"
            stroke="#ff6a00"
            strokeWidth={1.2}
            fill="#ff6a00"
            fillOpacity={0.22}
            isAnimationActive={false}
          />
        </RadarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
        <div className="text-center">
          <div className="font-display text-[9px] tracking-[0.18em] text-[var(--steel-400)]">SUGGESTED</div>
          <div className="font-display text-[11px] tracking-[0.14em] text-[var(--ed-orange-lt)] text-glow-orange">
            {suggested || '—'}
          </div>
        </div>
      </div>
    </div>
  );
}

// Per-economy mini bars — shown inline on every result row
export function EconomyBars({ breakdown }) {
  const max = Math.max(...Object.values(breakdown));
  return (
    <div className="flex items-end gap-[2px] h-4">
      {Object.entries(breakdown).map(([k, v]) => {
        const pct = (v / 100) * 100;
        const isMax = v === max;
        return (
          <span
            key={k}
            title={`${k}: ${v}`}
            className="w-[5px] bg-[var(--steel-700)] rounded-[1px] relative"
            style={{ height: '100%' }}
          >
            <span
              className="absolute bottom-0 left-0 right-0 rounded-[1px]"
              style={{
                height: `${pct}%`,
                background: isMax ? 'var(--ed-orange)' : 'var(--steel-400)',
                boxShadow: isMax ? '0 0 4px rgba(255,106,0,0.5)' : 'none',
              }}
            />
          </span>
        );
      })}
    </div>
  );
}
