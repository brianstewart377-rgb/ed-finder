import { PanelRight } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import type { SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { ColonyProject } from './colonyProjectStore';
import { ProjectControlsCard } from './ProjectControlsCard';
import {
  getPlanHealthSummary,
  humanizeArchetype,
} from './workspaceUtils';

export function WorkspaceSummaryRail({
  system,
  snapshot,
  selection,
  selectedContext,
  projects,
  activeProject,
  pendingProjectId,
  projectName,
  projectNotes,
  unsavedChanges,
  confirmArchive,
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
  selection: TopologySelection;
  selectedContext: TopologySelectionContext;
  projects: ColonyProject[];
  activeProject: ColonyProject | null;
  pendingProjectId: string;
  projectName: string;
  projectNotes: string;
  unsavedChanges: boolean;
  confirmArchive: boolean;
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
  const [collapsed, setCollapsed] = useState(true);

  return (
    <aside
      aria-label="Workspace summary"
      data-testid="planner-summary-panel"
      className="panel space-y-3 p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
          <PanelRight size={13} />
          Planner summary
        </div>
        <button
          type="button"
          data-testid="summary-rail-collapse-toggle"
          onClick={() => setCollapsed((value) => !value)}
          className="rounded border border-border/60 bg-bg3/45 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          {collapsed ? 'Expand' : 'Compact'}
        </button>
      </div>

      {collapsed ? (
        <CompactSummary
          saveStatus={health.saveStatus}
          selectedContext={selectedContext}
          projectionLabel={snapshot.projection?.label ?? null}
        />
      ) : (
        <>
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

          <PreviewSuggestedCard
            selection={selection}
            snapshot={snapshot}
            previewStatus={health.previewStatus}
          />
        </>
      )}
    </aside>
  );
}

function CompactSummary({
  saveStatus,
  selectedContext,
  projectionLabel,
}: {
  saveStatus: string;
  selectedContext: TopologySelectionContext;
  projectionLabel: string | null;
}) {
  return (
    <section className="space-y-2" data-testid="summary-rail-compact-view">
      <div className="rounded border border-cyan/25 bg-cyan/5 p-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Project</div>
        <p className="mt-1 font-mono text-[10px] text-silver-dk">{saveStatus}</p>
      </div>
      <div className="rounded border border-cyan/25 bg-cyan/5 p-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Current body</div>
        <p className="mt-1 font-mono text-[10px] text-silver-dk">{selectedContext.label}</p>
      </div>
      <div className="rounded border border-cyan/25 bg-cyan/5 p-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Projection</div>
        <p className="mt-1 font-mono text-[10px] text-silver-dk">{projectionLabel ?? 'No candidate selected'}</p>
      </div>
    </section>
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
        Current Focus
      </h3>
      <dl className="mt-2 space-y-2 font-mono text-[10px]">
        <SummaryRow label="Viewing" value={selectedContext.label} tone="cyan" />
        <SummaryRow label="Type" value={selectedContext.kind} />
        <SummaryRow label="Placements" value={String(selectedContext.placementCount)} />
        <SummaryRow label="Warnings" value={String(selectedContext.warningCount)} tone={selectedContext.warningCount > 0 ? 'gold' : 'green'} />
      </dl>
      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">{selectedContext.detail}</p>
    </section>
  );
}

function PreviewSuggestedCard({
  selection,
  snapshot,
  previewStatus,
}: {
  selection: TopologySelection;
  snapshot: TopologyPlanSnapshot;
  previewStatus: string;
}) {
  const projectedBodyIds = Array.from(new Set(
    (snapshot.projection?.placements ?? [])
      .map((placement) => placement.local_body_id != null ? String(placement.local_body_id) : '')
      .filter(Boolean),
  ));
  return (
    <section className="rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="preview-suggested-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        Preview / Suggested
      </h3>
      <dl className="mt-2 space-y-2 font-mono text-[10px]">
        <SummaryRow label="Preview" value={previewStatus} tone="cyan" />
        <SummaryRow
          label="Suggested"
          value={snapshot.projection ? 'Candidate selected' : 'No candidate selected'}
          tone={snapshot.projection ? 'orange' : undefined}
        />
        <SummaryRow
          label="Projected bodies"
          value={String(projectedBodyIds.length)}
          tone={projectedBodyIds.length > 0 ? 'cyan' : undefined}
        />
      </dl>
      {snapshot.projection && (
        <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
          {snapshot.projection.label}
        </p>
      )}
      {selection.type === 'body' && snapshot.projection && projectedBodyIds.includes(selection.bodyId) && (
        <p className="mt-1 rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] text-cyan">
          Selected body is used by the projected suggested build.
        </p>
      )}
    </section>
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
