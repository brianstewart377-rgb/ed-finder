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
import type { TopologyPlanSnapshot, TopologySelection } from '@/features/colony-planner/ColonyTopologyRail';
import type { ReviewDrawer } from '@/features/colony-planner/workspaceUtils';
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
  onPlanSnapshotChange,
  topologySelection,
  workspaceDrawer,
  onWorkspaceDrawerChange,
  showWorkspaceDrawerControls = true,
}: {
  system: SystemDetail;
  initialRequest?: SimulateBuildRequest | null;
  initialPlanLabel?: string | null;
  initialAssumptions?: string[];
  onPlanSnapshotChange?: (snapshot: TopologyPlanSnapshot) => void;
  topologySelection?: TopologySelection;
  workspaceDrawer?: ReviewDrawer;
  onWorkspaceDrawerChange?: (drawer: ReviewDrawer) => void;
  showWorkspaceDrawerControls?: boolean;
}) {
  const [localWorkspaceDrawer, setLocalWorkspaceDrawer] = useState<ReviewDrawer>(null);
  const activeWorkspaceDrawer = workspaceDrawer === undefined ? localWorkspaceDrawer : workspaceDrawer;
  const setActiveWorkspaceDrawer = onWorkspaceDrawerChange ?? setLocalWorkspaceDrawer;
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
    onPlanSnapshotChange?.({
      placements: plan.placements,
      templates,
      targetArchetype: plan.targetArchetype,
    });
  }, [onPlanSnapshotChange, plan.placements, plan.targetArchetype, templates]);

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
          topologySelection={topologySelection}
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

        <WorkspaceReviewDrawers
          openDrawer={activeWorkspaceDrawer}
          onOpenDrawer={setActiveWorkspaceDrawer}
          showControls={showWorkspaceDrawerControls}
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

function WorkspaceReviewDrawers({
  openDrawer,
  onOpenDrawer,
  showControls,
  systemId64,
  targetArchetype,
  previewResult,
  isPreviewResultStale,
}: {
  openDrawer: ReviewDrawer;
  onOpenDrawer: (drawer: ReviewDrawer) => void;
  showControls: boolean;
  systemId64: number;
  targetArchetype: string;
  previewResult: ReturnType<typeof useSimulationPreviewRun>['result'];
  isPreviewResultStale: boolean;
}) {
  return (
    <section className="rounded-chunk-lg border border-border/60 bg-bg2/25 p-3" aria-label="Evidence and validation workspace drawers">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">
            Evidence / Validation
          </div>
          <p className="mt-1 text-[11px] leading-snug text-silver-dk">
            Review evidence or validation when needed. Opening a drawer does not run Preview.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
          <StatusBadge label="Evidence" value="Manual" />
          <StatusBadge
            label="Validation"
            value={previewResult ? (isPreviewResultStale ? 'Preview stale' : 'Preview ready') : 'Needs preview'}
            warn={!previewResult || isPreviewResultStale}
          />
        </div>
      </div>

      {showControls && (
        <div className="mt-3 flex flex-wrap gap-2">
          <DrawerButton
            label="Evidence drawer"
            active={openDrawer === 'evidence'}
            onClick={() => onOpenDrawer(openDrawer === 'evidence' ? null : 'evidence')}
          />
          <DrawerButton
            label="Validation drawer"
            active={openDrawer === 'validation'}
            onClick={() => onOpenDrawer(openDrawer === 'validation' ? null : 'validation')}
          />
        </div>
      )}

      {!openDrawer && (
        <div className="mt-3 rounded border border-border/55 bg-bg3/30 px-3 py-2 font-mono text-[11px] text-silver-dk">
          Evidence and validation are available as drawers so they do not dominate the planning workspace.
        </div>
      )}

      {openDrawer === 'evidence' && (
        <div className="mt-3 rounded-chunk-lg border border-cyan/30 bg-bg1/50 p-3" data-testid="evidence-drawer">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-mono text-[11px] uppercase tracking-[0.16em] text-cyan">Evidence drawer</h4>
            <button type="button" onClick={() => onOpenDrawer(null)} className="rounded border border-border bg-bg3 px-2 py-1 font-mono text-[10px] text-silver hover:border-cyan/50">
              Close
            </button>
          </div>
          <details className="mb-3 rounded border border-border/55 bg-bg3/25 px-3 py-2">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Mismatch / needs-observation summary
            </summary>
            <p className="mt-2 text-[11px] leading-snug text-silver-dk">
              Add manual observations here when in-game facts need to be compared with the current preview.
            </p>
          </details>
          <ObservedEvidencePanel
            systemId64={systemId64}
            suggestedArchetype={targetArchetype}
          />
        </div>
      )}

      {openDrawer === 'validation' && (
        <div className="mt-3 rounded-chunk-lg border border-orange/30 bg-bg1/50 p-3" data-testid="validation-drawer">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-mono text-[11px] uppercase tracking-[0.16em] text-orange">Validation drawer</h4>
            <button type="button" onClick={() => onOpenDrawer(null)} className="rounded border border-border bg-bg3 px-2 py-1 font-mono text-[10px] text-silver hover:border-orange/50">
              Close
            </button>
          </div>
          <details className="mb-3 rounded border border-border/55 bg-bg3/25 px-3 py-2">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Mismatch / needs-observation summary
            </summary>
            <p className="mt-2 text-[11px] leading-snug text-silver-dk">
              Validation compares the current preview with manual evidence only after this drawer is opened.
            </p>
          </details>
          <ValidationPanel
            systemId64={systemId64}
            targetArchetype={targetArchetype}
            previewResult={previewResult}
            isPreviewResultStale={isPreviewResultStale}
          />
        </div>
      )}
    </section>
  );
}

function StatusBadge({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <span className={[
      'rounded border px-1.5 py-0.5',
      warn ? 'border-gold/40 bg-gold/10 text-gold' : 'border-cyan/35 bg-cyan/10 text-cyan',
    ].join(' ')}>
      {label}: {value}
    </span>
  );
}

function DrawerButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-expanded={active}
      onClick={onClick}
      className={[
        'rounded border px-3 py-2 font-mono text-xs font-bold transition',
        active ? 'border-orange/60 bg-orange/15 text-orange' : 'border-border bg-bg3 text-silver hover:border-cyan/50',
      ].join(' ')}
    >
      {label}
    </button>
  );
}
