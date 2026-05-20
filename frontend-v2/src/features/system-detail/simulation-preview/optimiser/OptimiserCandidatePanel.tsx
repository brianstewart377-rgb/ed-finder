import { useEffect, useMemo, useState } from 'react';
import { fetchOptimiserCandidates } from '@/lib/api';
import type { OptimiserCandidate, OptimiserCandidatesResponse, RankedOptimiserCandidate, SimulateBuildPlacement } from '@/types/api';
import { OptimiserCandidateCard } from './OptimiserCandidateCard';
import { OptimiserCandidateDetails } from './OptimiserCandidateDetails';
import { OptimiserEmptyState } from './OptimiserEmptyState';
import { OptimiserErrorState } from './OptimiserErrorState';
import { buildRankLookup, sortCandidatesForDisplay } from './optimiserUtils';
import { filterUsefulSuggestedBuilds, suggestedBuildScale, type SuggestedBuildScale } from './optimiserQualityUtils';
import { humanizeArchetype } from '@/features/colony-planner/workspaceUtils';

type GeneratedCandidateParams = {
  targetArchetype: string;
  maxCandidates: number;
  allowEstimatedData: boolean;
  scale: SuggestedBuildScaleFilter;
};

type SuggestedBuildScaleFilter = 'starter' | 'expansion' | 'full';

