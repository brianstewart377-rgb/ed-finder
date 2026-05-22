import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, PanelRight } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import type { FacilityTemplate, SimulateBuildPlacement, SimulationSummary, SystemBody, SystemDetail } from '@/types/api';
import { getFacilityTemplates, getSimulationSummary, getSlotPredictions } from '@/lib/api';
import type { SimulationWorkspaceMode } from '@/features/system-detail/simulation-preview/WorkspaceModeTabs';
import { bodyIdKey, sameBodyId } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import { archetypeFromEconomy, resequence } from '@/features/system-detail/simulation-preview/utils/placementHelpers';
import type { BodyPlannerLane } from './BodySlotPlanner';
import {
  describeTopologySelection,
  type TopologyPlanSnapshot,
  type TopologySelection,
} from './ColonyTopologyRail';
import { SelectedBodyPlannerCanvas } from './SelectedBodyPlannerCanvas';
import { PlannerStatusStrip } from './PlannerStatusStrip';
import { WorkspaceSummaryRail } from './WorkspaceSummaryRail';
import { useWorkspaceProjectState } from './useWorkspaceProjectState';
import { getPlanningFocusLabel, type PlannerWorkspaceCommand } from './workspaceUtils';
import { buildPlanningEconomyLedger } from './planningEconomy';
import { AdvancedPlannerDrawer } from './AdvancedPlannerDrawer';
import { RavenPlannerTelemetryPanel, RavenStylePlannerCanvas } from './RavenStylePlannerCanvas';

