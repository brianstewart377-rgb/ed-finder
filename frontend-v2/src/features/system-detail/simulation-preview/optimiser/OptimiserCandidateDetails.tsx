import type { OptimiserCandidate, OptimiserCandidatesResponse, RankedOptimiserCandidate } from '@/types/api';
import { OptimiserPlacementList } from './OptimiserPlacementList';
import { OptimiserRankingBreakdown } from './OptimiserRankingBreakdown';
import { formatScore, rankTone, strategyLabel } from './optimiserUtils';

export function OptimiserCandidateDetails({
  candidate,
  ranking,
  response,
}: {
  candidate?: OptimiserCandidate;
  ranking?: RankedOptimiserCandidate;
  response?: OptimiserCandidatesResponse | null;
}) {
  if (!candidate) {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-4 text-sm text-silver-dk">
        Select a generated candidate to inspect its rationale, placements, and ranking explanation.
      </div>
    );
  }

  const rankingReasons = ranking?.rank_breakdown.reasons ?? [];
  const responseAssumptions = response?.assumptions ?? [];

  return (
    <div className="space-y-3 rounded-chunk-lg border border-border/60 bg-bg1/45 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm font-semibold text-silver">{candidate.label}</h4>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            {strategyLabel(candidate.strategy)}
          </div>
        </div>
        {ranking && (
          <div className="flex items-center gap-2">
            <span className={`rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] ${rankTone(ranking.rank_tier)}`}>
              {ranking.rank_tier}
            </span>
            <span className="font-mono text-sm font-bold text-orange">{formatScore(ranking.rank_score)}</span>
          </div>
        )}
      </div>

      {candidate.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {candidate.tags.map((tag) => (
            <span key={tag} className="rounded border border-border/50 bg-bg3/30 px-1.5 py-0.5 font-mono text-[10px] text-silver-dk">
              {tag}
            </span>
          ))}
        </div>
      )}

      <Section title="Rationale" items={candidate.rationale} empty="No rationale was returned for this candidate." />
      <Section
        title="Warnings"
        items={[
          ...candidate.warnings,
          ...(candidate.preview_summary?.warnings_count ? [`Preview summary reported ${candidate.preview_summary.warnings_count} warning(s).`] : []),
        ]}
        empty="No candidate warnings."
      />
      <Section
        title="Ranking reasons"
        items={rankingReasons}
        empty="No ranking-specific reasons were returned."
      />
      <Section
        title="Assumptions"
        items={[...candidate.assumptions, ...responseAssumptions]}
        empty="No additional assumptions were returned."
      />

      <div>
        <h5 className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Placements</h5>
        <OptimiserPlacementList placements={candidate.placements} />
      </div>

      <OptimiserRankingBreakdown breakdown={ranking?.rank_breakdown} />
    </div>
  );
}

function Section({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded border border-border/45 bg-bg3/20 px-3 py-2">
      <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">{title}</h5>
      {items.length > 0 ? (
        <ul className="mt-1 space-y-1 text-[11px] text-silver-dk">
          {items.map((item, index) => <li key={`${title}-${index}-${item}`}>• {item}</li>)}
        </ul>
      ) : (
        <div className="mt-1 text-[11px] text-silver-dk">{empty}</div>
      )}
    </div>
  );
}
