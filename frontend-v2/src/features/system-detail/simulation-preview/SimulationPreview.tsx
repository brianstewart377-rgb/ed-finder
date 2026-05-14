import { useEffect, useMemo, useState } from 'react';
import { Play, Plus } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getFacilityTemplates, getSimulationSummary, simulateBuild } from '@/lib/api';
import type {
  FacilityTemplate,
  OptimiserCandidate,
  RecommendedBuildPlan,
  SimulateBuildPlacement,
  SimulateBuildRequest,
  SimulateBuildResponse,
  SimulationSummary,
  SystemDetail,
} from '@/types/api';
import { BuildPlanEditor } from './BuildPlanEditor';
import { SimulationResult } from './SimulationResult';
import { ModeIntro, PlanBadge, StartModes } from './StartModes';
import { GhostMetric, Message } from './components';
import { OptimiserCandidatePanel, candidatePlacementsToPreviewPlacements } from './optimiser';
import { RegionalContextMini } from './panels';
import { ARCHETYPES, type StartMode } from './types';
import {
  archetypeFromEconomy,
  buildRecommendedPlacements,
  preferredTemplate,
  resequence,
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
  const [targetArchetype, setTargetArchetype] = useState('refinery_industrial');
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [result, setResult] = useState<SimulateBuildResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startMode, setStartMode] = useState<StartMode>('recommended');
  const [autoLoadedRecommendation, setAutoLoadedRecommendation] = useState(false);
  const [optimiserCandidateOriginLabel, setOptimiserCandidateOriginLabel] = useState<string | null>(null);
  const [optimiserCandidateWasEdited, setOptimiserCandidateWasEdited] = useState(false);

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
  const canRun = placements.length > 0 && !running;

  useEffect(() => {
    if (!initialRequest) return;
    setTargetArchetype(initialRequest.target_archetype);
    setPlacements(resequence(initialRequest.placements));
    setResult(null);
    setError(null);
    setStartMode('edit_recommended');
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
    setAutoLoadedRecommendation(true);
  }, [initialRequest]);

  useEffect(() => {
    if (!hasRecommendedBuild || autoLoadedRecommendation) return;
    if (placements.length > 0 || startMode === 'blank_advanced') return;
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    setResult(null);
    setError(null);
    setStartMode('recommended');
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
    setAutoLoadedRecommendation(true);
  }, [autoLoadedRecommendation, hasRecommendedBuild, placements.length, recommendedPlacements, startMode, suggestedArchetype]);

  const loadRecommendedPlan = (mode: StartMode) => {
    if (!hasRecommendedBuild) return;
    setStartMode(mode);
    setTargetArchetype(suggestedArchetype);
    setPlacements(recommendedPlacements);
    setResult(null);
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
    setError(null);
  };

  const loadOptimiserCandidateIntoPreview = (candidate: OptimiserCandidate) => {
    const candidatePlacements = candidatePlacementsToPreviewPlacements(candidate.placements);
    setTargetArchetype(candidate.target_archetype);
    setPlacements(resequence(candidatePlacements));
    setResult(null);
    setError(null);
    setStartMode('optimiser_candidate');
    setAutoLoadedRecommendation(true);
    setOptimiserCandidateOriginLabel(candidate.label);
    setOptimiserCandidateWasEdited(false);
  };

  const startBlankAdvanced = () => {
    setStartMode('blank_advanced');
    setOptimiserCandidateOriginLabel(null);
    setOptimiserCandidateWasEdited(false);
    setAutoLoadedRecommendation(true);
    setPlacements([]);
    setResult(null);
    setError(null);
  };

  const markOptimiserCandidateEdited = () => {
    if (optimiserCandidateOriginLabel) {
      setOptimiserCandidateWasEdited(true);
    }
  };

  const addPlacement = () => {
    const firstTemplate = preferredTemplate(templates);
    if (!firstTemplate) return;
    markOptimiserCandidateEdited();
    if (placements.length === 0 && startMode !== 'blank_advanced') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => [
      ...current,
      {
        facility_template_id: firstTemplate.id,
        local_body_id: bodies[0]?.id != null ? String(bodies[0].id) : null,
        is_primary_port: current.length === 0 && firstTemplate.is_port,
        build_order: current.length + 1,
      },
    ]);
  };

  const updatePlacement = (index: number, patch: Partial<SimulateBuildPlacement>) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => current.map((item, i) => {
      if (i !== index) {
        return patch.is_primary_port ? { ...item, is_primary_port: false } : item;
      }
      return { ...item, ...patch };
    }));
  };

  const removePlacement = (index: number) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => resequence(current.filter((_, i) => i !== index)));
  };

  const movePlacement = (index: number, direction: -1 | 1) => {
    markOptimiserCandidateEdited();
    if (startMode === 'recommended') {
      setStartMode('edit_recommended');
    }
    setPlacements((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
      return resequence(copy);
    });
  };

  const runSimulation = async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    try {
      const response = await simulateBuild({
        system_id64: system.id64,
        target_archetype: targetArchetype,
        placements: resequence(placements),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div
      className="rounded-chunk-lg border border-orange/25 overflow-hidden shadow-metal"
      style={{
        background: 'linear-gradient(180deg, rgba(27,29,34,0.95), rgba(11,13,17,0.95))',
      }}
    >
      <div className="px-4 py-3 border-b border-border/70 bg-orange/5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">
              Simulation Preview
            </h3>
            <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
              This preview shows what your selected build would produce before you commit in-game.
            </p>
            {initialPlanLabel && (
              <p className="mt-1 text-[11px] text-orange font-mono">
                You are previewing the {initialPlanLabel}.
              </p>
            )}
          </div>
          <PlanBadge mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />
          <button
            type="button"
            onClick={runSimulation}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 disabled:opacity-45 disabled:cursor-not-allowed"
          >
            <Play size={14} />
            {running ? 'Running' : 'Run Preview'}
          </button>
        </div>
      </div>

      <div className="border-b border-border/60 px-4 py-3">
        <StartModes
          mode={startMode}
          hasRecommendedBuild={hasRecommendedBuild}
          loadingRecommended={summaryQuery.isLoading || templatesQuery.isLoading}
          onUseRecommended={() => loadRecommendedPlan('recommended')}
          onEditRecommended={() => loadRecommendedPlan('edit_recommended')}
          onBlank={startBlankAdvanced}
        />
        {optimiserCandidateOriginLabel && (
          <div className="mt-3 rounded border border-cyan/35 bg-cyan/5 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Optimiser candidate origin</div>
            <div className="mt-1 text-[11px] text-silver-dk">
              {optimiserCandidateWasEdited ? (
                <>Started from optimiser candidate: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. This preview plan has been edited since loading.</>
              ) : (
                <>Loaded optimiser candidate: <span className="text-silver">{optimiserCandidateOriginLabel}</span>. You can edit the build and run the normal preview.</>
              )}
            </div>
          </div>
        )}
        {initialAssumptions.length > 0 && (
          <div className="mt-3 rounded border border-gold/35 bg-gold/5 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">Estimated assumptions</div>
            <ul className="mt-1 space-y-1 font-mono text-[11px] text-silver-dk">
              {initialAssumptions.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
        <div className="space-y-3">
          <ModeIntro mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />

          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="space-y-1">
              <span className="block text-[10px] font-mono uppercase tracking-[0.16em] text-silver-dk">
                Target archetype
              </span>
              <select
                value={targetArchetype}
                onChange={(e) => setTargetArchetype(e.target.value)}
                className="w-full"
              >
                {ARCHETYPES.map((archetype) => (
                  <option key={archetype.id} value={archetype.id}>{archetype.label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={addPlacement}
              disabled={templates.length === 0}
              className="self-end inline-flex items-center justify-center gap-2 rounded-chunk-sm border border-border bg-bg3 px-3 py-2 text-xs font-mono text-silver hover:border-orange/60 hover:text-orange disabled:opacity-45"
            >
              <Plus size={14} />
              Add Facility
            </button>
          </div>

          {templatesQuery.isLoading && (
            <div className="rounded border border-border/60 bg-bg3/30 px-3 py-3 text-xs font-mono text-silver-dk">
              Loading facility catalogue...
            </div>
          )}

          {templatesQuery.isError && (
            <Message tone="warn" items={[templatesQuery.error?.message ?? 'Facility catalogue failed to load.']} />
          )}

          {placements.length === 0 ? (
            <div className="rounded-chunk-lg border border-dashed border-gold/45 bg-gold/5 px-4 py-6 text-center">
              <div className="font-mono text-xs text-gold">
                {startMode === 'blank_advanced' ? 'Blank advanced simulation' : 'No recommended build loaded yet'}
              </div>
              <div className="mt-1 text-[11px] text-silver-dk">
                {startMode === 'blank_advanced'
                  ? 'Start with a primary port, then add support facilities and run the preview.'
                  : 'Use a recommended build when available, or choose the advanced blank mode.'}
              </div>
            </div>
          ) : (
            <BuildPlanEditor
              placements={placements}
              templates={templates}
              bodies={bodies}
              onUpdate={updatePlacement}
              onRemove={removePlacement}
              onMove={movePlacement}
            />
          )}
        </div>

        <div className="space-y-3">
          <RegionalContextMini regional={regionalContext} loading={summaryQuery.isLoading} />
          {error && <Message tone="danger" items={[error]} />}
          {result ? (
            <SimulationResult result={result} />
          ) : (
            <div className="h-full min-h-[260px] rounded-chunk-lg border border-border/60 bg-bg3/25 p-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                Awaiting preview
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <GhostMetric label="Score" />
                <GhostMetric label="Build" />
                <GhostMetric label="Confidence" />
              </div>
              <div className="mt-5 space-y-2">
                <div className="h-3 w-4/5 rounded bg-bg4/70" />
                <div className="h-3 w-2/3 rounded bg-bg4/50" />
                <div className="h-3 w-1/2 rounded bg-bg4/40" />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-border/60 p-4">
            <OptimiserCandidatePanel
              systemId64={system.id64}
              targetArchetype={targetArchetype}
              hasExistingPreviewPlan={placements.length > 0}
              onLoadCandidate={loadOptimiserCandidateIntoPreview}
              currentPreviewPlacements={placements}
              currentTargetArchetype={targetArchetype}
              currentPreviewLabel="Current editable preview plan"
            />
      </div>
    </div>
  );
}

export type { RecommendedBuildPlan };
