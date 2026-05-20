import { useCallback, useMemo, useRef, useState } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import {
  bodyDisplayName,
  getBodyGroupWarnings,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
import { BodySlotPlanner, type BodyPlannerLane } from './BodySlotPlanner';
import {
  ColonyTopologyRail,
  describeTopologySelection,
  type TopologyPlanSnapshot,
  type TopologySelection,
} from './ColonyTopologyRail';
import { useWorkspaceProjectState } from './useWorkspaceProjectState';
import { WorkspaceSummaryRail } from './WorkspaceSummaryRail';
import { getPlanningFocusLabel, type PlannerWorkspaceCommand } from './workspaceUtils';

interface PlacementViewItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
  bodyId: string;
  hasUnknownBody: boolean;
}

interface ProjectedPlacementViewItem {
  placement: SimulateBuildPlacement;
  index: number;
  template: FacilityTemplate | undefined;
}

export function WorkspaceGrid({ system }: { system: SystemDetail }) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  const [workspaceCommand, setWorkspaceCommand] = useState<PlannerWorkspaceCommand | null>(null);
  const [planSnapshot, setPlanSnapshot] = useState<TopologyPlanSnapshot>({
    placements: [],
    templates: [],
    targetArchetype: 'refinery_industrial',
    projection: null,
  });
  const [advancedPanelOpen, setAdvancedPanelOpen] = useState(false);
  const [pickerContext, setPickerContext] = useState<{ bodyId: string; lane: BodyPlannerLane } | null>(null);
  const workspaceCommandToken = useRef(0);
  const projectState = useWorkspaceProjectState(system, planSnapshot);

  const handlePlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    setPlanSnapshot((previous) => (
      planSnapshotsEqual(previous, snapshot) ? previous : snapshot
    ));
  }, []);

  const selectedContext = useMemo(
    () => describeTopologySelection(selection, system, planSnapshot),
    [planSnapshot, selection, system],
  );

  const issueWorkspaceCommand = useCallback((kind: PlannerWorkspaceCommand['kind'], bodyId: string, templateId?: string | null) => {
    workspaceCommandToken.current += 1;
    setWorkspaceCommand({
      token: workspaceCommandToken.current,
      kind,
      bodyId,
      templateId: templateId ?? null,
    });
  }, []);

  const planningFocusLabel = getPlanningFocusLabel(selection, system);

  const selectedBody = useMemo(() => {
    if (selection.type === 'body') {
      return (system.bodies ?? []).find((body) => body.id != null && String(body.id) === selection.bodyId) ?? null;
    }
    if (selection.type === 'placement') {
      const placement = planSnapshot.placements[selection.placementIndex];
      const bodyId = placement?.local_body_id != null ? String(placement.local_body_id) : null;
      return bodyId ? (system.bodies ?? []).find((body) => body.id != null && String(body.id) === bodyId) ?? null : null;
    }
    return null;
  }, [planSnapshot.placements, selection, system.bodies]);

  const pickerBody = useMemo(() => {
    if (!pickerContext) return null;
    return (system.bodies ?? []).find((body) => body.id != null && String(body.id) === pickerContext.bodyId) ?? null;
  }, [pickerContext, system.bodies]);

  const selectedPlacementIndex = selection.type === 'placement' ? selection.placementIndex : null;

  const openBodyPicker = useCallback((bodyId: string, lane: BodyPlannerLane) => {
    setPickerContext({ bodyId, lane });
  }, []);

  const closeBodyPicker = useCallback(() => {
    setPickerContext(null);
  }, []);

  const reviewBodyStructures = useCallback((bodyId: string) => {
    setAdvancedPanelOpen(true);
    issueWorkspaceCommand('review-structures', bodyId);
  }, [issueWorkspaceCommand]);

  const pickTemplateForBody = useCallback((templateId: string) => {
    if (!pickerContext) return;
    issueWorkspaceCommand('add-structure', pickerContext.bodyId, templateId);
    setPickerContext(null);
  }, [issueWorkspaceCommand, pickerContext]);

  const focusPlacement = useCallback((placementIndex: number) => {
    setSelection({ type: 'placement', placementIndex });
    setAdvancedPanelOpen(true);
    const placement = planSnapshot.placements[placementIndex];
    if (placement?.local_body_id != null) {
      issueWorkspaceCommand('review-structures', String(placement.local_body_id));
    }
  }, [issueWorkspaceCommand, planSnapshot.placements]);

  return (
    <section
      aria-label="Colony Planner application shell"
      data-testid="planner-workspace-shell-v2"
      className="grid gap-4 lg:grid-cols-[16.5rem_minmax(0,1fr)_14rem] lg:items-start"
    >
      <main
        aria-label="Planning workspace content"
        data-testid="workspace-planner-content"
        className="order-1 min-w-0 rounded-chunk-lg border border-orange/25 bg-bg1/70 p-3 shadow-metal lg:order-2 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto"
      >
        <WorkspaceIntro
          selection={selection}
          hasPlacements={planSnapshot.placements.length > 0}
          planningFocusLabel={planningFocusLabel}
          unsavedChanges={projectState.unsavedChanges}
        />
        <BodyPlanningSurface
          body={selectedBody}
          snapshot={planSnapshot}
          selection={selection}
          selectedPlacementIndex={selectedPlacementIndex}
          onAddStructureHere={openBodyPicker}
          onReviewStructures={reviewBodyStructures}
          onSelectPlacement={focusPlacement}
        />
        <BodyStructurePickerDrawer
          body={pickerBody}
          lane={pickerContext?.lane ?? null}
          templates={planSnapshot.templates}
          onClose={closeBodyPicker}
          onPickTemplate={pickTemplateForBody}
        />

        <section className="mt-3 rounded-chunk-lg border border-border/55 bg-bg2/35">
          <button
            type="button"
            data-testid="advanced-workspace-toggle"
            onClick={() => setAdvancedPanelOpen((value) => !value)}
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
          >
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Advanced planner views</div>
              <p className="mt-0.5 font-mono text-[10px] text-silver-dk">
                Suggested Builds, Preview, and list editor remain explicit tools.
              </p>
            </div>
            <span className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver">
              {advancedPanelOpen ? 'Hide' : 'Open'}
            </span>
          </button>
          <div className={advancedPanelOpen ? 'border-t border-border/60 px-2 pb-2' : 'hidden'}>
            <SimulationPreviewPanel
              system={system}
              selectedPlan={null}
              onPlanSnapshotChange={handlePlanSnapshotChange}
              topologySelection={selection}
              initialRequest={projectState.projectRequest}
              declaredRoles={projectState.declaredRoles}
              workspaceCommand={workspaceCommand}
            />
          </div>
        </section>
      </main>
      <div className="order-3 lg:order-3">
        <WorkspaceSummaryRail
          system={system}
          snapshot={planSnapshot}
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
      <div className="order-2 lg:order-1">
        <ColonyTopologyRail
          system={system}
          snapshot={planSnapshot}
          selection={selection}
          onSelect={setSelection}
        />
      </div>
    </section>
  );
}

