import { PanelRight } from 'lucide-react';
import type { ReactNode } from 'react';
import type { SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelectionContext } from './ColonyTopologyRail';
import type { ColonyProject } from './colonyProjectStore';
import { ProjectControlsCard } from './ProjectControlsCard';
import {
  deriveArchitectStatus,
  formatProjectTimestamp,
  getPlanHealthSummary,
  humanizeArchetype,
  type ReviewDrawer,
} from './workspaceUtils';

export function WorkspaceSummaryRail({
  system,
  snapshot,
  selectedContext,
  projects,
  activeProject,
  pendingProjectId,
  projectName,
  projectNotes,
  unsavedChanges,
  confirmArchive,
  reviewDrawer,
  onReviewDrawerChange,
  onPendingProjectChange,
  onLoadProject,
  onProjectNameChange,
  onProjectNotesChange,
  onSaveProject,
  onRenameProject,
  onDuplicateProject,
  onArchiveProject,
  onConfirmArchiveChange,
}: {
  system: SystemDetail;
  snapshot: TopologyPlanSnapshot;
  selectedContext: TopologySelectionContext;
  projects: ColonyProject[];
  activeProject: ColonyProject | null;
  pendingProjectId: string;
  projectName: string;
  projectNotes: string;
  unsavedChanges: boolean;
  confirmArchive: boolean;
  reviewDrawer: ReviewDrawer;
  onReviewDrawerChange: (drawer: ReviewDrawer) => void;
  onPendingProjectChange: (projectId: string) => void;
  onLoadProject: () => void;
  onProjectNameChange: (name: string) => void;
  onProjectNotesChange: (notes: string) => void;
  onSaveProject: () => void;
  onRenameProject: () => void;
  onDuplicateProject: () => void;
  onArchiveProject: () => void;
  onConfirmArchiveChange: (confirming: boolean) => void;
}) {
  const health = getPlanHealthSummary({ snapshot, system, selectedContext, unsavedChanges });

  return (
    <aside
      aria-label="Workspace summary"
      data-testid="planner-summary-panel"
      className="panel space-y-3 p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
        <PanelRight size={13} />
        Planner summary
      </div>

      <ProjectControlsCard
        projects={projects}
        activeProject={activeProject}
        pendingProjectId={pendingProjectId}
        projectName={projectName}
        projectNotes={projectNotes}
        unsavedChanges={unsavedChanges}
        confirmArchive={confirmArchive}
        onPendingProjectChange={onPendingProjectChange}
        onLoadProject={onLoadProject}
        onProjectNameChange={onProjectNameChange}
        onProjectNotesChange={onProjectNotesChange}
        onSaveProject={onSaveProject}
        onRenameProject={onRenameProject}
        onDuplicateProject={onDuplicateProject}
        onArchiveProject={onArchiveProject}
        onConfirmArchiveChange={onConfirmArchiveChange}
      />

      <PlanHealthCard
        targetArchetype={snapshot.targetArchetype}
        placementCount={health.placementCount}
        unassignedCount={health.unassignedCount}
        warningCount={health.warningCount}
        previewStatus={health.previewStatus}
        saveStatus={health.saveStatus}
      />

      <SelectionSummaryCard selectedContext={selectedContext} />

      <ArchitectCard status={deriveArchitectStatus(snapshot)} />

      <WorkspaceModeCard
        reviewDrawer={reviewDrawer}
        onReviewDrawerChange={onReviewDrawerChange}
      />

      <section className="rounded border border-border/55 bg-bg3/30 p-2" data-testid="workspace-project-status">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">
          Current save state
        </h3>
        <dl className="mt-2 space-y-2 font-mono text-[10px]">
          <SummaryRow label="Project" value={activeProject?.project_name ?? 'Unsaved workspace'} tone={unsavedChanges ? 'gold' : 'green'} />
          <SummaryRow label="Last saved" value={formatProjectTimestamp(activeProject?.updated_at)} />
        </dl>
      </section>
    </aside>
  );
}

