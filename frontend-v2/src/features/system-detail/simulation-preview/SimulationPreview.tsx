import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFacilityTemplates, getSimulationSummary, getSlotPredictions, listObservedFacts } from '@/lib/api';
import type {
  FacilityTemplate,
  OptimiserCandidate,
  RecommendedBuildPlan,
  SimulateBuildPlacement,
  SimulateBuildRequest,
  SimulationSummary,
  SystemDetail,
} from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { DeclaredColonyRole } from '@/features/colony-planner/colonyRoles';
import {
  buildObservedRolesFromFacts,
  buildRoleReview,
} from '@/features/colony-planner/colonyRoleReview';
import { getPlanningFocusLabel } from '@/features/colony-planner/workspaceUtils';
import { bodyIdKey } from './bodyIdUtils';
import type { PlannerWorkspaceCommand, ReviewDrawer } from '@/features/colony-planner/workspaceUtils';
import { compactBodyDisplayName, groupPlacementsByBody, type BodyGroup } from './buildPlanLayoutUtils';
import { BuildPlanWorkspaceView } from './BuildPlanWorkspaceView';
import { ColonyPlannerHeader } from './ColonyPlannerHeader';
import { EvidenceWorkspaceView } from './EvidenceWorkspaceView';
import { PreviewWorkspaceView } from './PreviewWorkspaceView';
import { SuggestedBuildsWorkspaceView } from './SuggestedBuildsWorkspaceView';
import { ValidationWorkspaceView } from './ValidationWorkspaceView';
import { WorkspaceModeTabs, type SimulationWorkspaceMode } from './WorkspaceModeTabs';
import {
  buildColonyRoleSummaryForGroup,
  primaryRoleHint,
  roleConfidenceLabel,
  type ColonyRoleSummary,
} from './colonyRoleHintUtils';
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
  onPlanSnapshotChange,
  topologySelection,
  declaredRoles = [],
  workspaceCommand,
  lastHandledWorkspaceCommandToken = 0,
  onWorkspaceCommandHandled,
  workspaceDrawer,
  onWorkspaceDrawerChange,
  initialMode = 'build-plan',
}: {
  system: SystemDetail;
  initialRequest?: SimulateBuildRequest | null;
  initialPlanLabel?: string | null;
  initialAssumptions?: string[];
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  declaredRoles?: DeclaredColonyRole[];
  workspaceCommand?: PlannerWorkspaceCommand | null;
  lastHandledWorkspaceCommandToken?: number;
  onWorkspaceCommandHandled?: (token: number) => void;
  workspaceDrawer?: ReviewDrawer;
  onWorkspaceDrawerChange?: (drawer: ReviewDrawer) => void;
  initialMode?: SimulationWorkspaceMode;
}) {
  const [localWorkspaceDrawer, setLocalWorkspaceDrawer] = useState<ReviewDrawer>(null);
  const activeWorkspaceDrawer = workspaceDrawer === undefined ? localWorkspaceDrawer : workspaceDrawer;
  const setActiveWorkspaceDrawer = onWorkspaceDrawerChange ?? setLocalWorkspaceDrawer;
  const [activeMode, setActiveMode] = useState<SimulationWorkspaceMode>(initialMode);
  const [projectedCandidate, setProjectedCandidate] = useState<OptimiserCandidate | null>(null);
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
  const slotPredictionsQuery = useQuery({
    queryKey: ['slot-predictions-preview', system.id64],
    queryFn: () => getSlotPredictions(system.id64),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  const observedFactsQuery = useQuery({
    queryKey: ['role-review-observed-facts', system.id64],
    queryFn: () => listObservedFacts({ system_id64: system.id64, limit: 100 }),
    enabled: activeMode === 'evidence' || activeMode === 'validation',
    staleTime: 60 * 1000,
    retry: 1,
  });

  const templates = useMemo(
    () => templatesQuery.data ?? [],
    [templatesQuery.data],
  );
  const bodies = useMemo(() => simulationBodies(system.bodies), [system.bodies]);
  const recommendedSteps = useMemo(
    () => summaryQuery.data?.buildability?.recommended_build_order ?? [],
    [summaryQuery.data?.buildability?.recommended_build_order],
  );
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
  const planningFocusLabel = topologySelection ? getPlanningFocusLabel(topologySelection, system) : null;
  const bodyLabelsById = useMemo(() => Object.fromEntries(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [bodyIdKey(body.id), compactBodyDisplayName(body, system.name)]),
  ), [bodies, system.name]);

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
  const clearPreviewState = runState.clearPreviewState;
  const roleGroups = useMemo(
    () => groupPlacementsByBody(plan.placements, templates, bodies),
    [bodies, plan.placements, templates],
  );
  const selectedRoleSummary = useMemo(
    () => buildWorkspaceRoleSummary(topologySelection, roleGroups),
    [roleGroups, topologySelection],
  );
  const overviewRoleSummary = useMemo(
    () => buildOverviewRoleSummary(roleGroups),
    [roleGroups],
  );
  const observedRoles = useMemo(
    () => buildObservedRolesFromFacts(observedFactsQuery.data?.facts ?? []),
    [observedFactsQuery.data?.facts],
  );
  const roleReview = useMemo(
    () => buildRoleReview({ declaredRoles, observedRoles }),
    [declaredRoles, observedRoles],
  );
  const lastEmittedPlanSnapshotFingerprintRef = useRef<string | null>(null);
  const initialRequestHydrationRef = useRef<{ fingerprint: string | null; hydrated: boolean }>({
    fingerprint: null,
    hydrated: false,
  });

  useEffect(() => {
    if (!onPlanSnapshotChange) return;
    const projection: TopologyPlanSnapshot['projection'] = projectedCandidate ? {
      candidateId: projectedCandidate.candidate_id,
      label: projectedCandidate.label,
      placements: projectedCandidate.placements.map((placement) => ({
        facility_template_id: placement.facility_template_id,
        local_body_id: placement.local_body_id ?? null,
        is_primary_port: placement.is_primary_port,
        build_order: placement.build_order,
      })),
    } : null;
    const initialRequestFingerprint = initialRequest
      ? planSnapshotEmissionFingerprint(initialRequest.placements, initialRequest.target_archetype, null)
      : null;
    const currentPlanFingerprint = planSnapshotEmissionFingerprint(plan.placements, plan.targetArchetype, null);
    if (initialRequestHydrationRef.current.fingerprint !== initialRequestFingerprint) {
      initialRequestHydrationRef.current = { fingerprint: initialRequestFingerprint, hydrated: false };
    }
    if (initialRequestFingerprint && !initialRequestHydrationRef.current.hydrated) {
      if (currentPlanFingerprint !== initialRequestFingerprint) return;
      initialRequestHydrationRef.current.hydrated = true;
    }
    const fingerprint = planSnapshotEmissionFingerprint(plan.placements, plan.targetArchetype, projection);
    if (lastEmittedPlanSnapshotFingerprintRef.current === fingerprint) return;
    lastEmittedPlanSnapshotFingerprintRef.current = fingerprint;
    onPlanSnapshotChange({
      placements: plan.placements,
      templates,
      targetArchetype: plan.targetArchetype,
      slotPredictions: slotPredictionsQuery.data ?? null,
      projection,
    });
  }, [initialRequest, onPlanSnapshotChange, plan.placements, plan.targetArchetype, projectedCandidate, slotPredictionsQuery.data, templates]);

  useEffect(() => {
    clearPreviewState();
  }, [clearPreviewState, plan.planReplacementVersion]);

  useEffect(() => {
    if (activeWorkspaceDrawer === 'evidence') {
      setActiveMode('evidence');
    } else if (activeWorkspaceDrawer === 'validation') {
      setActiveMode('validation');
    }
  }, [activeWorkspaceDrawer]);

  useEffect(() => {
    setActiveMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    if (!workspaceCommand) return;
    if (workspaceCommand.token <= lastHandledWorkspaceCommandToken) return;
    setActiveMode('build-plan');
    if (activeWorkspaceDrawer) setActiveWorkspaceDrawer(null);
  }, [
    activeWorkspaceDrawer,
    lastHandledWorkspaceCommandToken,
    setActiveWorkspaceDrawer,
    workspaceCommand,
  ]);

  useEffect(() => () => {
    if (suggestedBuildsHighlightTimeoutRef.current !== null) {
      window.clearTimeout(suggestedBuildsHighlightTimeoutRef.current);
      suggestedBuildsHighlightTimeoutRef.current = null;
    }
  }, []);

  const focusSuggestedBuilds = () => {
    setActiveMode('suggested-builds');
    const node = suggestedBuildsRef.current;
    setHighlightSuggestedBuilds(true);
    if (suggestedBuildsHighlightTimeoutRef.current !== null) {
      window.clearTimeout(suggestedBuildsHighlightTimeoutRef.current);
    }
    suggestedBuildsHighlightTimeoutRef.current = window.setTimeout(() => {
      setHighlightSuggestedBuilds(false);
      suggestedBuildsHighlightTimeoutRef.current = null;
    }, 1800);
    window.setTimeout(() => {
      node?.focus({ preventScroll: true });
    }, 0);
  };

  const handleModeChange = (mode: SimulationWorkspaceMode) => {
    setActiveMode(mode);
    if (mode === 'evidence') {
      setActiveWorkspaceDrawer('evidence');
    } else if (mode === 'validation') {
      setActiveWorkspaceDrawer('validation');
    } else if (activeWorkspaceDrawer) {
      setActiveWorkspaceDrawer(null);
    }
  };

  const handleLoadSuggestedBuild = (candidate: Parameters<typeof plan.loadOptimiserCandidateIntoPreview>[0]) => {
    plan.loadOptimiserCandidateIntoPreview(candidate);
    setProjectedCandidate(null);
    setActiveMode('build-plan');
    if (activeWorkspaceDrawer) {
      setActiveWorkspaceDrawer(null);
    }
  };

  const handleSuggestedCandidateSelection = useCallback((candidate: OptimiserCandidate | null) => {
    setProjectedCandidate((current) => {
      if (!candidate) return current ? null : current;
      return current?.candidate_id === candidate.candidate_id ? current : candidate;
    });
  }, []);

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

      <WorkspaceModeTabs activeMode={activeMode} onModeChange={handleModeChange} />

      <div className="p-4" data-testid="simulation-preview-active-mode" data-active-mode={activeMode}>
        {activeMode === 'build-plan' && (
          <BuildPlanWorkspaceView
            planningFocusLabel={planningFocusLabel}
            roleContext={(
              <WorkspaceRoleContext
                mode="Build Plan"
                summary={selectedRoleSummary ?? overviewRoleSummary}
                fallback="Current body strategic purpose will appear here once placements provide role context."
              />
            )}
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
            topologySelection={topologySelection}
            workspaceCommand={workspaceCommand}
            lastHandledWorkspaceCommandToken={lastHandledWorkspaceCommandToken}
            onWorkspaceCommandHandled={onWorkspaceCommandHandled}
          />
        )}
        <div
          ref={suggestedBuildsRef}
          tabIndex={-1}
          data-testid="suggested-builds-focus-target"
          className="outline-none"
        >
          {activeMode === 'suggested-builds' && (
            <SuggestedBuildsWorkspaceView
              planningFocusLabel={planningFocusLabel}
              highlighted={highlightSuggestedBuilds}
              roleContext={(
                <WorkspaceRoleContext
                  mode="Suggested Builds"
                  summary={selectedRoleSummary ?? overviewRoleSummary}
                  fallback="Suggested Builds can be compared against the selected strategic purpose after candidates are loaded."
                />
              )}
              systemId64={system.id64}
              targetArchetype={plan.targetArchetype}
              hasExistingPreviewPlan={plan.placements.length > 0}
              onLoadCandidate={handleLoadSuggestedBuild}
              currentPreviewPlacements={plan.placements}
              currentTargetArchetype={plan.targetArchetype}
              currentPreviewLabel="Current editable Build Plan"
              onCandidateSelect={handleSuggestedCandidateSelection}
              bodyLabelsById={bodyLabelsById}
              templates={templates}
            />
          )}
        </div>

        {activeMode === 'preview' && (
          <PreviewWorkspaceView
            roleContext={(
              <WorkspaceRoleContext
                mode="Preview"
                summary={overviewRoleSummary}
                fallback="Preview role overview is informational until the Build Plan has body assignments."
              />
            )}
            regional={regionalContext}
            loadingRegional={summaryQuery.isLoading}
            error={runState.error}
            result={runState.result}
            isResultStale={runState.isResultStale}
            canRun={runState.canRun}
            running={runState.running}
            onRunPreview={() => void runState.runSimulation()}
          />
        )}

        {activeMode === 'evidence' && (
          <EvidenceWorkspaceView
            systemId64={system.id64}
            targetArchetype={plan.targetArchetype}
            roleContext={(
              <WorkspaceRoleContext
                mode="Evidence"
                summary={selectedRoleSummary ?? overviewRoleSummary}
                fallback="Role hints remain informational while observed evidence is reviewed."
                reviewLabel={roleReview.consistencyLabel}
              />
            )}
            roleReview={roleReview}
          />
        )}

        {activeMode === 'validation' && (
          <ValidationWorkspaceView
            systemId64={system.id64}
            targetArchetype={plan.targetArchetype}
            previewResult={runState.result}
            isPreviewResultStale={runState.isResultStale}
            roleContext={(
              <WorkspaceRoleContext
                mode="Validation"
                summary={selectedRoleSummary ?? overviewRoleSummary}
                fallback="Validation does not treat inferred roles as authoritative."
                reviewLabel={roleReview.consistencyLabel}
              />
            )}
            roleReview={roleReview}
          />
        )}
      </div>
    </div>
  );
}

