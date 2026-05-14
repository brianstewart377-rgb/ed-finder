import { useState } from 'react';
import type { OptimiserCandidate, OptimiserCandidatesResponse, RankedOptimiserCandidate } from '@/types/api';
import { OptimiserPlacementList } from './OptimiserPlacementList';
import { OptimiserRankingBreakdown } from './OptimiserRankingBreakdown';
import { formatScore, rankTone, strategyLabel } from './optimiserUtils';

export function OptimiserCandidateDetails({
  candidate,
  ranking,
  response,
  hasExistingPreviewPlan = false,
  onLoadCandidate,
}: {
  candidate?: OptimiserCandidate;
  ranking?: RankedOptimiserCandidate;
  response?: OptimiserCandidatesResponse | null;
  hasExistingPreviewPlan?: boolean;
  onLoadCandidate?: (candidate: OptimiserCandidate) => void;
}) {
  const [confirmingLoad, setConfirmingLoad] = useState(false);

  if (!candidate) {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-4 text-sm text-silver-dk">
        Select a generated candidate to inspect its rationale, placements, and ranking explanation.
      </div>
    );
  }

  const rankingReasons = ranking?.rank_breakdown.reasons ?? [];
  const responseAssumptions = response?.assumptions ?? [];

  const requestLoad = () => {
    if (!onLoadCandidate) return;
    if (hasExistingPreviewPlan) {
      setConfirmingLoad(true);
      return;
    }
    onLoadCandidate(candidate);
  };

  const confirmLoad = () => {
    if (!onLoadCandidate) return;
    onLoadCandidate(candidate);
    setConfirmingLoad(false);
  };

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

      {onLoadCandidate && (
        <div className="rounded-chunk-lg border border-orange/30 bg-orange/8 p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Load candidate</div>
          <p className="mt-1 text-[11px] text-silver-dk">
            Copies this candidate into the editable Simulation Preview. Nothing is committed in-game.
          </p>
          {confirmingLoad ? (
            <div className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2">
              <div className="text-xs font-semibold text-gold">Replace current preview plan with this optimiser candidate?</div>
              <p className="mt-1 text-[11px] text-silver-dk">
                This only replaces the editable preview placements. It does not save anything or affect in-game state.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmingLoad(false)}
                  className="rounded border border-border bg-bg3 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmLoad}
                  className="rounded border border-orange/50 bg-orange/15 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/25"
                >
                  Replace preview plan
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={requestLoad}
              className="mt-3 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 font-mono text-xs font-bold text-orange hover:bg-orange/25"
            >
              Load into preview
            </button>
          )}
        </div>
      )}

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
