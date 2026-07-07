import { PanelRight } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import type { SystemDetail } from '@/types/api';
import { bodyIdKey } from '@/features/system-detail/simulation-preview/bodyIdUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { ColonyProject } from './colonyProjectStore';
import { ProjectControlsCard } from './ProjectControlsCard';
import {
  getPlanHealthSummary,
  humanizeArchetype,
} from './workspaceUtils';
import { PlanningEconomyStrip } from './PlanningEconomyStrip';
import type { PlanningEconomyLedger } from './planningEconomy';
import type { PrerequisiteIssue } from './structurePlanningRules';

export function WorkspaceSummaryRail({
  system,
  snapshot,
  economyLedger,
  prerequisiteIssues = [],
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
  economyLedger: PlanningEconomyLedger;
  prerequisiteIssues?: PrerequisiteIssue[];
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
      className="panel space-y-3 p-3"
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
          className="premium-toolbar rounded-xl px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-silver-dk hover:border-orange/45 hover:text-orange"
        >
          {collapsed ? 'Expand' : 'Compact'}
        </button>
      </div>

      {collapsed ? (
        <CompactSummary
          saveStatus={health.saveStatus}
          selectedContext={selectedContext}
          projectionLabel={snapshot.projection?.label ?? null}
          placementCount={health.placementCount}
          projectedCount={snapshot.projection?.placements.length ?? 0}
          warningCount={health.warningCount}
          prerequisiteIssueCount={prerequisiteIssues.length}
          economyLedger={economyLedger}
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
            economyLedger={economyLedger}
            prerequisiteIssues={prerequisiteIssues}
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
  placementCount,
  projectedCount,
  warningCount,
  prerequisiteIssueCount,
  economyLedger,
}: {
  saveStatus: string;
  selectedContext: TopologySelectionContext;
  projectionLabel: string | null;
  placementCount: number;
  projectedCount: number;
  warningCount: number;
  prerequisiteIssueCount: number;
  economyLedger: PlanningEconomyLedger;
}) {
  return (
    <section className="space-y-2" data-testid="summary-rail-compact-view">
      <div className="grid grid-cols-2 gap-1.5">
        <CompactMetric label="Save" value={saveStatus} tone={saveStatus === 'Saved' ? 'green' : 'gold'} />
        <CompactMetric label="Builds" value={`${placementCount}${projectedCount > 0 ? ` +${projectedCount}` : ''}`} tone={projectedCount > 0 ? 'cyan' : 'orange'} />
        <CompactMetric label="Warnings" value={prerequisiteIssueCount > 0 ? `${warningCount} / ${prerequisiteIssueCount} prereq` : String(warningCount)} tone={warningCount > 0 || prerequisiteIssueCount > 0 ? 'gold' : 'green'} />
        <CompactMetric label="Focus" value={selectedContext.kind} tone="cyan" />
      </div>
      <div className="premium-toolbar rounded-xl px-2 py-1 font-mono text-[10px]">
        <div className="flex items-center justify-between gap-2 uppercase tracking-[0.12em] text-silver-dk">
          <span>Current focus</span>
          <span className={projectionLabel ? 'text-cyan' : 'text-silver-dk'}>{projectionLabel ? 'Projection on' : 'No projection'}</span>
        </div>
        <div className="mt-0.5 truncate text-silver" title={selectedContext.label}>{selectedContext.label}</div>
        {projectionLabel && <div className="mt-0.5 truncate text-cyan" title={projectionLabel}>{projectionLabel}</div>}
      </div>
      <PlanningEconomyStrip ledger={economyLedger} compact testId="summary-economy-ledger" />
    </section>
  );
}

function CompactMetric({ label, value, tone }: { label: string; value: ReactNode; tone: 'orange' | 'cyan' | 'gold' | 'green' }) {
  const toneClass = tone === 'orange'
    ? 'text-orange'
    : tone === 'gold'
      ? 'text-gold'
      : tone === 'green'
        ? 'text-green'
        : 'text-cyan';
  return (
    <div className="premium-toolbar rounded-xl px-2 py-1 font-mono">
      <div className="truncate text-[9px] uppercase tracking-[0.12em] text-silver-dk">{label}</div>
      <div className={["mt-0.5 truncate text-[12px] font-semibold", toneClass].join(' ')}>{value}</div>
    </div>
  );
}

function PlanHealthCard({
  targetArchetype,
  placementCount,
  unassignedCount,
  warningCount,
  previewStatus,
  saveStatus,
  economyLedger,
  prerequisiteIssues,
}: {
  targetArchetype: string;
  placementCount: number;
  unassignedCount: number;
  warningCount: number;
  previewStatus: string;
  saveStatus: string;
  economyLedger: PlanningEconomyLedger;
  prerequisiteIssues: PrerequisiteIssue[];
}) {
  return (
    <section className="premium-subpanel border-orange/25 bg-orange/5 p-2" data-testid="plan-health-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
        Plan Health
      </h3>
      <dl className="mt-2 grid grid-cols-2 gap-2 font-mono text-[10px]">
        <SummaryRow label="Target" value={humanizeArchetype(targetArchetype)} tone="orange" />
        <SummaryRow label="Placements" value={String(placementCount)} tone="orange" />
        <SummaryRow label="Unassigned" value={String(unassignedCount)} tone={unassignedCount > 0 ? 'gold' : 'green'} />
        <SummaryRow label="Warnings" value={String(warningCount)} tone={warningCount > 0 ? 'gold' : 'green'} />
        <SummaryRow label="Prerequisites" value={String(prerequisiteIssues.length)} tone={prerequisiteIssues.length > 0 ? 'gold' : 'green'} />
        <SummaryRow label="Preview" value={previewStatus} tone="cyan" />
        <SummaryRow label="Save" value={saveStatus} tone={saveStatus === 'Saved' ? 'green' : 'gold'} />
      </dl>
      {prerequisiteIssues.length > 0 && (
        <div data-testid="plan-health-prerequisite-warnings" className="mt-2 rounded border border-gold/35 bg-gold/10 px-2 py-1 font-mono text-[10px] text-gold shadow-[0_12px_22px_-18px_rgba(234,179,8,0.85)]">
          Missing prerequisite: {prerequisiteIssues.slice(0, 3).map((issue) => `${issue.templateName}: ${issue.missing.join('; ')}`).join(' / ')}
        </div>
      )}
      <div className="mt-2">
        <PlanningEconomyStrip ledger={economyLedger} compact testId="plan-health-economy-ledger" />
      </div>
    </section>
  );
}

function SelectionSummaryCard({ selectedContext }: { selectedContext: TopologySelectionContext }) {
  return (
    <section className="premium-subpanel border-cyan/25 bg-cyan/5 p-2" data-testid="selection-card">
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
      .map((placement) => bodyIdKey(placement.local_body_id))
      .filter(Boolean),
  ));
  return (
    <section className="premium-subpanel border-cyan/25 bg-cyan/5 p-2" data-testid="preview-suggested-card">
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
      {selection.type === 'body' && snapshot.projection && projectedBodyIds.includes(bodyIdKey(selection.bodyId)) && (
        <p className="mt-1 rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] text-cyan shadow-[0_12px_22px_-18px_rgba(34,211,238,0.9)]">
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
    <div className="premium-toolbar rounded-xl px-2 py-1.5">
      <dt className="uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className={['mt-0.5 break-words text-[11px]', toneClass].join(' ')}>{value}</dd>
    </div>
  );
}
