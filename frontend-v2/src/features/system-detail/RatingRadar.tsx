import { useState } from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts';
import { ChevronDown } from 'lucide-react';
import type { SystemDetail } from '@/types/api';
import { formatConfidence } from '@/lib/format';
import { displayRationale } from '@/lib/rationale';
import { economyColor, economySoftColor, normaliseCoreEconomy } from '@/features/colony-planner/economyVisuals';

/**
 * Rating breakdown JSON shape produced by `build_ratings.py`. Stored in
 * `score_breakdown` JSONB column and surfaced via `RatingModel.breakdown`.
 */
interface RatingBreakdown {
  economies?: Record<string, number>;
  dimensions?: {
    slots?: number;
    strategic?: number;
    safety?: number;
    terraforming?: number;
    diversity?: number;
  };
  top_pair?: {
    a?: string;
    b?: string;
    a_score?: number;
    b_score?: number;
    pair_score?: number;
  };
  primary_economy?: string;
  secondary_economy?: string;
  has_standout?: boolean;
  rationale?: string;
  confidence?: number;
  rating_version?: string;
}

function parseBreakdown(raw: unknown): RatingBreakdown | null {
  if (!raw || typeof raw !== 'object') return null;
  return raw as RatingBreakdown;
}

/**
 * Rich rating profile for a system. Shows:
 *  - Best-build potential headline with score meaning
 *  - Economy radar (7 axes including Extraction)
 *  - Economy suitability bars
 *  - Top complementary pair
 *  - Confidence
 *  - Rationale
 *  - Expandable dimension breakdown (slots/strategic/safety/terraforming/diversity)
 *
 * Renders nothing if every score is null.
 */