export function OptimiserCandidatePanel({
  systemId64,
  targetArchetype,
  hasExistingPreviewPlan = false,
  onLoadCandidate,
  onCandidateSelect,
  bodyLabelsById,
  currentPreviewPlacements,
  currentTargetArchetype,
  currentPreviewLabel,
}: {
  systemId64: number;
  targetArchetype: string;
  hasExistingPreviewPlan?: boolean;
  onLoadCandidate?: (candidate: OptimiserCandidate) => void;
  onCandidateSelect?: (candidate: OptimiserCandidate | null) => void;
  bodyLabelsById?: Record<string, string>;
  currentPreviewPlacements?: SimulateBuildPlacement[];
  currentTargetArchetype?: string | null;
  currentPreviewLabel?: string;
}) {
  const [maxCandidates, setMaxCandidates] = useState(5);
  const [allowEstimatedData, setAllowEstimatedData] = useState(true);
  const [scale, setScale] = useState<SuggestedBuildScaleFilter>('expansion');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<OptimiserCandidatesResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generatedParams, setGeneratedParams] = useState<GeneratedCandidateParams | null>(null);

  const rankLookup = useMemo(() => buildRankLookup(response?.ranking), [response]);
  const allUsefulCandidates = useMemo(
    () => filterUsefulSuggestedBuilds(sortCandidatesForDisplay(response?.candidates ?? [], response?.ranking)),
    [response],
  );
  const candidates = useMemo(
    () => allUsefulCandidates.filter((candidate) => scaleMatchesFilter(suggestedBuildScale(candidate), scale)),
    [allUsefulCandidates, scale],
  );
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_id === selectedId) ?? candidates[0];
  const currentParams: GeneratedCandidateParams = { targetArchetype, maxCandidates, allowEstimatedData, scale };
  const controlsChangedSinceGeneration = Boolean(generatedParams && (
    generatedParams.targetArchetype !== currentParams.targetArchetype
    || generatedParams.maxCandidates !== currentParams.maxCandidates
    || generatedParams.allowEstimatedData !== currentParams.allowEstimatedData
    || generatedParams.scale !== currentParams.scale
  ));

  useEffect(() => {
    onCandidateSelect?.(selectedCandidate ?? null);
  }, [onCandidateSelect, selectedCandidate]);

  const generateCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const requestParams = { ...currentParams };
      const data = await fetchOptimiserCandidates({
        system_id64: systemId64,
        target_archetype: requestParams.targetArchetype,
        max_candidates: requestParams.maxCandidates,
        allow_estimated_data: requestParams.allowEstimatedData,
        run_preview: true,
        include_ranking: true,
      });
      setGeneratedParams(requestParams);
      setResponse(data);
      setSelectedId(data.ranking?.ranked_candidates[0]?.candidate_id ?? data.candidates[0]?.candidate_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Candidate generation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-chunk-lg border border-orange/20 bg-bg1/55 p-4" aria-label="Suggested Builds">
      <div className="mb-3 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">Suggested Builds</h3>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            Generate Suggested Builds to get possible build plans for this system and goal. The workspace filters generated candidates for usefulness before display, so trivial backend candidates may be hidden. Nothing is saved or committed in-game.
          </p>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            {onLoadCandidate
              ? 'Load a useful suggested build deliberately when you want to review it as the editable Build Plan.'
              : 'Review suggested builds here without changing the editable Build Plan.'}
          </p>
        </div>
      </div>

      <div className="mb-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
        <div className="rounded border border-border/50 bg-bg3/20 px-3 py-2 font-mono text-[11px] text-silver-dk">
          Target: <span className="text-silver">{humanizeArchetype(targetArchetype)}</span>
        </div>
        <div className="inline-flex items-center rounded border border-border/70 bg-bg2/60 p-1" role="group" aria-label="Suggested build scale">
          {([
            ['starter', 'Starter'],
            ['expansion', 'Expansion'],
            ['full', 'Full / Ambitious'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={scale === value}
              onClick={() => setScale(value)}
              className={[
                'rounded px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em]',
                scale === value ? 'bg-orange/18 text-orange' : 'text-silver-dk hover:text-silver',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
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
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => void generateCandidates()}
            disabled={loading}
            data-testid="generate-suggested-builds"
            className="rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 font-mono text-xs font-bold text-orange hover:bg-orange/25 disabled:opacity-45"
          >
            {loading ? 'Generating' : 'Generate Suggested Builds'}
          </button>
          <p className="max-w-xs font-mono text-[10px] leading-snug text-silver-dk">
            Generates bounded suggested build plans and lightweight preview summaries. It does not run the main Simulation Preview or change your current Build Plan.
          </p>
        </div>
      </div>

      <label className="mb-1 flex items-center gap-2 font-mono text-[11px] text-silver-dk">
        <input
          type="checkbox"
          checked={allowEstimatedData}
          onChange={(event) => setAllowEstimatedData(event.target.checked)}
        />
        Include estimated data
      </label>
      <p className="mb-3 max-w-2xl font-mono text-[10px] leading-snug text-silver-dk">
        Allows Suggested Builds to use inferred or incomplete data when exact data is unavailable. This can produce more suggestions, but confidence and warnings should be reviewed.
      </p>

      {generatedParams && (
        <div className="mb-3 rounded border border-cyan/35 bg-cyan/5 px-3 py-2 font-mono text-[10px] leading-snug text-silver-dk">
          <div className="uppercase tracking-[0.16em] text-cyan">Generated for</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <span>Target: <span className="text-silver">{humanizeArchetype(generatedParams.targetArchetype)}</span></span>
            <span>Scale: <span className="text-silver">{scaleLabel(generatedParams.scale)}</span></span>
            <span>Max suggested builds: <span className="text-silver">{generatedParams.maxCandidates}</span></span>
            <span>Estimated data: <span className="text-silver">{generatedParams.allowEstimatedData ? 'on' : 'off'}</span></span>
          </div>
        </div>
      )}

      {controlsChangedSinceGeneration && generatedParams && (
        <div className="mb-3 rounded border border-gold/55 bg-gold/12 px-3 py-2 font-mono text-[11px] leading-snug text-gold">
          <div className="font-bold">Controls have changed since these suggested builds were generated. Generate again to refresh suggested builds before comparing or copying.</div>
          <div className="mt-2 grid gap-1 text-[10px] text-silver-dk sm:grid-cols-3">
            <span>Generated target: <span className="text-silver">{humanizeArchetype(generatedParams.targetArchetype)}</span></span>
            <span>Generated scale: <span className="text-silver">{scaleLabel(generatedParams.scale)}</span></span>
            <span>Generated max: <span className="text-silver">{generatedParams.maxCandidates}</span></span>
            <span>Generated estimated data: <span className="text-silver">{generatedParams.allowEstimatedData ? 'on' : 'off'}</span></span>
            <span>Current target: <span className="text-silver">{humanizeArchetype(currentParams.targetArchetype)}</span></span>
            <span>Current scale: <span className="text-silver">{scaleLabel(currentParams.scale)}</span></span>
            <span>Current max: <span className="text-silver">{currentParams.maxCandidates}</span></span>
            <span>Current estimated data: <span className="text-silver">{currentParams.allowEstimatedData ? 'on' : 'off'}</span></span>
          </div>
        </div>
      )}

      {loading && (
        <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-xs text-silver-dk">
          Generating ranked Suggested Builds...
        </div>
      )}

      {error && <OptimiserErrorState message={error} onRetry={() => void generateCandidates()} />}

      {!loading && !error && !response && <OptimiserEmptyState />}
      {!loading && !error && response && response.candidates.length === 0 && (
        <OptimiserEmptyState warnings={response.warnings} assumptions={response.assumptions} />
      )}
      {!loading && !error && response && response.candidates.length > 0 && candidates.length === 0 && (
        <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 font-mono text-xs text-silver-dk">
          No useful {scaleLabel(scale).toLowerCase()} suggested builds are available yet. Change scale or generate again with different controls.
        </div>
      )}

      {!loading && !error && response && response.candidates.length > 0 && candidates.length > 0 && (
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
            controlsChangedSinceGeneration={controlsChangedSinceGeneration}
            generatedTargetArchetype={generatedParams?.targetArchetype ?? null}
            currentControlTargetArchetype={currentParams.targetArchetype}
            bodyLabelsById={bodyLabelsById}
          />
        </div>
      )}
    </section>
  );
}

function scaleMatchesFilter(scale: SuggestedBuildScale, filter: SuggestedBuildScaleFilter) {
  if (filter === 'starter') return scale === 'starter' || scale === 'bootstrap';
  if (filter === 'expansion') return scale === 'starter' || scale === 'expansion' || scale === 'full';
  return scale === 'expansion' || scale === 'full';
}

function scaleLabel(scale: SuggestedBuildScaleFilter) {
  if (scale === 'starter') return 'Starter';
  if (scale === 'expansion') return 'Expansion';
  return 'Full / Ambitious';
}

export function getRankForCandidate(
  lookup: Map<string, RankedOptimiserCandidate>,
  candidate: OptimiserCandidate,
): RankedOptimiserCandidate | undefined {
  return lookup.get(candidate.candidate_id);
}
