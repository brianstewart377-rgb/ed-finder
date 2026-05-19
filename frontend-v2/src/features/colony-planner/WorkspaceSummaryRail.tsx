import { PanelRight } from 'lucide-react';
import type { ReactNode } from 'react';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody, SystemDetail } from '@/types/api';
import type { BodyGroup, GroupedPlacement } from '@/features/system-detail/simulation-preview/buildPlanLayoutUtils';
import {
  buildColonyRoleSummaryForGroup,
  primaryRoleHint,
  type ColonyRoleSummary,
} from '@/features/system-detail/simulation-preview/colonyRoleHintUtils';
import type { TopologyPlanSnapshot, TopologySelection, TopologySelectionContext } from './ColonyTopologyRail';
import type { ColonyProject } from './colonyProjectStore';
import {
  declaredRoleConflicts,
  roleCompactLabel,
  rolesForBody,
  type DeclaredColonyRole,
} from './colonyRoles';
import { ProjectControlsCard } from './ProjectControlsCard';
import {
  getPlanHealthSummary,
  humanizeArchetype,
  type ReviewDrawer,
} from './workspaceUtils';

export function WorkspaceSummaryRail({
  system,
  snapshot,
  selection,
  declaredRoles,
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
  selection: TopologySelection;
  declaredRoles: DeclaredColonyRole[];
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
  const selectedRoleContext = buildSelectedRoleContext(selection, system, snapshot, declaredRoles);

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

      {selectedRoleContext && <SelectedRoleCard context={selectedRoleContext} />}

      <WorkspaceModeCard
        reviewDrawer={reviewDrawer}
        onReviewDrawerChange={onReviewDrawerChange}
      />
    </aside>
  );
}

interface SelectedRoleContext {
  summary: ColonyRoleSummary;
  declaredRoles: DeclaredColonyRole[];
}

function SelectedRoleCard({ context }: { context: SelectedRoleContext }) {
  const { summary, declaredRoles } = context;
  const primary = primaryRoleHint(summary.hints);
  const declaredConflicts = declaredRoleConflicts(declaredRoles);
  return (
    <section className="rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="selected-role-summary-card">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        Body Hint
      </h3>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        {primary && (
          <span
            className={[
              'rounded border px-1.5 py-0.5 uppercase tracking-[0.12em]',
              primary.tone === 'good'
                ? 'border-green/35 bg-green/10 text-green'
                : primary.tone === 'warn'
                  ? 'border-gold/35 bg-gold/10 text-gold'
                  : 'border-border/60 bg-bg3/45 text-silver',
            ].join(' ')}
          >
            {primary.compactLabel}
          </span>
        )}
        {declaredRoles.slice(0, 1).map((role) => (
          <span
            key={role.id}
            className="rounded border border-green/35 bg-green/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-green"
          >
            Declared: {roleCompactLabel(role.role_id)}
          </span>
        ))}
      </div>
      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        {summary.reasoning}
      </p>
      {declaredConflicts.length > 0 && (
        <div className="mt-2 space-y-1 font-mono text-[10px] text-gold">
          {declaredConflicts.map((conflict) => <p key={conflict}>{conflict}</p>)}
        </div>
      )}
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
        <ModeButton label="Evidence" active={reviewDrawer === 'evidence'} onClick={() => onReviewDrawerChange(reviewDrawer === 'evidence' ? null : 'evidence')} />
        <ModeButton label="Validation" active={reviewDrawer === 'validation'} onClick={() => onReviewDrawerChange(reviewDrawer === 'validation' ? null : 'validation')} />
      </div>
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

function buildSelectedRoleContext(
  selection: TopologySelection,
  system: SystemDetail,
  snapshot: TopologyPlanSnapshot,
  declaredRoles: DeclaredColonyRole[],
): SelectedRoleContext | null {
  const bodies = system.bodies ?? [];
  const groups = buildBodyGroups(snapshot.placements, snapshot.templates, bodies);
  if (selection.type === 'body') {
    const existing = groups.find((group) => group.key === selection.bodyId);
    const body = bodies.find((candidate) => candidate.id != null && String(candidate.id) === selection.bodyId) ?? null;
    if (!existing && !body) return null;
    return {
      summary: buildColonyRoleSummaryForGroup(existing ?? { key: selection.bodyId, body, placements: [] }, groups),
      declaredRoles: rolesForBody(declaredRoles, selection.bodyId),
    };
  }
  if (selection.type === 'placement') {
    const group = groups.find((candidate) => candidate.placements.some((item) => item.index === selection.placementIndex));
    return group ? {
      summary: buildColonyRoleSummaryForGroup(group, groups),
      declaredRoles: rolesForBody(declaredRoles, group.key),
    } : null;
  }
  return null;
}

function buildBodyGroups(
  placements: SimulateBuildPlacement[],
  templates: FacilityTemplate[],
  bodies: SystemBody[],
): BodyGroup[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const bodiesById = new Map(
    bodies
      .filter((body) => body.id != null)
      .map((body) => [String(body.id), body]),
  );
  const groupsByKey = new Map<string, BodyGroup>();
  const ensureGroup = (key: string, body: SystemBody | null): BodyGroup => {
    const existing = groupsByKey.get(key);
    if (existing) return existing;
    const next: BodyGroup = { key, body, placements: [] };
    groupsByKey.set(key, next);
    return next;
  };

  placements.forEach((placement, index) => {
    const bodyId = placement.local_body_id != null ? String(placement.local_body_id) : '';
    const body = bodyId ? bodiesById.get(bodyId) ?? null : null;
    const key = body ? bodyId : 'unassigned';
    const item: GroupedPlacement = {
      placement,
      index,
      template: templatesById.get(placement.facility_template_id),
      bodyId: bodyId || undefined,
      hasUnknownBody: Boolean(bodyId && !body),
    };
    ensureGroup(key, body).placements.push(item);
  });

  return Array.from(groupsByKey.values());
}