function BodyPlanningSurface({
  body,
  snapshot,
  selection,
  selectedPlacementIndex,
  onAddStructureHere,
  onReviewStructures,
  onSelectPlacement,
}: {
  body: SystemBody | null;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
  selectedPlacementIndex: number | null;
  onAddStructureHere: (bodyId: string, lane: BodyPlannerLane) => void;
  onReviewStructures: (bodyId: string) => void;
  onSelectPlacement: (placementIndex: number) => void;
}) {
  if (!body || body.id == null) {
    return (
      <section
        data-testid="body-planning-surface"
        className="mb-3 rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-3 font-mono text-[11px] leading-snug"
      >
        <div className="text-[10px] uppercase tracking-[0.16em] text-cyan">Body planning surface</div>
        <h3 className="mt-1 text-sm font-bold text-silver">Select a body to plan there</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <BodyStartAction label="Select a body" detail="Use the build tree on the left." />
          <BodyStartAction label="Generate strategy" detail="Open Suggested Builds in advanced views." />
          <BodyStartAction label="Start manually" detail="Pick a body, then add a structure." />
        </div>
        {selection.type === 'group' && (
          <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-2 py-1 text-gold">
            {selection.groupKey === 'unknown' ? 'Unknown placements need a matching body.' : 'Unassigned placements need a body.'}
          </p>
        )}
      </section>
    );
  }

  const bodyId = String(body.id);
  const templatesById = new Map(snapshot.templates.map((template) => [template.id, template]));
  const placements: PlacementViewItem[] = snapshot.placements
    .map((placement, index) => ({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
      bodyId: placement.local_body_id != null ? String(placement.local_body_id) : '',
      hasUnknownBody: false,
    }))
    .filter((item) => item.bodyId === bodyId);
  const warnings = getBodyGroupWarnings({ key: bodyId, body, placements });
  const projectedPlacements: ProjectedPlacementViewItem[] = (snapshot.projection?.placements ?? [])
    .map((placement, index) => ({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
    }))
    .filter((item) => item.placement.local_body_id != null && String(item.placement.local_body_id) === bodyId);

  const reviewBodyStructures = () => {
    onReviewStructures(bodyId);
  };

  return (
    <div data-testid="body-planning-surface">
      <BodySlotPlanner
        body={body}
        placements={placements}
        projectedPlacements={projectedPlacements}
        selectedPlacementIndex={selectedPlacementIndex}
        hasTemplates={snapshot.templates.length > 0}
        onSelectPlacement={onSelectPlacement}
        onAddLaneStructure={(lane) => onAddStructureHere(bodyId, lane)}
      />

      {warnings.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5 rounded border border-gold/30 bg-gold/6 px-3 py-2">
          {warnings.slice(0, 3).map((warning) => <BodyFact key={warning} label={warning} tone="gold" />)}
        </div>
      )}

      <div className="mb-3 flex justify-end">
        <button
          type="button"
          onClick={reviewBodyStructures}
          className="rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-cyan hover:bg-cyan/20"
        >
          Review structures
        </button>
      </div>
    </div>
  );
}

