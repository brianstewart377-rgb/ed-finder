import { useCallback, useMemo, useRef, useState } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import {
  bodyDisplayName,
  bodyTags,
  getBodyGroupWarnings,
  getPlacementWarnings,
} from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import { templateLocationKind } from '@/features/system-detail/simulation-preview/structurePickerUtils';
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
  const [pickerBodyId, setPickerBodyId] = useState<string | null>(null);
  const workspaceCommandToken = useRef(0);
  const projectState = useWorkspaceProjectState(system, planSnapshot);

  const handlePlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    setPlanSnapshot(snapshot);
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
    if (!pickerBodyId) return null;
    return (system.bodies ?? []).find((body) => body.id != null && String(body.id) === pickerBodyId) ?? null;
  }, [pickerBodyId, system.bodies]);

  const selectedPlacementIndex = selection.type === 'placement' ? selection.placementIndex : null;

  const openBodyPicker = useCallback((bodyId: string) => {
    setPickerBodyId(bodyId);
  }, []);

  const closeBodyPicker = useCallback(() => {
    setPickerBodyId(null);
  }, []);

  const reviewBodyStructures = useCallback((bodyId: string) => {
    setAdvancedPanelOpen(true);
    issueWorkspaceCommand('review-structures', bodyId);
  }, [issueWorkspaceCommand]);

  const pickTemplateForBody = useCallback((templateId: string) => {
    if (!pickerBodyId) return;
    issueWorkspaceCommand('add-structure', pickerBodyId, templateId);
    setPickerBodyId(null);
  }, [issueWorkspaceCommand, pickerBodyId]);

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
      className="grid gap-4 xl:grid-cols-[18rem_minmax(0,1fr)_20rem] xl:items-start"
    >
      <ColonyTopologyRail
        system={system}
        snapshot={planSnapshot}
        selection={selection}
        onSelect={setSelection}
      />
      <main
        aria-label="Planning workspace content"
        data-testid="workspace-planner-content"
        className="min-w-0 rounded-chunk-lg border border-orange/25 bg-bg1/70 p-3 shadow-metal xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
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
  onAddStructureHere: (bodyId: string) => void;
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
  const tags = bodyTags(body).slice(0, 3);
  const projectedPlacements: ProjectedPlacementViewItem[] = (snapshot.projection?.placements ?? [])
    .map((placement, index) => ({
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
    }))
    .filter((item) => item.placement.local_body_id != null && String(item.placement.local_body_id) === bodyId);

  const focusAddStructure = () => onAddStructureHere(bodyId);
  const reviewBodyStructures = () => {
    onReviewStructures(bodyId);
  };

  return (
    <section
      data-testid="body-planning-surface"
      className="mb-3 rounded-chunk-lg border border-orange/30 bg-bg2/55 px-3 py-3 font-mono text-[11px] leading-snug"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.16em] text-orange">Planning on body</div>
          <h3 className="mt-0.5 truncate text-sm font-bold text-silver">{bodyDisplayName(body)}</h3>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <BodyFact label={body.subtype ?? body.body_type ?? 'Body'} />
            {tags.map((tag) => <BodyFact key={tag} label={tag} />)}
            <BodyFact label={`${placements.length} planned`} tone={placements.length > 0 ? 'orange' : 'silver'} />
            {projectedPlacements.length > 0 && <BodyFact label={`projected ${projectedPlacements.length}`} tone="cyan" />}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={focusAddStructure}
            disabled={snapshot.templates.length === 0}
            className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-orange hover:bg-orange/25 disabled:cursor-not-allowed disabled:opacity-45"
          >
            Add structure here
          </button>
          <button
            type="button"
            onClick={reviewBodyStructures}
            className="rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-cyan hover:bg-cyan/20"
          >
            Review structures
          </button>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {warnings.slice(0, 3).map((warning) => <BodyFact key={warning} label={warning} tone="gold" />)}
        </div>
      )}

      {snapshot.templates.length === 0 && (
        <div className="mt-3 rounded border border-gold/35 bg-gold/10 px-3 py-2 text-gold">
          Structure picker will open after the facility catalogue loads.
        </div>
      )}

      {snapshot.projection && projectedPlacements.length > 0 && (
        <div className="mt-3 rounded border border-cyan/30 bg-cyan/5 px-3 py-2 text-cyan">
          <div className="text-[10px] uppercase tracking-[0.14em]">Projected suggested build (not loaded)</div>
          <div className="mt-2 grid gap-1.5">
            {projectedPlacements.map((item) => (
              <ProjectedPlacementRow key={`body-projection-${item.index}-${item.placement.facility_template_id}`} item={item} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 grid gap-2" data-testid="body-planning-placements">
        {placements.length === 0 ? (
          <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2 text-silver-dk">
            No structures planned on this body yet.
          </div>
        ) : placements.map((item) => (
          <BodyPlacementRow
            key={`${item.index}-${item.placement.facility_template_id}`}
            item={item}
            body={body}
            selected={selectedPlacementIndex === item.index}
            onSelect={() => onSelectPlacement(item.index)}
          />
        ))}
      </div>
    </section>
  );
}

function BodyPlacementRow({
  item,
  body,
  selected,
  onSelect,
}: {
  item: PlacementViewItem;
  body: SystemBody;
  selected: boolean;
  onSelect: () => void;
}) {
  const location = item.template ? templateLocationKind(item.template) : 'unknown';
  const warnings = getPlacementWarnings(item, body);
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid={`body-placement-row-${item.index}`}
      aria-pressed={selected}
      className={[
        'flex w-full flex-wrap items-center justify-between gap-2 rounded border px-3 py-2 text-left transition-colors',
        selected
          ? 'border-orange/55 bg-orange/12'
          : 'border-border/55 bg-bg3/40 hover:border-orange/40 hover:bg-orange/6',
      ].join(' ')}
    >
      <div className="min-w-0">
        <div className="truncate text-[11px] font-bold text-silver">
          #{item.placement.build_order || item.index + 1} {item.template?.name ?? item.placement.facility_template_id}
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5">
          <BodyFact label={location} />
          {item.template?.economy && <BodyFact label={item.template.economy} />}
          {item.template?.category && <BodyFact label={item.template.category} />}
          {item.placement.is_primary_port && <BodyFact label="primary" tone="gold" />}
          {warnings.length > 0 && <BodyFact label={`${warnings.length} warnings`} tone="gold" />}
        </div>
      </div>
      <span className="rounded border border-border/60 bg-bg2/55 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-silver-dk">
        Review
      </span>
    </button>
  );
}

function ProjectedPlacementRow({ item }: { item: ProjectedPlacementViewItem }) {
  return (
    <div className="rounded border border-cyan/30 bg-cyan/8 px-2 py-1 text-[10px]">
      <span className="font-bold">#{item.placement.build_order || item.index + 1}</span>{' '}
      <span>{item.template?.name ?? item.placement.facility_template_id}</span>{' '}
      <span className="text-cyan/80">(projected)</span>
    </div>
  );
}

function BodyStructurePickerDrawer({
  body,
  templates,
  onClose,
  onPickTemplate,
}: {
  body: SystemBody | null;
  templates: FacilityTemplate[];
  onClose: () => void;
  onPickTemplate: (templateId: string) => void;
}) {
  const [query, setQuery] = useState('');

  if (!body || body.id == null) return null;

  const bodyName = bodyDisplayName(body);
  const filtered = templates
    .filter((template) => templateCanFitBody(template, body))
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
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">Add structure on selected body</div>
          <h4 className="mt-0.5 text-sm font-bold text-silver">{bodyName}</h4>
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
          No matching structures for this body and filter.
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

function templateCanFitBody(template: FacilityTemplate, body: SystemBody) {
  const location = templateLocationKind(template);
  if (location === 'surface') return Boolean(body.is_landable);
  return true;
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