export function WholeSystemColonyPlanner({ system }: { system: SystemDetail }) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  const [placements, setPlacements] = useState<SimulateBuildPlacement[]>([]);
  const [targetArchetype, setTargetArchetype] = useState(() => (
    archetypeFromEconomy(system.economy_suggestion ?? system.primary_economy) ?? 'refinery_industrial'
  ));
  const [projection, setProjection] = useState<TopologyPlanSnapshot['projection']>(null);
  const [advancedPanelOpen, setAdvancedPanelOpen] = useState(false);
  const [advancedInitialMode, setAdvancedInitialMode] = useState<SimulationWorkspaceMode>('build-plan');
  const [telemetryDockOpen, setTelemetryDockOpen] = useState(false);
  const [workspaceCommand, setWorkspaceCommand] = useState<PlannerWorkspaceCommand | null>(null);
  const [lastHandledWorkspaceCommandToken, setLastHandledWorkspaceCommandToken] = useState(0);
  const workspaceCommandToken = useRef(0);
  const appliedProjectFingerprint = useRef<string | null>(null);

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
    ?? archetypeFromEconomy(system.economy_suggestion ?? system.primary_economy)
    ?? 'refinery_industrial';

  useEffect(() => {
    setSelection({ type: 'system' });
    setPlacements([]);
    setProjection(null);
    setTargetArchetype(archetypeFromEconomy(system.economy_suggestion ?? system.primary_economy) ?? 'refinery_industrial');
    appliedProjectFingerprint.current = null;
  }, [system.economy_suggestion, system.id64, system.primary_economy]);

  useEffect(() => {
    if (placements.length > 0) return;
    setTargetArchetype((current) => current || suggestedArchetype);
  }, [placements.length, suggestedArchetype]);

  const planSnapshot = useMemo<TopologyPlanSnapshot>(() => ({
    placements,
    templates,
    targetArchetype,
    slotPredictions: slotPredictionsQuery.data ?? null,
    projection,
  }), [placements, projection, slotPredictionsQuery.data, targetArchetype, templates]);

  const projectState = useWorkspaceProjectState(system, planSnapshot);
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

  useEffect(() => {
    if (!projectState.projectRequest || !projectRequestFingerprint) return;
    if (appliedProjectFingerprint.current === projectRequestFingerprint) return;
    appliedProjectFingerprint.current = projectRequestFingerprint;
    setTargetArchetype(projectState.projectRequest.target_archetype);
    setPlacements(resequence(projectState.projectRequest.placements));
    setProjection(null);
  }, [projectRequestFingerprint, projectState.projectRequest]);

  const selectedContext = useMemo(
    () => describeTopologySelection(selection, system, planSnapshot),
    [planSnapshot, selection, system],
  );

  const planningFocusLabel = getPlanningFocusLabel(selection, system, planSnapshot);
  const selectedBody = useMemo(
    () => selectedBodyFromSelection(selection, system.bodies ?? [], placements, projection?.placements ?? []),
    [placements, projection?.placements, selection, system.bodies],
  );
  const selectedPlacementIndex = selection.type === 'placement' ? selection.placementIndex : null;
  const selectedProjectedPlacementIndex = selection.type === 'projected-placement' ? selection.placementIndex : null;
  const systemEconomyLedger = useMemo(() => buildPlanningEconomyLedger({
    placements,
    projectedPlacements: projection?.placements ?? [],
    templates,
  }), [placements, projection?.placements, templates]);

  const openAdvanced = useCallback((mode: SimulationWorkspaceMode = 'build-plan') => {
    setAdvancedInitialMode(mode);
    setAdvancedPanelOpen(true);
  }, []);

  const addStructure = useCallback((bodyId: string, _lane: BodyPlannerLane, templateId: string) => {
    const template = templates.find((candidate) => candidate.id === templateId);
    if (!template) return;
    setSelection({ type: 'body', bodyId });
    setPlacements((current) => resequence([
      ...current,
      {
        facility_template_id: template.id,
        local_body_id: bodyId,
        is_primary_port: template.is_port && !current.some((placement) => placement.is_primary_port),
        build_order: current.length + 1,
      },
    ]));
  }, [templates]);

  const issueWorkspaceCommand = useCallback((kind: PlannerWorkspaceCommand['kind'], bodyId: string, templateId?: string | null) => {
    workspaceCommandToken.current += 1;
    setWorkspaceCommand({
      token: workspaceCommandToken.current,
      kind,
      bodyId,
      templateId: templateId ?? null,
    });
  }, []);

  const reviewBodyStructures = useCallback((bodyId: string) => {
    setSelection({ type: 'body', bodyId });
    openAdvanced('build-plan');
    issueWorkspaceCommand('review-structures', bodyId);
  }, [issueWorkspaceCommand, openAdvanced]);

  const handleWorkspaceCommandHandled = useCallback((token: number) => {
    setLastHandledWorkspaceCommandToken((current) => (token > current ? token : current));
    setWorkspaceCommand((current) => (current?.token === token ? null : current));
  }, []);

  const handleAdvancedPlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    setPlacements((current) => placementsEqual(current, snapshot.placements) ? current : resequence(snapshot.placements));
    setTargetArchetype((current) => current === snapshot.targetArchetype ? current : snapshot.targetArchetype);
    setProjection((current) => projectionEqual(current, snapshot.projection) ? current : snapshot.projection ?? null);
  }, []);

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
          unsavedChanges={projectState.unsavedChanges}
          economyLedger={systemEconomyLedger}
        />
        <RavenStylePlannerCanvas
          system={system}
          snapshot={planSnapshot}
          selection={selection}
          expandedBodyDetail={selectedBody ? (
            <SelectedBodyPlannerCanvas
              system={system}
              body={selectedBody}
              snapshot={planSnapshot}
              selection={selection}
              selectedPlacementIndex={selectedPlacementIndex}
              selectedProjectedPlacementIndex={selectedProjectedPlacementIndex}
              templatesLoading={templatesQuery.isLoading}
              templatesErrorMessage={templatesQuery.isError ? templatesQuery.error?.message ?? 'Facility catalogue failed to load.' : null}
              onAddStructure={addStructure}
              onOpenAdvanced={openAdvanced}
              onReviewStructures={reviewBodyStructures}
              onSelectBody={(bodyId) => setSelection({ type: 'body', bodyId })}
              onSelectPlacement={(placementIndex) => setSelection({ type: 'placement', placementIndex })}
              onSelectProjectedPlacement={(placementIndex) => setSelection({ type: 'projected-placement', placementIndex })}
            />
          ) : null}
          onSelect={setSelection}
        />
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
            setAdvancedInitialMode('build-plan');
            setAdvancedPanelOpen(open);
          }}
          onPlanSnapshotChange={handleAdvancedPlanSnapshotChange}
          onWorkspaceCommandHandled={handleWorkspaceCommandHandled}
        />
      </main>

      <div
        className="order-2 min-w-0 max-xl:sticky max-xl:bottom-3 max-xl:z-30 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
        data-testid="planner-telemetry-region"
        data-layout="telemetry-context-panel"
        data-mobile-dock={telemetryDockOpen ? 'open' : 'closed'}
      >
        <button
          type="button"
          data-testid="planner-telemetry-dock-toggle"
          aria-expanded={telemetryDockOpen}
          aria-controls="planner-telemetry-dock-content"
          onClick={() => setTelemetryDockOpen((open) => !open)}
          className="flex w-full items-center justify-between gap-3 rounded-chunk-lg border border-cyan/35 bg-bg2/95 px-3 py-2 shadow-metal xl:hidden"
        >
          <span className="flex min-w-0 items-center gap-2">
            <PanelRight size={16} className="shrink-0 text-cyan" />
            <span className="min-w-0 text-left">
              <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Telemetry</span>
              <span className="block truncate text-[11px] text-silver-dk">
                {selectedContext.label} / {placements.length} planned{projection ? ` / ${projection.placements.length} projected` : ''}
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
          <RavenPlannerTelemetryPanel
            system={system}
            snapshot={planSnapshot}
            economyLedger={systemEconomyLedger}
            selectedContext={selectedContext}
            selection={selection}
          />
          <WorkspaceSummaryRail
            system={system}
            snapshot={planSnapshot}
            economyLedger={systemEconomyLedger}
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
function selectedBodyFromSelection(
  selection: TopologySelection,
  bodies: SystemBody[],
  placements: SimulateBuildPlacement[],
  projectedPlacements: SimulateBuildPlacement[],
): SystemBody | null {
  if (selection.type === 'body') {
    return bodies.find((body) => sameBodyId(body.id, selection.bodyId)) ?? null;
  }
  if (selection.type === 'placement' || selection.type === 'projected-placement') {
    const placement = selection.type === 'placement'
      ? placements[selection.placementIndex]
      : projectedPlacements[selection.placementIndex];
    const bodyId = placement?.local_body_id != null ? bodyIdKey(placement.local_body_id) : null;
    return bodyId ? bodies.find((body) => sameBodyId(body.id, bodyId)) ?? null : null;
  }
  return null;
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