function BodyStructurePickerDrawer({
  body,
  lane,
  templates,
  onClose,
  onPickTemplate,
}: {
  body: SystemBody | null;
  lane: BodyPlannerLane | null;
  templates: FacilityTemplate[];
  onClose: () => void;
  onPickTemplate: (templateId: string) => void;
}) {
  const [query, setQuery] = useState('');

  if (!body || body.id == null || !lane) return null;

  const bodyName = bodyDisplayName(body);
  const laneLabel = lane === 'orbital' ? 'orbital' : lane === 'surface' ? 'surface' : 'flexible/unknown';
  const filtered = templates
    .filter((template) => templateMatchesLane(template, lane))
    .filter((template) => templateCanFitBody(template, body, lane))
    .filter((template) => {
      const text = `${template.name} ${template.id} ${template.category} ${template.economy ?? ''}`.toLowerCase();
      return text.includes(query.trim().toLowerCase());
    })
    .sort((a, b) => (a.tier - b.tier) || a.name.localeCompare(b.name));

  return (
    <section
      data-testid="body-structure-picker"
      className="mb-3 rounded-chunk-lg border border-orange/35 bg-bg2/75 px-3 py-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
            Add {laneLabel} structure
          </div>
          <h4 className="mt-0.5 text-sm font-bold text-silver">{bodyName}</h4>
          <p className="mt-0.5 font-mono text-[10px] text-silver-dk">
            Filtered to {laneLabel}-compatible templates for this body.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          Close
        </button>
      </div>

      <label className="mt-3 block">
        <span className="block text-[10px] uppercase tracking-[0.14em] text-silver-dk">Filter structures</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, economy, or category"
          className="mt-1 w-full"
        />
      </label>

      {templates.length === 0 ? (
        <p className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-[11px] text-gold">
          Facility catalogue is loading.
        </p>
      ) : filtered.length === 0 ? (
        <p className="mt-3 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-[11px] text-silver-dk">
          No matching {laneLabel} structures for this body and filter.
        </p>
      ) : (
        <div className="mt-3 grid max-h-72 gap-1.5 overflow-y-auto">
          {filtered.map((template) => (
            <button
              key={template.id}
              type="button"
              data-testid={`body-structure-template-${template.id}`}
              onClick={() => onPickTemplate(template.id)}
              className="flex items-center justify-between gap-2 rounded border border-border/55 bg-bg3/35 px-3 py-2 text-left hover:border-orange/45 hover:bg-orange/8"
            >
              <div className="min-w-0">
                <div className="truncate text-[11px] font-bold text-silver">{template.name}</div>
                <div className="mt-0.5 flex flex-wrap gap-1.5">
                  <BodyFact label={`tier ${template.tier}`} />
                  <BodyFact label={template.category} />
                  {template.economy && <BodyFact label={template.economy} />}
                  <BodyFact label={templateLocationKind(template)} tone="cyan" />
                </div>
              </div>
              <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-orange">
                Add
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function templateCanFitBody(template: FacilityTemplate, body: SystemBody, lane: BodyPlannerLane) {
  const location = templateLocationKind(template);
  if (lane === 'surface') {
    if (body.is_water_world) return false;
    if (body.is_landable === false) return false;
  }
  if (location === 'surface') return Boolean(body.is_landable) && !body.is_water_world;
  return true;
}

function templateMatchesLane(template: FacilityTemplate, lane: BodyPlannerLane) {
  const location = templateLocationKind(template);
  if (lane === 'orbital') return location === 'orbital' || location === 'both';
  if (lane === 'surface') return location === 'surface' || location === 'both';
  return location === 'both' || location === 'unknown';
}

function BodyStartAction({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-silver">{label}</div>
      <p className="mt-1 text-[10px] text-silver-dk">{detail}</p>
    </div>
  );
}

function BodyFact({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'orange' | 'gold' | 'cyan' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
            : tone === 'cyan'
              ? 'border-cyan/35 bg-cyan/10 text-cyan'
              : 'border-border/60 bg-bg3/45 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}

function WorkspaceIntro({
  selection,
  hasPlacements,
  planningFocusLabel,
  unsavedChanges,
}: {
  selection: TopologySelection;
  hasPlacements: boolean;
  planningFocusLabel: string | null;
  unsavedChanges: boolean;
}) {
  const title = selection.type === 'body' ? 'Body Planner' : 'Planning Workspace';
  return (
    <div className="mb-3 border-b border-border/70 pb-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-orange">
            {title}
          </h2>
          <p className="mt-1 max-w-2xl text-[11px] font-mono leading-snug text-silver-dk">
            {planningFocusLabel
              ? `Planning focus: ${planningFocusLabel}`
              : 'Select a body from the topology rail or open Suggested Builds.'}
          </p>
        </div>
        <WhatNextStrip hasPlacements={hasPlacements} unsavedChanges={unsavedChanges} />
      </div>
    </div>
  );
}

function WhatNextStrip({ hasPlacements, unsavedChanges }: { hasPlacements: boolean; unsavedChanges: boolean }) {
  const items = [
    hasPlacements ? 'Review body plan' : 'Select a body',
    hasPlacements ? 'Run Preview' : 'Generate strategy',
    unsavedChanges ? 'Save project' : 'Saved locally',
  ];

  return (
    <div className="flex flex-wrap gap-1.5" aria-label="What next">
      {items.map((item) => (
        <span key={item} className="rounded border border-border/60 bg-bg3/55 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk">
          {item}
        </span>
      ))}
    </div>
  );
}

function planSnapshotsEqual(a: TopologyPlanSnapshot, b: TopologyPlanSnapshot) {
  if (a === b) return true;
  if (a.targetArchetype !== b.targetArchetype) return false;
  if (!placementsEqual(a.placements, b.placements)) return false;
  if (!templatesEqual(a.templates, b.templates)) return false;
  if (!projectionEqual(a.projection, b.projection)) return false;
  return true;
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

function templatesEqual(a: FacilityTemplate[], b: FacilityTemplate[]) {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) {
    const left = a[index];
    const right = b[index];
    if (left.id !== right.id) return false;
    if (left.name !== right.name) return false;
    if (left.category !== right.category) return false;
    if ((left.allowed_location ?? null) !== (right.allowed_location ?? null)) return false;
    if ((left.tier ?? null) !== (right.tier ?? null)) return false;
    if ((left.economy ?? null) !== (right.economy ?? null)) return false;
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