function WorkspaceRoleContext({
  mode,
  summary,
  fallback,
  reviewLabel,
}: {
  mode: SimulationWorkspaceMode | 'Build Plan' | 'Suggested Builds' | 'Preview' | 'Evidence' | 'Validation';
  summary: ColonyRoleSummary | null;
  fallback: string;
  reviewLabel?: string;
}) {
  const primary = summary ? primaryRoleHint(summary.hints) : null;
  return (
    <section
      data-testid="workspace-mode-role-context"
      className="rounded-chunk-lg border border-cyan/20 bg-bg3/35 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-[0.16em] text-cyan">{mode} role context</span>
        {primary && (
          <span className="rounded border border-cyan/30 bg-cyan/5 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-cyan">
            {primary.compactLabel}
          </span>
        )}
        {summary && (
          <span className="rounded border border-border/60 bg-bg2/55 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-silver-dk">
            {roleConfidenceLabel(summary.confidence)}
          </span>
        )}
        {summary?.conflicts.length ? (
          <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-gold">
            role overlap
          </span>
        ) : null}
        {reviewLabel && (
          <span className="rounded border border-orange/35 bg-orange/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-orange">
            {reviewLabel}
          </span>
        )}
      </div>
      <p className="mt-1">
        {summary ? summary.reasoning : fallback}
        <span className="ml-2 text-silver-dk">Advisory only; no role assignment or mechanics change is applied.</span>
      </p>
    </section>
  );
}

