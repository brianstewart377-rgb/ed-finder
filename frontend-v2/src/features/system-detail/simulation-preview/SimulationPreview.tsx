import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFacilityTemplates, getSimulationSummary } from '@/lib/api';
import type {
  FacilityTemplate,
  RecommendedBuildPlan,
  SimulateBuildRequest,
  SimulationSummary,
  SystemDetail,
} from '@/types/api';
import { BuildPlanSection } from './BuildPlanSection';
import { ColonyPlannerHeader } from './ColonyPlannerHeader';
import { ColonyPlannerSectionNav } from './ColonyPlannerSectionNav';
import { PreviewResultSection } from './PreviewResultSection';
import { ObservedEvidencePanel } from './observations';
import { OptimiserCandidatePanel } from './optimiser';
import { ValidationPanel } from './validation';
import { useSimulationPreviewPlan } from './hooks/useSimulationPreviewPlan';
import { useSimulationPreviewRun } from './hooks/useSimulationPreviewRun';
import {
  archetypeFromEconomy,
  buildRecommendedPlacements,
  simulationBodies,
} from './utils/placementHelpers';

export function SimulationPreview({
  system,
  initialRequest,
  initialPlanLabel,
  initialAssumptions = [],
}: {
  system: SystemDetail;
  initialRequest?: SimulateBuildRequest | null;
  initialPlanLabel?: string | null;
  initialAssumptions?: string[];
}) {
  const templatesQuery = useQuery<FacilityTemplate[], Error>({
    queryKey: ['facility-templates'],
    queryFn: getFacilityTemplates,
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });
  const summaryQuery = useQuery<SimulationSummary, Error>({
    queryKey: ['sim-summary-preview', system.id64],
    queryFn: () => getSimulationSummary(system.id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const templates = templatesQuery.data ?? [];
  const bodies = useMemo(() => simulationBodies(system.bodies), [system.bodies]);
  const recommendedSteps = summaryQuery.data?.buildability?.recommended_build_order ?? [];
  const regionalContext = summaryQuery.data?.regional_context ?? null;
  const suggestedArchetype = summaryQuery.data?.classification?.primary_archetype
    ?? archetypeFromEconomy(system.economy_suggestion)
    ?? 'refinery_industrial';
  const recommendedPlacements = useMemo(
    () => buildRecommendedPlacements(recommendedSteps, templates, bodies),
    [recommendedSteps, templates, bodies],
  );
  const hasRecommendedBuild = recommendedPlacements.length > 0;
  const suggestedBuildsRef = useRef<HTMLDivElement | null>(null);
  const suggestedBuildsHighlightTimeoutRef = useRef<number | null>(null);
  const [highlightSuggestedBuilds, setHighlightSuggestedBuilds] = useState(false);

  const plan = useSimulationPreviewPlan({
    initialRequest,
    templates,
    bodies,
    recommendedPlacements,
    hasRecommendedBuild,
    suggestedArchetype,
  });

  const runState = useSimulationPreviewRun({
    systemId64: system.id64,
    targetArchetype: plan.targetArchetype,
    placements: plan.placements,
  });

  useEffect(() => {
    runState.clearPreviewState();
  }, [plan.planReplacementVersion, runState.clearPreviewState]);

  useEffect(() => () => {
    if (suggestedBuildsHighlightTimeoutRef.current !== null) {
      window.clearTimeout(suggestedBuildsHighlightTimeoutRef.current);
      suggestedBuildsHighlightTimeoutRef.current = null;
    }
  }, []);

  const focusSuggestedBuilds = () => {
    const node = suggestedBuildsRef.current;
    if (!node) return;
    node.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    node.focus({ preventScroll: true });
    setHighlightSuggestedBuilds(true);
    if (suggestedBuildsHighlightTimeoutRef.current !== null) {
      window.clearTimeout(suggestedBuildsHighlightTimeoutRef.current);
    }
    suggestedBuildsHighlightTimeoutRef.current = window.setTimeout(() => {
      setHighlightSuggestedBuilds(false);
      suggestedBuildsHighlightTimeoutRef.current = null;
    }, 1800);
  };

  return (
    <div
      className="rounded-chunk-lg border border-orange/25 overflow-hidden shadow-metal"
      style={{
        background: 'linear-gradient(180deg, rgba(27,29,34,0.95), rgba(11,13,17,0.95))',
      }}
    >
      <ColonyPlannerHeader
        initialPlanLabel={initialPlanLabel}
        startMode={plan.startMode}
        hasRecommendedBuild={hasRecommendedBuild}
        canRun={runState.canRun}
        running={runState.running}
        onRunPreview={() => void runState.runSimulation()}
      />

      <ColonyPlannerSectionNav />

      <div className="space-y-4 p-4">
        <BuildPlanSection
          systemId64={system.id64}
          systemName={system.name}
          startMode={plan.startMode}
          hasRecommendedBuild={hasRecommendedBuild}
          loadingRecommended={summaryQuery.isLoading || templatesQuery.isLoading}
          targetArchetype={plan.targetArchetype}
          onTargetArchetypeChange={plan.setTargetArchetype}
          placements={plan.placements}
          templates={templates}
          bodies={bodies}
          templatesLoading={templatesQuery.isLoading}
          templatesErrorMessage={templatesQuery.isError ? templatesQuery.error?.message ?? 'Facility catalogue failed to load.' : null}
          optimiserCandidateOriginLabel={plan.optimiserCandidateOriginLabel}
          optimiserCandidateWasEdited={plan.optimiserCandidateWasEdited}
          initialAssumptions={initialAssumptions}
          previewResult={runState.result}
          isPreviewResultStale={runState.isResultStale}
          runningPreview={runState.running}
          onUseRecommended={() => plan.loadRecommendedPlan('recommended')}
          onBlank={plan.startBlankAdvanced}
          onShowSuggestedBuilds={focusSuggestedBuilds}
          onAddPlacement={plan.addPlacement}
          onUpdatePlacement={plan.updatePlacement}
          onRemovePlacement={plan.removePlacement}
          onMovePlacement={plan.movePlacement}
        />

        <div
          ref={suggestedBuildsRef}
          tabIndex={-1}
          data-testid="suggested-builds-focus-target"
          className={[
            'rounded-chunk-lg outline-none transition-[box-shadow,border-color] duration-300',
            highlightSuggestedBuilds ? 'ring-2 ring-cyan/70 shadow-brand-glow' : '',
          ].join(' ')}
        >
          <section aria-label="Suggested Builds">
            <OptimiserCandidatePanel
              systemId64={system.id64}
              targetArchetype={plan.targetArchetype}
              hasExistingPreviewPlan={plan.placements.length > 0}
              onLoadCandidate={plan.loadOptimiserCandidateIntoPreview}
              currentPreviewPlacements={plan.placements}
              currentTargetArchetype={plan.targetArchetype}
              currentPreviewLabel="Current editable Build Plan"
            />
          </section>
        </div>

        <PreviewResultSection
          regional={regionalContext}
          loadingRegional={summaryQuery.isLoading}
          error={runState.error}
          result={runState.result}
          isResultStale={runState.isResultStale}
        />

        {/* Stage 6B: Observed Evidence panel renders after Preview Result.
            It is intentionally passive — see ObservedEvidencePanel for the
            contract. The simulation and optimiser data above are NOT
            re-derived from observations; Stage 6C added the predicted-vs-
            observed comparison engine and Stage 6D renders that result
            below in the Validation section. */}
        <ObservedEvidencePanel
          systemId64={system.id64}
          suggestedArchetype={plan.targetArchetype}
        />

        {/* Stage 6D: Validation section renders the Stage 6C
            `/api/observations/compare` response in-page (no popout, no
            top-level tab). The panel is passive: it never runs
            simulation, never invokes the optimiser, never mutates
            observed evidence, and never feeds confidence back into
            scoring or ranking. */}
        <ValidationPanel
          systemId64={system.id64}
          targetArchetype={plan.targetArchetype}
          previewResult={runState.result}
          isPreviewResultStale={runState.isResultStale}
        />
      </div>
    </div>
  );
}

export type { RecommendedBuildPlan };
