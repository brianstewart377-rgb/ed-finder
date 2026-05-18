import { useCallback, useMemo, useState } from 'react';
import type { SystemDetail } from '@/types/api';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
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
          hasPlacements={planSnapshot.placements.length > 0}
          planningFocusLabel={planningFocusLabel}
          unsavedChanges={projectState.unsavedChanges}
        />
        <SimulationPreviewPanel
          system={system}
          selectedPlan={null}
          onPlanSnapshotChange={handlePlanSnapshotChange}
          topologySelection={selection}
          initialRequest={projectState.projectRequest}
          workspaceDrawer={reviewDrawer}
          onWorkspaceDrawerChange={setReviewDrawer}
          showWorkspaceDrawerControls={false}
        />
      </main>
      <WorkspaceSummaryRail
        system={system}
        snapshot={planSnapshot}
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

function WorkspaceIntro({
  hasPlacements,
  planningFocusLabel,
  unsavedChanges,
}: {
  hasPlacements: boolean;
  planningFocusLabel: string | null;
  unsavedChanges: boolean;
}) {
  return (
    <div className="mb-3 space-y-3 border-b border-border/70 pb-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-orange">
            Planning Workspace
          </h2>
          <p className="mt-1 max-w-2xl text-[11px] font-mono leading-snug text-silver-dk">
            Use the Build Plan for edits. Topology selection sets planning context only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded border border-cyan/30 bg-cyan/5 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            Contained planner
          </span>
          <WhatNextStrip hasPlacements={hasPlacements} unsavedChanges={unsavedChanges} />
        </div>
      </div>

      {planningFocusLabel && (
        <section
          data-testid="planning-focus-banner"
          className="rounded border border-cyan/30 bg-cyan/5 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk"
        >
          <span className="font-bold text-cyan">Planning focus: {planningFocusLabel}</span>
          <span className="ml-2">Edits still happen explicitly in Build Plan.</span>
        </section>
      )}

      {!hasPlacements && (
        <section className="rounded border border-orange/25 bg-orange/5 p-3" data-testid="first-run-empty-state">
          <h3 className="font-mono text-[11px] uppercase tracking-[0.16em] text-orange">
            Start a colony plan
          </h3>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <StartOption title="Start with Suggested Build" body="Generate candidates, then load one deliberately." />
            <StartOption title="Start manually" body="Add placements directly in Build Plan." />
            <StartOption title="Review body topology" body="Select a body to focus placement review." />
            <StartOption title="Save project" body="Name the local project once the plan has shape." />
          </div>
        </section>
      )}
    </div>
  );
}

function WhatNextStrip({ hasPlacements, unsavedChanges }: { hasPlacements: boolean; unsavedChanges: boolean }) {
  const items = [
    hasPlacements ? 'Review placements' : 'Select a body',
    hasPlacements ? 'Run Preview' : 'Generate Suggested Builds',
    unsavedChanges ? 'Save project' : 'Keep planning',
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

function StartOption({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-border/55 bg-bg2/45 p-2">
      <div className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-silver">
        {title}
      </div>
      <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">{body}</p>
    </div>
  );
}
