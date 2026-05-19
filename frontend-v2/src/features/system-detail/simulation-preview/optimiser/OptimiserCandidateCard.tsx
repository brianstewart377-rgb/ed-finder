import type { OptimiserCandidate, RankedOptimiserCandidate } from '@/types/api';
import { formatPercent, formatScore, rankTone, strategyLabel } from './optimiserUtils';
import { suggestedBuildPresentation } from './optimiserQualityUtils';

export function OptimiserCandidateCard({
  candidate,
  ranking,
  selected,
  onSelect,
}: {
  candidate: OptimiserCandidate;
  ranking?: RankedOptimiserCandidate;
  selected: boolean;
  onSelect: () => void;
}) {
  const summary = candidate.preview_summary;
  const warningCount = candidate.warnings.length + (summary?.warnings_count ?? 0);
  const presentation = suggestedBuildPresentation(candidate);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-chunk-lg border p-3 text-left transition ${selected ? 'border-orange bg-orange/10' : 'border-border/60 bg-bg2/45 hover:border-orange/45 hover:bg-bg3/45'}`}
      aria-pressed={selected}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {ranking && (
              <span className="rounded border border-orange/40 bg-orange/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-orange">
                #{ranking.rank}
              </span>
            )}
            {ranking && (
              <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] ${rankTone(ranking.rank_tier)}`}>
                {ranking.rank_tier}
              </span>
            )}
          </div>
          <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            {presentation.category}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span className="rounded border border-cyan/35 bg-cyan/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-cyan">
              {presentation.scaleLabel}
            </span>
            <span className="rounded border border-border/55 bg-bg3/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-silver-dk">
              {presentation.placementCount} placements
            </span>
            <span className="rounded border border-border/55 bg-bg3/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-silver-dk">
              {presentation.bodyCount || 1} bodies
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-silver-dk">{presentation.purpose}</p>
          <div className="mt-2 truncate text-sm font-semibold text-silver">{candidate.label}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            {strategyLabel(candidate.strategy)}
          </div>
        </div>
        {ranking && (
          <div className="shrink-0 text-right">
            <div className="font-mono text-lg font-bold text-orange">{formatScore(ranking.rank_score)}</div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">rank</div>
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 font-mono text-[10px]">
        <Metric label="Final" value={formatScore(summary?.final_score)} />
        <Metric label="Build" value={formatScore(summary?.buildability_score)} />
        <Metric label="Conf" value={formatPercent(summary?.confidence)} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[10px]">
        {warningCount > 0 && <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 text-gold">{warningCount} warning(s)</span>}
        {summary?.cp_negative && <span className="rounded border border-red/35 bg-red/10 px-1.5 py-0.5 text-red">CP risk</span>}
        {!summary && <span className="rounded border border-border bg-bg3 px-1.5 py-0.5 text-silver-dk">No preview summary</span>}
      </div>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border/45 bg-bg3/25 px-2 py-1">
      <div className="text-silver-dk">{label}</div>
      <div className="text-silver">{value}</div>
    </div>
  );
}
