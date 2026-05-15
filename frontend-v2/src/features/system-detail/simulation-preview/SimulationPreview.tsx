import { useEffect, useMemo } from 'react';
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
          onUseRecommended={() => plan.loadRecommendedPlan('recommended')}
          onEditRecommended={() => plan.loadRecommendedPlan('edit_recommended')}
          onBlank={plan.startBlankAdvanced}
          onAddPlacement={plan.addPlacement}
          onUpdatePlacement={plan.updatePlacement}
          onRemovePlacement={plan.removePlacement}
          onMovePlacement={plan.movePlacement}
        />

        <section aria-label="Optimiser Candidates">
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
            re-derived from observations; Stage 6C will add predicted-vs-
            observed comparison and Stage 6D will render validation. */}
        <ObservedEvidencePanel
          systemId64={system.id64}
          suggestedArchetype={plan.targetArchetype}
        />
      </div>
    </div>
  );
}

export type { RecommendedBuildPlan };
