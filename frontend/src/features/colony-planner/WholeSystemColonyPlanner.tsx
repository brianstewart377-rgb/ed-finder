import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, PanelRight } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import type { FacilityTemplate, SimulateBuildPlacement, SimulationSummary, SystemDetail } from '@/types/api';
import { getFacilityTemplates, getSimulationSummary, getSlotPredictions } from '@/lib/api';
import type { SimulationWorkspaceMode } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';
import { sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import { archetypeFromEconomy, resequence } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import type { BodyPlannerLane } from './BodySlotPlanner';
import { CanvasStructurePicker } from './CanvasStructurePicker';
import type { TopologyPlanSnapshot, TopologySelection } from './ColonyTopologyRail';
import { describeTopologySelection } from './topologySelectionUtils';
import { PlannerStatusStrip } from './PlannerStatusStrip';
import { WorkspaceSummaryRail } from './WorkspaceSummaryRail';
import { useWorkspaceProjectState } from './useWorkspaceProjectState';
import { getPlanningFocusLabel, type PlannerWorkspaceCommand } from './workspaceUtils';
import { buildPlanningEconomyLedger } from './planningEconomy';
import { AdvancedPlannerDrawer } from './AdvancedPlannerDrawer';
import {
  SystemBuildMapCanvas,
} from './SystemBuildMapCanvas';
import { WORKSPACE_MODE_META, workspaceModeLabel } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';
import {
  buildPlannerCanvasOccupancySummary,
  getPlannerLaneCapacityState,
} from './plannerCanvasUtils';
import {
  buildPlanPrerequisiteIssues,
  describePlacementTarget,
  laneDisabledReason,
  templateCanFitBody,
  templateDisplayName,
  templateMatchesLane,
} from './structurePlanningRules';

export function WholeSystemColonyPlanner({
  system,
  initialProjectId = null,
  initialCockpitMode = 'build-plan',
  onCockpitModeChange,
  onProjectContextChange,
}: {
  system: SystemDetail;
  initialProjectId?: string | null;
  initialCockpitMode?: SimulationWorkspaceMode;
  onCockpitModeChange?: (mode: SimulationWorkspaceMode) => void;
  onProjectContextChange?: (context: {
    activeProject: ReturnType<typeof useWorkspaceProjectState>['activeProject'];
    unsavedChanges: boolean;
    plannedStructureCount: number;
    deleteActiveProject: ReturnType<typeof useWorkspaceProjectState>['deleteActiveProject'];
  }) => void;
}) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [placementLaneHints, setPlacementLaneHints] = useState<Record<number, BodyPlannerLane>>({});
  const [targetArchetype, setTargetArchetype] = useState(() => (
    system.primary_archetype ?? archetypeFromEconomy(system.primary_economy) ?? 'refinery_industrial'
  ));
  const [projection, setProjection] = useState<TopologyPlanSnapshot['projection']>(null);
  const [advancedPanelOpen, setAdvancedPanelOpen] = useState(false);
  const [advancedInitialMode, setAdvancedInitialMode] = useState<SimulationWorkspaceMode>('build-plan');
  const [telemetryDockOpen, setTelemetryDockOpen] = useState(false);
  const [workspaceCommand, setWorkspaceCommand] = useState<PlannerWorkspaceCommand | null>(null);
  const [lastHandledWorkspaceCommandToken, setLastHandledWorkspaceCommandToken] = useState(0);
  const [structurePicker, setStructurePicker] = useState<{ bodyId: string; lane: BodyPlannerLane } | null>(null);
  const [structureAddFeedback, setStructureAddFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const appliedProjectFingerprint = useRef<string | null>(null);
  const hasMountedSystemReset = useRef(false);
  const placementsRef = useRef<SimulateBuildPlacement[]>(placements);

  useEffect(() => {
    placementsRef.current = placements;
  }, [placements]);

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

  const templates = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data]);
  const suggestedArchetype = summaryQuery.data?.classification?.primary_archetype
    ?? system.primary_archetype
    ?? archetypeFromEconomy(system.primary_economy)
    ?? 'refinery_industrial';

  useEffect(() => {
    if (!hasMountedSystemReset.current) {
      hasMountedSystemReset.current = true;
      return;
    }
    setSelection({ type: 'system' });
    setPlacements([]);
    setPlacementLaneHints({});
    setProjection(null);
    setStructurePicker(null);
    setStructureAddFeedback(null);
    setTargetArchetype(system.primary_archetype ?? archetypeFromEconomy(system.primary_economy) ?? 'refinery_industrial');
    appliedProjectFingerprint.current = null;
  }, [system.id64, system.primary_archetype, system.primary_economy]);

  useEffect(() => {
    setAdvancedInitialMode(initialCockpitMode);
    if (initialCockpitMode !== 'build-plan') {
      setAdvancedPanelOpen(true);
    }
  }, [initialCockpitMode]);

  useEffect(() => {
    if (placements.length > 0 || targetArchetype) return;
    setTargetArchetype(suggestedArchetype);
  }, [placements.length, suggestedArchetype, targetArchetype]);

  useEffect(() => {
    if (!structureAddFeedback || structureAddFeedback.tone !== 'success') return undefined;
    const timeout = window.setTimeout(() => setStructureAddFeedback(null), 5000);
    return () => window.clearTimeout(timeout);
  }, [structureAddFeedback]);

  const planSnapshot = useMemo<TopologyPlanSnapshot>(() => ({
    placements,
    templates,
    targetArchetype,
    slotPredictions: slotPredictionsQuery.data ?? null,
    placementLaneHints,
    projection,
  }), [placementLaneHints, placements, projection, slotPredictionsQuery.data, targetArchetype, templates]);
  const occupancySummary = useMemo(
    () => buildPlannerCanvasOccupancySummary(system, planSnapshot),
    [planSnapshot, system],
  );

  const projectState = useWorkspaceProjectState(system, planSnapshot, initialProjectId);
  useEffect(() => {
    onProjectContextChange?.({
      activeProject: projectState.activeProject,
      unsavedChanges: projectState.unsavedChanges,
      plannedStructureCount: placements.length,
      deleteActiveProject: projectState.deleteActiveProject,
    });
  }, [onProjectContextChange, placements.length, projectState.activeProject, projectState.deleteActiveProject, projectState.unsavedChanges]);
  const projectRequestFingerprint = useMemo(
    () => projectState.projectRequest ? JSON.stringify({
      target_archetype: projectState.projectRequest.target_archetype,
      placements: resequence(projectState.projectRequest.placements).map((placement) => ({
        facility_template_id: placement.facility_template_id,
        local_body_id: placement.local_body_id ?? null,
        is_primary_port: Boolean(placement.is_primary_port),
        build_order: placement.build_order,
      })),
    }) : null,
    [projectState.projectRequest],
  );
  const currentPlanFingerprint = useMemo(
    () => JSON.stringify({
      target_archetype: targetArchetype,
      placements: resequence(placements).map((placement) => ({
        facility_template_id: placement.facility_template_id,
        local_body_id: placement.local_body_id ?? null,
        is_primary_port: Boolean(placement.is_primary_port),
        build_order: placement.build_order,
      })),
    }),
    [placements, targetArchetype],
  );

  useEffect(() => {
    if (!projectState.projectRequest || !projectRequestFingerprint) return;
    if (appliedProjectFingerprint.current === projectRequestFingerprint) return;
    if (projectRequestFingerprint === currentPlanFingerprint) {
      appliedProjectFingerprint.current = projectRequestFingerprint;
      return;
    }
    appliedProjectFingerprint.current = projectRequestFingerprint;
    setTargetArchetype(projectState.projectRequest.target_archetype);
    setPlacements(resequence(projectState.projectRequest.placements));
    setPlacementLaneHints({});
    setProjection(null);
  }, [currentPlanFingerprint, projectRequestFingerprint, projectState.projectRequest]);

  const selectedContext = useMemo(
    () => describeTopologySelection(selection, system, planSnapshot),
    [planSnapshot, selection, system],
  );

  const planningFocusLabel = getPlanningFocusLabel(selection, system, planSnapshot);
  const pickerBody = useMemo(() => {
    if (!structurePicker) return null;
    return (system.bodies ?? []).find((body) => sameBodyId(body.id, structurePicker.bodyId)) ?? null;
  }, [structurePicker, system.bodies]);
  const systemEconomyLedger = useMemo(() => buildPlanningEconomyLedger({
    placements,
    projectedPlacements: projection?.placements ?? [],
    templates,
  }), [placements, projection?.placements, templates]);
  const prerequisiteIssues = useMemo(() => buildPlanPrerequisiteIssues(placements, templates), [placements, templates]);
  const dockSummary = useMemo(() => {
    const counts = [
      placements.length > 0 ? `${placements.length} planned` : null,
      projection ? `${projection.placements.length} projected` : null,
    ].filter(Boolean);
    if (counts.length === 0) {
      return 'Choose a body to begin planning.';
    }
    return `${selectedContext.label} / ${counts.join(' / ')}`;
  }, [placements.length, projection, selectedContext.label]);
  const activeCockpitModeMeta = WORKSPACE_MODE_META[advancedInitialMode];
  const activeProjectLabel = projectState.activeProject?.project_name ?? 'Unsaved planning surface';
  const contextSummary = selection.type === 'system'
    ? 'System-wide planning focus'
    : selectedContext.label;

  const requestAddStructure = useCallback((bodyId: string, lane: BodyPlannerLane) => {
    const state = getPlannerLaneCapacityState(system, planSnapshot, bodyId, lane);
    if (state.disabledReason) {
      setStructureAddFeedback({ tone: 'error', message: state.disabledReason });
      setStructurePicker(null);
      return;
    }
    setSelection({ type: 'body', bodyId });
    setStructureAddFeedback(null);
    setStructurePicker({ bodyId, lane });
  }, [planSnapshot, system]);

  const addStructure = useCallback((bodyId: string, lane: BodyPlannerLane, templateId: string) => {
    const template = templates.find((candidate) => candidate.id === templateId);
    if (!template) {
      return { ok: false as const, message: 'Facility template is no longer available.' };
    }
    const body = (system.bodies ?? []).find((candidate) => sameBodyId(candidate.id, bodyId));
    if (!body) {
      return { ok: false as const, message: 'Selected body is no longer available.' };
    }
    const disabledReason = laneDisabledReason(body, lane);
    if (disabledReason) {
      return { ok: false as const, message: disabledReason };
    }
    const capacityState = getPlannerLaneCapacityState(system, planSnapshot, bodyId, lane);
    if (capacityState.disabledReason) {
      return { ok: false as const, message: capacityState.disabledReason };
    }
    if (!templateMatchesLane(template, lane) || !templateCanFitBody(template, body, lane)) {
      return { ok: false as const, message: `${templateDisplayName(template)} is not compatible with this ${lane === 'orbital' ? 'orbit' : 'surface'} lane.` };
    }
    const nextPlacements = resequence([
      ...placementsRef.current,
      {
        facility_template_id: template.id,
        local_body_id: bodyId,
        is_primary_port: template.is_port && !placementsRef.current.some((placement) => placement.is_primary_port),
        build_order: placementsRef.current.length + 1,
      },
    ]);
    setSelection({ type: 'body', bodyId });
    setPlacements(nextPlacements);
    setPlacementLaneHints((currentHints) => ({ ...currentHints, [nextPlacements.length - 1]: lane }));
    return {
      ok: true as const,
      message: `Added ${templateDisplayName(template)} to ${describePlacementTarget(body, lane)}.`,
    };
  }, [planSnapshot, system, templates]);

  const pickStructureTemplate = useCallback((templateId: string) => {
    if (!structurePicker) return;
    const result = addStructure(structurePicker.bodyId, structurePicker.lane, templateId);
    setStructureAddFeedback({ tone: result.ok ? 'success' : 'error', message: result.message });
    if (result.ok) {
      setStructurePicker(null);
    }
  }, [addStructure, structurePicker]);

  const handleWorkspaceCommandHandled = useCallback((token: number) => {
    setLastHandledWorkspaceCommandToken((current) => (token > current ? token : current));
    setWorkspaceCommand((current) => (current?.token === token ? null : current));
  }, []);

  const handleAdvancedPlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    if (!placementsEqual(placementsRef.current, snapshot.placements)) {
      setPlacements(resequence(snapshot.placements));
      setPlacementLaneHints({});
    }
    setTargetArchetype((current) => current === snapshot.targetArchetype ? current : snapshot.targetArchetype);
    setProjection((current) => projectionEqual(current, snapshot.projection) ? current : snapshot.projection ?? null);
  }, []);

  const openCockpitMode = useCallback((mode: SimulationWorkspaceMode) => {
    setAdvancedInitialMode(mode);
    setAdvancedPanelOpen(true);
    onCockpitModeChange?.(mode);
  }, [onCockpitModeChange]);

  const handleCockpitModeChange = useCallback((mode: SimulationWorkspaceMode) => {
    setAdvancedInitialMode(mode);
    onCockpitModeChange?.(mode);
  }, [onCockpitModeChange]);

  return (
    <section
      aria-label="Whole-system colony planner"
      data-testid="whole-system-colony-planner"
      data-layout="stage17n-docked-context-canvas"
      className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,28rem)] xl:items-start"
    >
      <main
        aria-label="Whole-system build canvas surface"
        data-testid="workspace-planner-content"
        data-layout="main-system-canvas"
        data-readability="stage17n"
        className="order-1 min-w-0 space-y-3"
      >
        <PlannerStatusStrip
          selection={selection}
          planningFocusLabel={planningFocusLabel}
          placementCount={placements.length}
          projectedCount={projection?.placements.length ?? 0}
          existingCount={occupancySummary.existingCount}
          inferredExistingCount={occupancySummary.inferredExistingCount}
          emptySlotCount={occupancySummary.emptySlotCount}
          unresolvedExistingCount={occupancySummary.unresolvedExistingCount}
          unsavedChanges={projectState.unsavedChanges}
          economyLedger={systemEconomyLedger}
          prerequisiteIssueCount={prerequisiteIssues.length}
        />
        {(structurePicker || structureAddFeedback) && (
          <div className="space-y-2" data-testid="canvas-structure-picker-region">
            {structureAddFeedback && (
              <p
                role={structureAddFeedback.tone === 'error' ? 'alert' : 'status'}
                data-testid="canvas-add-structure-feedback"
                className={[
                  'rounded border px-3 py-2 text-sm leading-relaxed',
                  structureAddFeedback.tone === 'error'
                    ? 'border-gold/35 bg-gold/10 text-gold'
                    : 'border-green/35 bg-green/10 text-green',
                ].join(' ')}
              >
                {structureAddFeedback.message}
              </p>
            )}
            <CanvasStructurePicker
              body={pickerBody}
              lane={structurePicker?.lane ?? null}
              templates={templates}
              placements={placements}
              templatesLoading={templatesQuery.isLoading}
              templatesErrorMessage={templatesQuery.isError ? templatesQuery.error?.message ?? 'Facility catalogue failed to load.' : null}
              onClose={() => setStructurePicker(null)}
              onPickTemplate={pickStructureTemplate}
            />
          </div>
        )}
        <SystemBuildMapCanvas
          system={system}
          snapshot={planSnapshot}
          selection={selection}
          onSelect={setSelection}
          onRequestAddStructure={requestAddStructure}
          prerequisiteIssues={prerequisiteIssues}
        />
        <section
          data-testid="colony-cockpit-launch-strip"
          className="rounded-chunk-lg border border-cyan/25 bg-[linear-gradient(180deg,rgba(34,211,238,0.08),rgba(15,23,42,0.18))] p-3 shadow-[0_20px_40px_-34px_rgba(34,211,238,0.7)]"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Colony Cockpit</div>
                <span
                  data-testid="colony-cockpit-active-mode-chip"
                  className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange"
                >
                  {workspaceModeLabel(advancedInitialMode)}
                </span>
                {advancedPanelOpen ? (
                  <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">
                    Live mode
                  </span>
                ) : (
                  <span className="rounded border border-border/60 bg-bg3/35 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk">
                    Ready to open
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-silver">
                {activeCockpitModeMeta.summary}
              </p>
              <p
                data-testid="colony-cockpit-active-mode-emphasis"
                className="mt-1 text-xs leading-relaxed text-silver-dk"
              >
                {activeCockpitModeMeta.emphasis}
              </p>
            </div>
            <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
              Route-aware mode handoff
            </span>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <div className="rounded border border-border/60 bg-bg3/35 p-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Project context</div>
              <div className="mt-1 text-sm text-silver">{activeProjectLabel}</div>
              <div className="mt-1 text-xs text-silver-dk">
                {projectState.unsavedChanges ? 'Unsaved changes are still local to this browser.' : 'Planner state is saved locally or still blank.'}
              </div>
            </div>
            <div className="rounded border border-border/60 bg-bg3/35 p-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Planning focus</div>
              <div className="mt-1 text-sm text-silver">{contextSummary}</div>
              <div className="mt-1 text-xs text-silver-dk">
                {placements.length} planned / {projection?.placements.length ?? 0} projected
              </div>
            </div>
            <div className="rounded border border-border/60 bg-bg3/35 p-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Best next move</div>
              <div className="mt-1 text-sm text-silver">{activeCockpitModeMeta.helper}</div>
              <div className="mt-1 text-xs text-silver-dk">
                Keep one canonical Plan surface while switching review depth intentionally.
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {([
              ['build-plan', 'Build Plan'],
              ['suggested-builds', 'Suggested Builds'],
              ['preview', 'Preview'],
              ['sequence', 'Sequence'],
              ['evidence', 'Evidence'],
              ['validation', 'Validation'],
              ['export', 'Export'],
            ] as Array<[SimulationWorkspaceMode, string]>).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                data-testid={`colony-cockpit-open-${mode}`}
                onClick={() => openCockpitMode(mode)}
                className={[
                  'rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
                  advancedPanelOpen && advancedInitialMode === mode
                    ? 'border-orange/55 bg-orange/15 text-orange'
                    : 'border-border/60 bg-bg3/35 text-silver-dk hover:border-cyan/45 hover:text-cyan',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {activeCockpitModeMeta.nextModes.map((mode) => (
              <button
                key={mode}
                type="button"
                data-testid={`colony-cockpit-suggested-next-${mode}`}
                onClick={() => openCockpitMode(mode)}
                className="rounded border border-cyan/30 bg-cyan/10 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan transition-colors hover:border-cyan/50 hover:bg-cyan/15"
              >
                Next: {workspaceModeLabel(mode)}
              </button>
            ))}
          </div>
        </section>
        <AdvancedPlannerDrawer
          open={advancedPanelOpen}
          initialMode={advancedInitialMode}
          system={system}
          snapshot={planSnapshot}
          selection={selection}
          declaredRoles={projectState.declaredRoles}
          workspaceCommand={workspaceCommand}
          lastHandledWorkspaceCommandToken={lastHandledWorkspaceCommandToken}
          onOpenChange={(open) => {
            setAdvancedPanelOpen(open);
            if (!open) {
              setAdvancedInitialMode('build-plan');
              onCockpitModeChange?.('build-plan');
            }
          }}
          onActiveModeChange={handleCockpitModeChange}
          onPlanSnapshotChange={handleAdvancedPlanSnapshotChange}
          onWorkspaceCommandHandled={handleWorkspaceCommandHandled}
        />
      </main>

      <div
        className="order-2 min-w-0 max-xl:sticky max-xl:bottom-3 max-xl:z-30 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
        data-testid="planner-telemetry-region"
        data-layout="plan-details-panel"
        data-mobile-dock={telemetryDockOpen ? 'open' : 'closed'}
      >
        <button
          type="button"
          data-testid="planner-telemetry-dock-toggle"
          aria-expanded={telemetryDockOpen}
          aria-controls="planner-telemetry-dock-content"
          onClick={() => setTelemetryDockOpen((open) => !open)}
          className="flex w-full items-center justify-between gap-3 rounded-chunk-lg border border-cyan/35 bg-bg2/95 px-3 py-2 shadow-metal"
        >
          <span className="flex min-w-0 items-center gap-2">
              <PanelRight size={16} className="shrink-0 text-cyan" />
            <span className="min-w-0 text-left">
              <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Plan details</span>
              <span className="block truncate text-[11px] text-silver-dk">
                {dockSummary}
              </span>
            </span>
          </span>
          <ChevronDown
            size={16}
            className={['shrink-0 text-silver-dk transition-transform', telemetryDockOpen ? 'rotate-180' : ''].join(' ')}
          />
        </button>
        <div
          id="planner-telemetry-dock-content"
          data-testid="planner-telemetry-dock-content"
          data-open={telemetryDockOpen ? 'true' : 'false'}
          className={[telemetryDockOpen ? 'block' : 'hidden xl:block', 'max-xl:mt-2 max-xl:max-h-[min(76vh,42rem)] max-xl:overflow-y-auto max-xl:rounded-chunk-lg max-xl:border max-xl:border-cyan/25 max-xl:bg-bg1/95 max-xl:p-2 max-xl:shadow-metal xl:space-y-3'].join(' ')}
        >
          <WorkspaceSummaryRail
            system={system}
            snapshot={planSnapshot}
            economyLedger={systemEconomyLedger}
            prerequisiteIssues={prerequisiteIssues}
            selection={selection}
            selectedContext={selectedContext}
            projects={projectState.projects}
            activeProject={projectState.activeProject}
            pendingProjectId={projectState.pendingProjectId}
            projectName={projectState.projectName}
            projectNotes={projectState.projectNotes}
            unsavedChanges={projectState.unsavedChanges}
            confirmArchive={projectState.confirmArchive}
            onPendingProjectChange={projectState.setPendingProjectId}
            onLoadProject={projectState.loadProject}
            onProjectNameChange={projectState.setProjectName}
            onProjectNotesChange={projectState.setProjectNotes}
            onSaveProject={projectState.saveProject}
            onRenameProject={projectState.renameProject}
            onDuplicateProject={projectState.duplicateProject}
            onArchiveProject={projectState.archiveProject}
            onConfirmArchiveChange={projectState.setConfirmArchive}
          />
        </div>
      </div>
    </section>
  );
}
function placementsEqual(a: SimulateBuildPlacement[], b: SimulateBuildPlacement[]) {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) {
    const left = a[index];
    const right = b[index];
    if (left.facility_template_id !== right.facility_template_id) return false;
    if ((left.local_body_id ?? null) !== (right.local_body_id ?? null)) return false;
    if ((left.is_primary_port ?? false) !== (right.is_primary_port ?? false)) return false;
    if ((left.build_order ?? null) !== (right.build_order ?? null)) return false;
  }
  return true;
}

function projectionEqual(
  a: TopologyPlanSnapshot['projection'],
  b: TopologyPlanSnapshot['projection'],
) {
  if (a === b) return true;
  if (!a || !b) return !a && !b;
  if (a.candidateId !== b.candidateId) return false;
  if (a.label !== b.label) return false;
  return placementsEqual(a.placements, b.placements);
}
