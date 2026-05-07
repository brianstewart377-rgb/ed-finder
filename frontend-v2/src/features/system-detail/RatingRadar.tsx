import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts';
import type { SystemDetail } from '@/types/api';

/**
 * Hexagonal radar chart visualising a system's six economic suitability
 * scores (Agriculture / Refinery / Industrial / HighTech / Military /
 * Tourism). Designed to feel like a HUD readout on the cockpit dash —
 * gunmetal background, ED-orange polygon fill, silver labels.
 *
 * Renders nothing if every score is null.
 */
export function RatingRadar({ sys }: { sys: SystemDetail }) {
  const data = [
    { axis: 'AGRI',     value: sys.score_agriculture ?? 0, label: 'Agriculture' },
    { axis: 'REFI',     value: sys.score_refinery    ?? 0, label: 'Refinery' },
    { axis: 'INDU',     value: sys.score_industrial  ?? 0, label: 'Industrial' },
    { axis: 'HI-TECH',  value: sys.score_hightech    ?? 0, label: 'HighTech' },
    { axis: 'MIL',      value: sys.score_military    ?? 0, label: 'Military' },
    { axis: 'TOUR',     value: sys.score_tourism     ?? 0, label: 'Tourism' },
  ];

  const allZero = data.every((d) => !d.value);
  if (allZero) return null;

  // Highest-scoring axis (used to highlight the "suggested economy")
  const suggested = sys.economy_suggestion;
  const overall   = sys.score ?? 0;

  return (
    <div className="grid md:grid-cols-[1fr_auto] gap-5 items-center">
      {/* The radar */}
      <div className="relative w-full max-w-[460px] mx-auto md:mx-0 aspect-square">
        {/* Hex backplate glow */}
        <div
          className="absolute inset-0 rounded-chunk-xl pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at center, rgba(255,122,20,0.08) 0%, transparent 65%)',
          }}
        />
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%" margin={{ top: 18, right: 32, bottom: 18, left: 32 }}>
            {/* Concentric hex grid — gunmetal */}
            <PolarGrid
              stroke="rgba(200, 204, 209, 0.18)"
              strokeWidth={1}
              gridType="polygon"
            />
            <PolarAngleAxis
              dataKey="axis"
              tick={{
                fill: '#c8ccd1',
                fontSize: 11,
                fontFamily: 'Orbitron, monospace',
                fontWeight: 700,
                letterSpacing: '0.12em',
              }}
              tickLine={false}
              stroke="rgba(200, 204, 209, 0.35)"
            />
            <Radar
              dataKey="value"
              stroke="#ff7a14"
              strokeWidth={2}
              fill="#ff7a14"
              fillOpacity={0.32}
              dot={{ r: 3, fill: '#ff7a14', stroke: '#ffb074', strokeWidth: 1.5 }}
              isAnimationActive={true}
              animationDuration={650}
            />
          </RadarChart>
        </ResponsiveContainer>

        {/* Centre overall-score hex */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 grid place-items-center w-[88px] h-[88px] pointer-events-none"
          style={{
            clipPath:
              'polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)',
            background:
              'radial-gradient(circle at 30% 30%, rgba(40,44,50,0.95), rgba(14,16,20,0.95))',
            boxShadow: 'inset 0 0 0 1px rgba(255, 122, 20, 0.45), 0 0 24px -4px rgba(255,122,20,0.7)',
          }}
        >
          <span className="font-mono text-[9px] tracking-[0.2em] text-silver-dk uppercase">
            Overall
          </span>
          <span className="font-mono text-[28px] font-extrabold text-orange-lt tabular-nums leading-none mt-1">
            {overall}
          </span>
          <span className="font-mono text-[8px] tracking-widest text-silver-dk mt-0.5">
            / 100
          </span>
        </div>
      </div>

      {/* Score legend column */}
      <div className="space-y-1.5 min-w-[200px]">
        <div className="font-mono text-[10px] tracking-[0.18em] text-silver-dk uppercase pb-1.5 border-b border-border/60">
          Suitability profile
        </div>
        {data.map((d) => {
          const pct = Math.max(0, Math.min(100, d.value));
          const isSuggested = suggested && d.label === suggested;
          return (
            <div key={d.axis} className="grid grid-cols-[88px_1fr_28px] items-center gap-2 text-[11px] font-mono">
              <span
                className={[
                  'truncate',
                  isSuggested ? 'text-orange-lt font-bold' : 'text-silver',
                ].join(' ')}
              >
                {isSuggested && '★ '}{d.label}
              </span>
              <span
                className="block h-1.5 rounded-full overflow-hidden"
                style={{
                  background: 'linear-gradient(180deg, hsl(216 10% 12%), hsl(218 11% 8%))',
                  border: '1px solid hsl(216 10% 24%)',
                }}
              >
                <span
                  className="block h-full"
                  style={{
                    width: `${pct}%`,
                    background: isSuggested
                      ? 'linear-gradient(90deg, #ffb074, #ff7a14)'
                      : 'linear-gradient(90deg, #8a8f96, #c8ccd1)',
                    boxShadow: isSuggested ? '0 0 8px rgba(255,122,20,0.6)' : 'none',
                  }}
                />
              </span>
              <span
                className={[
                  'text-right tabular-nums',
                  isSuggested ? 'text-orange-lt font-bold' : 'text-silver-dk',
                ].join(' ')}
              >
                {pct}
              </span>
            </div>
          );
        })}
        {suggested && (
          <div className="pt-2 mt-2 border-t border-border/60 text-[10px] font-mono text-silver-dk">
            Suggested economy: <span className="text-orange-lt font-bold">{suggested}</span>
          </div>
        )}
      </div>
    </div>
  );
}
