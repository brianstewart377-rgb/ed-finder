import { useCallback, useMemo, useState } from 'react';
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
import { getPlanningFocusLabel, type ReviewDrawer } from './workspaceUtils';

export function WorkspaceGrid({ system }: { system: SystemDetail }) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  const [reviewDrawer, setReviewDrawer] = useState<ReviewDrawer>(null);
  const [planSnapshot, setPlanSnapshot] = useState<TopologyPlanSnapshot>({
    placements: [],
    templates: [],
    targetArchetype: 'refinery_industrial',
  });
  const projectState = useWorkspaceProjectState(system, planSnapshot);

  const handlePlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    setPlanSnapshot(snapshot);
  }, []);

  const selectedContext = useMemo(
    () => describeTopologySelection(selection, system, planSnapshot),
    [planSnapshot, selection, system],
  );
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

  return (
    <section
      aria-label="Colony Planner application shell"
      data-testid="planner-workspace-shell-v2"
      className="grid gap-4 xl:grid-cols-[18rem_minmax(0,1fr)_20rem] xl:items-start"
    >
      <ColonyTopologyRail
        system={system}
        snapshot={planSnapshot}
        declaredRoles={projectState.declaredRoles}
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
        />
        <SimulationPreviewPanel
          system={system}
          selectedPlan={null}
          onPlanSnapshotChange={handlePlanSnapshotChange}
          topologySelection={selection}
          initialRequest={projectState.projectRequest}
          declaredRoles={projectState.declaredRoles}
          workspaceDrawer={reviewDrawer}
          onWorkspaceDrawerChange={setReviewDrawer}
        />
      </main>
      <WorkspaceSummaryRail
        system={system}
        snapshot={planSnapshot}
        selection={selection}
        declaredRoles={projectState.declaredRoles}
        selectedContext={selectedContext}
        projects={projectState.projects}
        activeProject={projectState.activeProject}
        pendingProjectId={projectState.pendingProjectId}
        projectName={projectState.projectName}
        projectNotes={projectState.projectNotes}
        unsavedChanges={projectState.unsavedChanges}
        confirmArchive={projectState.confirmArchive}
        reviewDrawer={reviewDrawer}
        onReviewDrawerChange={setReviewDrawer}
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
}: {
  body: SystemBody | null;
  snapshot: TopologyPlanSnapshot;
  selection: TopologySelection;
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
          <BodyStartAction label="Select a body" detail="Use the topology rail." />
          <BodyStartAction label="Generate a strategy" detail="Open Suggested Builds when ready." />
          <BodyStartAction label="Start manually" detail="Add structures in Build Plan." />
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
  const placements = snapshot.placements
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
  const addButton = () => document.querySelector<HTMLButtonElement>('[data-testid="add-structure-selected-body"]');
  const listButton = () => document.querySelector<HTMLButtonElement>('[data-testid="build-plan-list-view"]');
  const bodyButton = () => document.querySelector<HTMLButtonElement>('[data-testid="build-plan-body-view"]');

  const focusAddStructure = () => {
    const target = addButton();
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target?.focus({ preventScroll: true });
  };
  const reviewBodyStructures = () => {
    const target = placements.length > 0 ? bodyButton() : listButton();
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target?.click();
    target?.focus({ preventScroll: true });
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
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={focusAddStructure}
            className="rounded-chunk-sm border border-orange/55 bg-orange/15 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-orange hover:bg-orange/25"
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

      <div className="mt-3 grid gap-2">
        {placements.length === 0 ? (
          <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2 text-silver-dk">
            No structures planned on this body yet.
          </div>
        ) : placements.map((item) => (
          <BodyPlacementRow key={`${item.index}-${item.placement.facility_template_id}`} item={item} body={body} />
        ))}
      </div>
    </section>
  );
}

function BodyPlacementRow({
  item,
  body,
}: {
  item: {
    placement: SimulateBuildPlacement;
    index: number;
    template: FacilityTemplate | undefined;
    bodyId: string;
    hasUnknownBody: boolean;
  };
  body: SystemBody;
}) {
  const location = item.template ? templateLocationKind(item.template) : 'unknown';
  const warnings = getPlacementWarnings(item, body);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border/55 bg-bg3/40 px-3 py-2">
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
    </div>
  );
}

function BodyStartAction({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-silver">{label}</div>
      <p className="mt-1 text-[10px] text-silver-dk">{detail}</p>
    </div>
  );
}

function BodyFact({ label, tone = 'silver' }: { label: string; tone?: 'silver' | 'orange' | 'gold' }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]',
        tone === 'orange'
          ? 'border-orange/35 bg-orange/10 text-orange'
          : tone === 'gold'
            ? 'border-gold/35 bg-gold/10 text-gold'
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