export function RatingRadar({ sys }: { sys: SystemDetail }) {
  const [expanded, setExpanded] = useState(false);

  const economyScores = [
    { axis: 'AGRI',     value: sys.score_agriculture ?? 0, label: 'Agriculture' },
    { axis: 'REFI',     value: sys.score_refinery    ?? 0, label: 'Refinery' },
    { axis: 'INDU',     value: sys.score_industrial  ?? 0, label: 'Industrial' },
    { axis: 'HI-TECH',  value: sys.score_hightech    ?? 0, label: 'HighTech' },
    { axis: 'MIL',      value: sys.score_military    ?? 0, label: 'Military' },
    { axis: 'TOUR',     value: sys.score_tourism     ?? 0, label: 'Tourism' },
    { axis: 'EXTR',     value: sys.score_extraction  ?? 0, label: 'Extraction' },
  ];

  const allZero = economyScores.every((d) => !d.value);
  if (allZero) return null;

  const suggested = sys.economy_suggestion;
  const overall   = sys.score ?? 0;
  const conf      = formatConfidence(sys.confidence);
  const rationale = displayRationale(sys.rationale);

  // Parse the richer breakdown from the score_breakdown JSONB column.
  // SystemDetail uses snake_case; the field comes through as an indexed
  // property via the `& { [key: string]: unknown }` intersection.
  const bd = parseBreakdown((sys as Record<string, unknown>).score_breakdown);
  const ratingVersion = sys.rating_version ?? bd?.rating_version ?? null;
  const cappedEconomies = economyScores.filter((d) => d.value >= 100).length;
  const topPair = bd?.top_pair;
  const dims = bd?.dimensions;
  const primaryEco = bd?.primary_economy ?? sys.primary_economy;
  const secondaryEco = bd?.secondary_economy ?? sys.secondary_economy;

  return (
    <div data-testid="rating-profile" className="space-y-4">
      {/* ── Headline: Best-build potential ─────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div data-testid="rating-headline" className="font-mono text-[10px] tracking-[0.18em] text-silver-dk uppercase">
            Best-build potential
          </div>
          <div className="flex items-baseline gap-2 mt-0.5">
            <span data-testid="rating-overall-score" className="font-mono text-[32px] font-extrabold text-orange-lt tabular-nums leading-none">
              {overall}
            </span>
            <span className="font-mono text-[11px] text-silver-dk">/ 100</span>
          </div>
        </div>

        {conf && (
          <span
            data-testid="rating-confidence"
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{
              borderColor: conf.tier === 'High' ? 'rgba(61,220,132,0.5)' : conf.tier === 'Medium' ? 'rgba(250,204,21,0.5)' : 'rgba(239,68,68,0.5)',
              color: conf.tier === 'High' ? '#3ddc84' : conf.tier === 'Medium' ? '#facc15' : '#ef4444',
            }}
            title={`Rating confidence: ${conf.tier} (${conf.pct}%)`}
          >
            {conf.symbol} {conf.tier} confidence ({conf.pct}%)
          </span>
        )}
        {!conf && (
          <span data-testid="rating-confidence-missing" className="rounded border border-border/50 px-2 py-1 font-mono text-[10px] text-silver-dk">
            Confidence unknown
          </span>
        )}
      </div>

      <p className="font-mono text-[10px] text-silver-dk leading-snug">
        Based on body mix, economy fit, strategic value, and slot potential. Run planner / Preview to validate an actual build.
      </p>

      {(cappedEconomies >= 3 || !ratingVersion) && (
        <p data-testid="rating-caveat" className="font-mono text-[10px] leading-snug text-gold">
          {cappedEconomies >= 3
            ? 'Several economy scores are capped; treat their exact ordering as uncertain until the rating is refreshed.'
            : 'This rating predates the current scoring contract; treat the economy order as approximate.'}
        </p>
      )}

      {/* ── Top pair + primary/secondary ──────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-[11px] font-mono">
        {topPair?.a && topPair?.b && (
          <span data-testid="rating-top-pair" className="rounded border border-orange/40 bg-orange/10 px-2.5 py-1 text-orange-lt">
            Top pair: <strong>{topPair.a} + {topPair.b}</strong>
            {topPair.pair_score != null && <span className="text-silver-dk ml-1">({topPair.pair_score})</span>}
          </span>
        )}
        {primaryEco && (
          <span className="rounded border border-border/50 bg-bg3/30 px-2 py-1 text-silver">
            Primary: <span className="text-orange-lt font-bold">{primaryEco}</span>
          </span>
        )}
        {secondaryEco && secondaryEco !== 'None' && (
          <span className="rounded border border-border/50 bg-bg3/30 px-2 py-1 text-silver">
            Secondary: <span className="text-silver-lt font-bold">{secondaryEco}</span>
          </span>
        )}
      </div>

      {/* ── Rationale ─────────────────────────────────────────────── */}
      {rationale && (
        <p data-testid="rating-rationale" className="text-silver-dk italic leading-snug text-[12px] font-mono border-l-2 border-orange/30 pl-3">
          {rationale}
        </p>
      )}

      {/* ── Radar + economy bars ──────────────────────────────────── */}
      <div className="grid md:grid-cols-[1fr_auto] gap-5 items-center">
        {/* The radar */}
        <div className="relative w-full max-w-[420px] mx-auto md:mx-0 aspect-square">
          <div
            className="absolute inset-0 rounded-chunk-xl pointer-events-none"
            style={{
              background:
                'radial-gradient(ellipse at center, rgba(255,122,20,0.08) 0%, transparent 65%)',
            }}
          />
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={economyScores} outerRadius="68%" margin={{ top: 18, right: 32, bottom: 18, left: 32 }}>
              <PolarGrid
                stroke="rgba(200, 204, 209, 0.18)"
                strokeWidth={1}
                gridType="polygon"
              />
              <PolarAngleAxis
                dataKey="axis"
                tick={{
                  fill: '#c8ccd1',
                  fontSize: 10,
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
        </div>

        {/* Economy bars */}
        <div className="space-y-1.5 min-w-[220px]">
          <div className="font-mono text-[10px] tracking-[0.18em] text-silver-dk uppercase pb-1.5 border-b border-border/60">
            Economy suitability
          </div>
          {economyScores.map((d) => {
            const pct = Math.max(0, Math.min(100, d.value));
            const isSuggested = suggested && d.label === suggested;
            const economy = normaliseCoreEconomy(d.label);
            const color = economyColor(economy);
            return (
              <div key={d.axis} className="grid grid-cols-[88px_1fr_28px] items-center gap-2 text-[11px] font-mono">
                <span
                  data-testid={`rating-economy-${d.label.toLowerCase()}`}
                  className={[
                    'truncate',
                    isSuggested ? 'text-orange-lt font-bold' : 'text-silver',
                  ].join(' ')}
                >
                  {isSuggested && '★ '}{d.label}
                </span>
                <span
                  data-testid={`rating-economy-bar-${d.label.toLowerCase()}`}
                  className="block h-2 rounded-full overflow-hidden"
                  style={{
                    background: economySoftColor(economy),
                    border: `1px solid ${color}66`,
                  }}
                >
                  <span
                    data-economy-color={color}
                    className="block h-full"
                    style={{
                      width: `${pct}%`,
                      background: color,
                      boxShadow: isSuggested ? `0 0 8px ${color}99` : 'none',
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

      {/* ── Expandable dimension breakdown ────────────────────────── */}
      {dims && (
        <div className="border-t border-border/40 pt-2">
          <button
            type="button"
            data-testid="rating-breakdown-toggle"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk hover:text-silver"
          >
            Score breakdown
            <ChevronDown size={12} className={expanded ? 'rotate-180 transition-transform' : 'transition-transform'} />
          </button>
          {expanded && (
            <div data-testid="rating-breakdown-panel" className="mt-2 space-y-1.5">
              {dimensionBar('Slots', dims.slots)}
              {dimensionBar('Strategic', dims.strategic)}
              {dimensionBar('Safety', dims.safety)}
              {dimensionBar('Terraforming', dims.terraforming)}
              {dimensionBar('Diversity', dims.diversity)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function dimensionBar(label: string, value: number | undefined | null) {
  const v = value ?? 0;
  const pct = Math.max(0, Math.min(100, v));
  return (
    <div data-testid={`rating-dim-${label.toLowerCase()}`} className="grid grid-cols-[100px_1fr_32px] items-center gap-2 text-[10px] font-mono">
      <span className="text-silver truncate">{label}</span>
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
            background: 'linear-gradient(90deg, #66b3ff, #3399ff)',
          }}
        />
      </span>
      <span className="text-right tabular-nums text-silver-dk">{v}</span>
    </div>
  );
}