function PlanHealthCard({
  targetArchetype,
  placementCount,
  unassignedCount,
  warningCount,
  previewStatus,
  saveStatus,
}: {
  targetArchetype: string;
  placementCount: number;
  unassignedCount: number;
  warningCount: number;
  previewStatus: string;
  saveStatus: string;
}) {
  return (
    <section className="rounded border border-orange/25 bg-orange/5 p-2" data-testid="plan-health-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
        Plan Health
      </h3>
      <dl className="mt-2 grid grid-cols-2 gap-2 font-mono text-[10px]">
        <SummaryRow label="Target" value={humanizeArchetype(targetArchetype)} tone="orange" />
        <SummaryRow label="Placements" value={String(placementCount)} tone="orange" />
        <SummaryRow label="Unassigned" value={String(unassignedCount)} tone={unassignedCount > 0 ? 'gold' : 'green'} />
        <SummaryRow label="Warnings" value={String(warningCount)} tone={warningCount > 0 ? 'gold' : 'green'} />
        <SummaryRow label="Preview" value={previewStatus} tone="cyan" />
        <SummaryRow label="Save" value={saveStatus} tone={saveStatus === 'Saved' ? 'green' : 'gold'} />
      </dl>
    </section>
  );
}

function SelectionSummaryCard({ selectedContext }: { selectedContext: TopologySelectionContext }) {
  return (
    <section className="rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="selection-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        Selection
      </h3>
      <div className="mt-1 font-mono text-[10px] text-silver-dk">
        Read-only topology selection
      </div>
      <dl className="mt-2 space-y-2 font-mono text-[10px]">
        <SummaryRow label="Viewing" value={selectedContext.label} tone="cyan" />
        <SummaryRow label="Type" value={selectedContext.kind} />
        <SummaryRow label="Placements" value={String(selectedContext.placementCount)} />
        <SummaryRow label="Warnings" value={String(selectedContext.warningCount)} tone={selectedContext.warningCount > 0 ? 'gold' : 'green'} />
      </dl>
      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        {selectedContext.detail}
      </p>
    </section>
  );
}

function ArchitectCard({ status }: { status: string }) {
  return (
    <section className="rounded border border-gold/30 bg-gold/5 p-2" data-testid="architect-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
        Architect
      </h3>
      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        {status}
      </p>
      <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
        Primary-port guidance must come from in-game Architect Mode evidence.
      </p>
    </section>
  );
}

function WorkspaceModeCard({
  reviewDrawer,
  onReviewDrawerChange,
}: {
  reviewDrawer: ReviewDrawer;
  onReviewDrawerChange: (drawer: ReviewDrawer) => void;
}) {
  return (
    <section className="rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="workspace-modes-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        Workspace Modes
      </h3>
      <div className="mt-2 grid gap-2 font-mono text-[10px]">
        <ModeButton label="Evidence drawer" active={reviewDrawer === 'evidence'} onClick={() => onReviewDrawerChange(reviewDrawer === 'evidence' ? null : 'evidence')} />
        <ModeButton label="Validation drawer" active={reviewDrawer === 'validation'} onClick={() => onReviewDrawerChange(reviewDrawer === 'validation' ? null : 'validation')} />
      </div>
      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        Drawers open in the central planner and do not run Preview or Validation by themselves.
      </p>
    </section>
  );
}

function ModeButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-expanded={active}
      onClick={onClick}
      className={[
        'rounded border px-2 py-1.5 text-left font-bold',
        active ? 'border-orange/60 bg-orange/15 text-orange' : 'border-border bg-bg3 text-silver hover:border-cyan/50',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function SummaryRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: 'orange' | 'cyan' | 'gold' | 'green';
}) {
  const toneClass = tone === 'orange'
    ? 'text-orange'
    : tone === 'gold'
      ? 'text-gold'
      : tone === 'cyan'
        ? 'text-cyan'
        : tone === 'green'
          ? 'text-green'
          : 'text-silver';
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1.5">
      <dt className="uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className={['mt-0.5 break-words text-[11px]', toneClass].join(' ')}>{value}</dd>
    </div>
  );
}