function planSnapshotEmissionFingerprint(
  placements: SimulateBuildPlacement[],
  targetArchetype: string,
  projection: TopologyPlanSnapshot['projection'],
): string {
  return JSON.stringify({
    targetArchetype,
    placements: placements.map(snapshotPlacementFingerprint),
    projection: projection ? {
      candidateId: projection.candidateId,
      label: projection.label,
      placements: projection.placements.map(snapshotPlacementFingerprint),
    } : null,
  });
}

function snapshotPlacementFingerprint(placement: SimulateBuildPlacement) {
  return {
    facility_template_id: placement.facility_template_id,
    local_body_id: placement.local_body_id ?? null,
    is_primary_port: Boolean(placement.is_primary_port),
    build_order: placement.build_order,
  };
}

function buildWorkspaceRoleSummary(
  selection: TopologySelection | undefined,
  groups: BodyGroup[],
): ColonyRoleSummary | null {
  if (!selection) return null;
  if (selection.type === 'body') {
    const group = groups.find((item) => item.key === selection.bodyId);
    return group ? buildColonyRoleSummaryForGroup(group, groups) : null;
  }
  if (selection.type === 'placement') {
    const group = groups.find((item) => item.placements.some((placement) => placement.index === selection.placementIndex));
    return group ? buildColonyRoleSummaryForGroup(group, groups) : null;
  }
  return null;
}

function buildOverviewRoleSummary(groups: BodyGroup[]): ColonyRoleSummary | null {
  const summaries = groups
    .filter((group) => group.placements.length > 0)
    .map((group) => buildColonyRoleSummaryForGroup(group, groups));
  return summaries.find((summary) => summary.confidence === 'strong')
    ?? summaries.find((summary) => summary.confidence === 'likely')
    ?? summaries[0]
    ?? null;
}

export type { RecommendedBuildPlan };
