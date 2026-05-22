import { useMemo, useState } from 'react';
import type { FacilityTemplate, OptimiserCandidate, OptimiserCandidatesResponse, RankedOptimiserCandidate, SimulateBuildPlacement } from '@/types/api';
import { PlanningEconomyStrip } from '@/features/colony-planner/PlanningEconomyStrip';
import { bodyIdKey } from '../bodyIdUtils';
import { buildPlanningEconomyLedger } from '@/features/colony-planner/planningEconomy';
import { OptimiserPlacementList } from './OptimiserPlacementList';
import { OptimiserRankingBreakdown } from './OptimiserRankingBreakdown';
import { OptimiserComparisonPanel, compareBuildSources, sourceFromCurrentPreview, sourceFromOptimiserCandidate } from './comparison';
import { formatScore, rankTone, strategyLabel } from './optimiserUtils';
import { suggestedBuildPresentation } from './optimiserQualityUtils';

export function OptimiserCandidateDetails({
  candidate,
  ranking,
  response,
  hasExistingPreviewPlan = false,
  onLoadCandidate,
  currentPreviewPlacements,
  currentTargetArchetype,
  currentPreviewLabel = 'Current Build Plan',
  controlsChangedSinceGeneration = false,
  generatedTargetArchetype,
  currentControlTargetArchetype,
  bodyLabelsById,
  templates = [],
}: {
  candidate?: OptimiserCandidate;
  ranking?: RankedOptimiserCandidate;
  response?: OptimiserCandidatesResponse | null;
  hasExistingPreviewPlan?: boolean;
  onLoadCandidate?: (candidate: OptimiserCandidate) => void;
  currentPreviewPlacements?: SimulateBuildPlacement[];
  currentTargetArchetype?: string | null;
  currentPreviewLabel?: string;
  controlsChangedSinceGeneration?: boolean;
  generatedTargetArchetype?: string | null;
  currentControlTargetArchetype?: string | null;
  bodyLabelsById?: Record<string, string>;
  templates?: FacilityTemplate[];
}) {
  const [loadConfirmation, setLoadConfirmation] = useState<'replace' | 'stale' | 'stale_replace' | null>(null);
  const comparison = useMemo(() => {
    if (!candidate || !currentPreviewPlacements || currentPreviewPlacements.length === 0) {
      return null;
    }
    return compareBuildSources(
      sourceFromCurrentPreview({
        label: currentPreviewLabel,
        targetArchetype: currentTargetArchetype,
        placements: currentPreviewPlacements,
      }),
      sourceFromOptimiserCandidate(candidate, ranking),
    );
  }, [candidate, currentPreviewLabel, currentPreviewPlacements, currentTargetArchetype, ranking]);

  if (!candidate) {
    return (
      <div className="rounded-chunk-lg border border-border/60 bg-bg3/25 p-4 text-sm text-silver-dk">
        Select a suggested build to inspect its rationale, placements, and ranking explanation.
      </div>
    );
  }

  const rankingReasons = ranking?.rank_breakdown.reasons ?? [];
  const responseAssumptions = response?.assumptions ?? [];
  const presentation = suggestedBuildPresentation(candidate);
  const usedBodyIds = Array.from(new Set(
    candidate.placements
      .map((placement) => placement.local_body_id ?? '')
      .filter((bodyId) => Boolean(bodyId)),
  ));
  const labelForBodyId = (bodyId: string) => bodyLabelsById?.[bodyId] ?? bodyLabelsById?.[bodyIdKey(bodyId)] ?? `Body ${bodyId}`;
  const usedBodyNames = usedBodyIds.map(labelForBodyId);
  const mainBodyId = candidate.placements.find((placement) => placement.is_primary_port)?.local_body_id
    ?? usedBodyIds[0]
    ?? null;
  const mainBodyLabel = mainBodyId ? labelForBodyId(mainBodyId) : null;
  const supportBodyLabels = usedBodyIds
    .filter((bodyId) => bodyId !== mainBodyId)
    .map(labelForBodyId);
  const projectedEconomyLedger = buildPlanningEconomyLedger({
    projectedPlacements: candidate.placements.map((placement) => ({
      facility_template_id: placement.facility_template_id,
      local_body_id: placement.local_body_id,
      is_primary_port: placement.is_primary_port,
      build_order: placement.build_order,
    })),
    templates,
  });

  const requestLoad = () => {
    if (!onLoadCandidate) return;
    if (controlsChangedSinceGeneration) {
      setLoadConfirmation(hasExistingPreviewPlan ? 'stale_replace' : 'stale');
      return;
    }
    if (hasExistingPreviewPlan) {
      setLoadConfirmation('replace');
      return;
    }
    onLoadCandidate(candidate);
  };

  const confirmLoad = () => {
    if (!onLoadCandidate) return;
    onLoadCandidate(candidate);
    setLoadConfirmation(null);
  };

  const cancelLoad = () => setLoadConfirmation(null);

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
          {presentation.tags.map((tag) => (
            <span key={tag} className="rounded border border-border/50 bg-bg3/30 px-1.5 py-0.5 font-mono text-[10px] text-silver-dk">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-2 md:grid-cols-2">
        <SummaryBox title="What this build is for" body={presentation.purpose} />
        <SummaryBox title="Why suggested" body={presentation.reason} />
        <SummaryBox title="Tradeoff" body={presentation.tradeoff} />
        <SummaryBox title="Next action" body={presentation.nextAction} />
      </div>

      <div className="rounded border border-orange/25 bg-orange/8 px-3 py-2">
        <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Plan scale</h5>
        <p className="mt-1 text-[11px] text-silver-dk">
          <span className="text-silver">{presentation.scaleLabel}</span> scale: {presentation.placementCount} placements across {presentation.bodyCount || 1} body/bodies.
        </p>
        <p className="mt-1 text-[11px] text-silver-dk">{presentation.scaleReason}</p>
      </div>

      <div className="rounded border border-cyan/25 bg-cyan/5 px-3 py-2">
        <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Projected layout</h5>
        <p className="mt-1 text-[11px] text-silver-dk">
          {usedBodyNames.length > 0 ? `This plan uses: ${usedBodyNames.join(', ')}` : 'This plan has no explicit body assignments yet.'}
        </p>
        {mainBodyLabel && (
          <p className="mt-1 text-[11px] text-silver-dk">
            Main station candidate: <span className="text-silver">{mainBodyLabel}</span>
          </p>
        )}
        {supportBodyLabels.length > 0 && (
          <p className="mt-1 text-[11px] text-silver-dk">
            Support bodies: <span className="text-silver">{supportBodyLabels.join(', ')}</span>
          </p>
        )}
        <div className="mt-2">
          <PlanningEconomyStrip
            ledger={projectedEconomyLedger}
            compact
            testId="candidate-projected-economy"
          />
        </div>
      </div>

      <Section title="Rationale" items={candidate.rationale} empty="No rationale was returned for this suggested build." />
      <Section
        title="Warnings"
        items={[
          ...candidate.warnings,
          ...(candidate.preview_summary?.warnings_count ? [`Preview summary reported ${candidate.preview_summary.warnings_count} warning(s).`] : []),
        ]}
        empty="No suggested-build warnings."
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

      {controlsChangedSinceGeneration && (
        <div className="rounded-chunk-lg border border-gold/45 bg-gold/10 p-3 font-mono text-[11px] leading-snug text-gold">
          These suggested builds may not match the current Build Plan target/settings. Copying is still possible, but requires confirmation because the suggested build was generated from older controls.
          {generatedTargetArchetype && currentControlTargetArchetype && generatedTargetArchetype !== currentControlTargetArchetype && (
            <div className="mt-1 text-[10px] text-silver-dk">
              Generated target differs from the current Build Plan target. Generate Suggested Builds again for the current target before relying on comparison.
            </div>
          )}
        </div>
      )}

      {onLoadCandidate && (
        <div className="rounded-chunk-lg border border-orange/30 bg-orange/8 p-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Load into Planner Workspace</div>
          <p className="mt-1 text-[11px] text-silver-dk">
            Loads this suggested build into the editable Build Plan for review. Nothing is committed in-game.
          </p>
          {controlsChangedSinceGeneration && (
            <p className="mt-2 text-[11px] text-gold">
              These suggested builds may not match the current Build Plan target/settings. Copying is still possible, but requires confirmation because the suggested build was generated from older controls.
            </p>
          )}
          {loadConfirmation ? (
            <LoadConfirmation
              mode={loadConfirmation}
              onCancel={cancelLoad}
              onConfirm={confirmLoad}
            />
          ) : (
            <button
              type="button"
              onClick={requestLoad}
              className="mt-3 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 font-mono text-xs font-bold text-orange hover:bg-orange/25"
            >
              Load into Planner Workspace
            </button>
          )}
        </div>
      )}

      <OptimiserComparisonPanel result={comparison} />

      <OptimiserRankingBreakdown breakdown={ranking?.rank_breakdown} />
    </div>
  );
}

function LoadConfirmation({
  mode,
  onCancel,
  onConfirm,
}: {
  mode: 'replace' | 'stale' | 'stale_replace';
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const isStale = mode === 'stale' || mode === 'stale_replace';
  const title = mode === 'stale_replace'
    ? 'Replace current Build Plan with older suggested build?'
    : mode === 'stale'
      ? 'These suggested builds were generated with older controls'
      : 'Replace current Build Plan with this suggested build?';
  const body = mode === 'stale_replace'
    ? 'These suggested builds were generated with older controls and may not match the current Build Plan target/settings. This will replace your current Build Plan with this suggested build. It does not save anything or affect in-game state.'
    : mode === 'stale'
      ? 'The current target/settings differ from the values used to generate this suggested build. Generate again for the safest comparison, or deliberately copy this older suggested build into the editable Build Plan.'
      : 'This will replace your current Build Plan with this suggested build. It does not save anything or affect in-game state.';
  const confirmLabel = mode === 'stale_replace'
    ? 'Replace with older suggested build'
    : isStale
      ? 'Copy older suggested build anyway'
      : 'Replace Build Plan';

  return (
    <div className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2">
      <div className="text-xs font-semibold text-gold">{title}</div>
      <p className="mt-1 text-[11px] text-silver-dk">{body}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-border bg-bg3 px-3 py-1.5 font-mono text-[11px] text-silver hover:border-orange/50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="rounded border border-orange/50 bg-orange/15 px-3 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/25"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}

function SummaryBox({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-cyan/25 bg-cyan/5 px-3 py-2">
      <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">{title}</h5>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">{body}</p>
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
