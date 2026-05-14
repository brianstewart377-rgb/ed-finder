import { useMemo, useState } from 'react';
import { fetchOptimiserCandidates } from '@/lib/api';
import type { OptimiserCandidate, OptimiserCandidatesResponse, RankedOptimiserCandidate, SimulateBuildPlacement } from '@/types/api';
import { OptimiserCandidateCard } from './OptimiserCandidateCard';
import { OptimiserCandidateDetails } from './OptimiserCandidateDetails';
import { OptimiserEmptyState } from './OptimiserEmptyState';
import { OptimiserErrorState } from './OptimiserErrorState';
import { buildRankLookup, sortCandidatesForDisplay } from './optimiserUtils';

export function OptimiserCandidatePanel({
  systemId64,
  targetArchetype,
  hasExistingPreviewPlan = false,
  onLoadCandidate,
  currentPreviewPlacements,
  currentTargetArchetype,
  currentPreviewLabel,
}: {
  systemId64: number;
  targetArchetype: string;
  hasExistingPreviewPlan?: boolean;
  onLoadCandidate?: (candidate: OptimiserCandidate) => void;
  currentPreviewPlacements?: SimulateBuildPlacement[];
  currentTargetArchetype?: string | null;
  currentPreviewLabel?: string;
}) {
  const [maxCandidates, setMaxCandidates] = useState(5);
  const [allowEstimatedData, setAllowEstimatedData] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<OptimiserCandidatesResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const rankLookup = useMemo(() => buildRankLookup(response?.ranking), [response]);
  const candidates = useMemo(
    () => sortCandidatesForDisplay(response?.candidates ?? [], response?.ranking),
    [response],
  );
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_id === selectedId) ?? candidates[0];

  const generateCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOptimiserCandidates({
        system_id64: systemId64,
        target_archetype: targetArchetype,
        max_candidates: maxCandidates,
        allow_estimated_data: allowEstimatedData,
        run_preview: true,
        include_ranking: true,
      });
      setResponse(data);
      setSelectedId(data.ranking?.ranked_candidates[0]?.candidate_id ?? data.candidates[0]?.candidate_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Candidate generation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-chunk-lg border border-orange/20 bg-bg1/55 p-4" aria-label="Optimiser candidates">
      <div className="mb-3 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Optimiser candidates</h3>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            {onLoadCandidate
              ? 'Generated and ranked suggestions. You can load a selected candidate into the editable preview. Nothing is committed in-game.'
              : 'Generated and ranked suggestions. Read-only for now — applying a candidate comes in a later stage.'}
          </p>
        </div>
      </div>

      <div className="mb-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
        <div className="rounded border border-border/50 bg-bg3/20 px-3 py-2 font-mono text-[11px] text-silver-dk">
          Target: <span className="text-silver">{targetArchetype}</span>
        </div>
        <label className="flex items-center gap-2 rounded border border-border/50 bg-bg3/20 px-3 py-2 font-mono text-[11px] text-silver-dk">
          Max
          <select
            value={maxCandidates}
            onChange={(event) => setMaxCandidates(Number(event.target.value))}
            className="h-7 rounded border border-border bg-bg2 px-2 text-silver"
          >
            {[3, 5, 8, 10].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void generateCandidates()}
          disabled={loading}
          className="rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 font-mono text-xs font-bold text-orange hover:bg-orange/25 disabled:opacity-45"
        >
          {loading ? 'Generating' : 'Generate candidates'}
        </button>
      </div>

      <label className="mb-3 flex items-center gap-2 font-mono text-[11px] text-silver-dk">
        <input
          type="checkbox"
          checked={allowEstimatedData}
          onChange={(event) => setAllowEstimatedData(event.target.checked)}
        />
        Include estimated data
      </label>

      {loading && (
        <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-xs text-silver-dk">
          Generating ranked optimiser candidates...
        </div>
      )}

      {error && <OptimiserErrorState message={error} onRetry={() => void generateCandidates()} />}

      {!loading && !error && !response && <OptimiserEmptyState />}
      {!loading && !error && response && response.candidates.length === 0 && (
        <OptimiserEmptyState warnings={response.warnings} assumptions={response.assumptions} />
      )}

      {!loading && !error && response && response.candidates.length > 0 && (
        <div className="grid gap-3 xl:grid-cols-[minmax(220px,0.85fr)_minmax(0,1.15fr)]">
          <div className="space-y-2">
            {candidates.map((candidate) => (
              <OptimiserCandidateCard
                key={candidate.candidate_id}
                candidate={candidate}
                ranking={rankLookup.get(candidate.candidate_id)}
                selected={candidate.candidate_id === selectedCandidate?.candidate_id}
                onSelect={() => setSelectedId(candidate.candidate_id)}
              />
            ))}
          </div>
          <OptimiserCandidateDetails
            candidate={selectedCandidate}
            ranking={selectedCandidate ? rankLookup.get(selectedCandidate.candidate_id) : undefined}
            response={response}
            hasExistingPreviewPlan={hasExistingPreviewPlan}
            onLoadCandidate={onLoadCandidate}
            currentPreviewPlacements={currentPreviewPlacements}
            currentTargetArchetype={currentTargetArchetype}
            currentPreviewLabel={currentPreviewLabel}
          />
        </div>
      )}
    </section>
  );
}

export function getRankForCandidate(
  lookup: Map<string, RankedOptimiserCandidate>,
  candidate: OptimiserCandidate,
): RankedOptimiserCandidate | undefined {
  return lookup.get(candidate.candidate_id);
}
