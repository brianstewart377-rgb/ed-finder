import type { OptimiserRankBreakdown } from '@/types/api';
import { formatScore } from './optimiserUtils';

const CONTRIBUTIONS: Array<[keyof OptimiserRankBreakdown, string]> = [
  ['preview_score_component', 'Preview final score'],
  ['composition_component', 'Composition'],
  ['buildability_component', 'Buildability'],
  ['confidence_component', 'Confidence'],
  ['alignment_component', 'Top-two alignment'],
  ['strategy_modifier', 'Strategy modifier'],
];

const PENALTIES: Array<[keyof OptimiserRankBreakdown, string]> = [
  ['warning_penalty', 'Warning penalty'],
  ['cp_penalty', 'CP penalty'],
];

export function OptimiserRankingBreakdown({ breakdown }: { breakdown?: OptimiserRankBreakdown | null }) {
  if (!breakdown) {
    return (
      <div className="rounded border border-border/60 bg-bg3/25 px-3 py-2 text-[11px] text-silver-dk">
        No ranking breakdown is available for this candidate.
      </div>
    );
  }

  return (
    <div className="rounded-chunk-lg border border-border/60 bg-bg2/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Ranking breakdown</h5>
        <div className="font-mono text-sm font-bold text-orange">{formatScore(breakdown.total_score)}</div>
      </div>
      <div className="mt-3 grid gap-1.5 font-mono text-[11px]">
        {CONTRIBUTIONS.map(([key, label]) => (
          <div key={key} className="flex justify-between gap-3 rounded border border-border/40 bg-bg3/20 px-2 py-1">
            <span className="text-silver-dk">{label}</span>
            <span className="text-silver">+{formatScore(Number(breakdown[key] ?? 0))}</span>
          </div>
        ))}
        {PENALTIES.map(([key, label]) => {
          const value = Number(breakdown[key] ?? 0);
          return (
            <div key={key} className="flex justify-between gap-3 rounded border border-gold/25 bg-gold/5 px-2 py-1">
              <span className="text-gold">{label}</span>
              <span className={value < 0 ? 'text-gold' : 'text-silver-dk'}>{formatScore(value)}</span>
            </div>
          );
        })}
      </div>
      {breakdown.reasons.length > 0 && (
        <div className="mt-3 rounded border border-border/50 bg-bg3/20 px-2 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Reasons</div>
          <ul className="mt-1 space-y-1 text-[11px] text-silver-dk">
            {breakdown.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
