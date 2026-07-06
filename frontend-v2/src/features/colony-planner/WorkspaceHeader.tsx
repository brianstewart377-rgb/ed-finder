import { useState } from 'react';
import { ArrowLeft, ExternalLink, MoreHorizontal, Trash2 } from 'lucide-react';
import { formatCoords, formatPopulationForSystem, systemStatusLabel } from '@/lib/format';
import { formatArchetypeLabel } from '@/lib/archetypes';
import type { SystemDetail } from '@/types/api';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';
import type { ColonyProject } from './colonyProjectStore';
import {
  objectiveSummaryLabel,
  plannerNextActionCopy,
  startApproachLabel,
} from './plannerDraftContext';

function projectStatusLabel(status?: ColonyProject['status'] | null) {
  if (status === 'ready_to_build') return 'Ready to build';
  if (status === 'building') return 'Building';
  if (status === 'established') return 'Established';
  return 'Draft';
}

function projectStatusTone(status?: ColonyProject['status'] | null) {
  if (status === 'ready_to_build') return 'available' as const;
  if (status === 'building') return 'caution' as const;
  if (status === 'established') return 'canonical' as const;
  return 'available' as const;
}

function plannedStructureDeletionCopy(count: number, itemKind: 'draft' | 'plan') {
  if (count <= 0) return `This ${itemKind} has no planned structures yet.`;
  const structureLabel = count === 1 ? 'planned structure' : 'planned structures';
  return `This will remove ${count} ${structureLabel} from this ${itemKind}.`;
}

export function WorkspaceHeaderSkeleton({
  id64,
  onBackToFinder,
}: {
  id64: number;
  onBackToFinder: () => void;
}) {
  return (
    <header className="panel overflow-hidden p-4 sm:p-5">
      <WorkspaceContextHeader
        journeyLabel="Plan"
        title="Colony Planner"
        supportingText="Build and review a canonical plan while the selected-system evidence lane stays read-only."
        selectedSystemName="Loading system..."
        selectedSystemMeta={<span className="tabular-nums">ID64 {id64}</span>}
        status={<SemanticStatusBadge label="Loading" tone="loading" />}
        actions={(
          <button
            type="button"
            onClick={onBackToFinder}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
          >
            <ArrowLeft size={14} />
            Back to Finder
          </button>
        )}
      />
    </header>
  );
}

export function WorkspaceHeader({
  system,
  onBackToFinder,
  onOpenSystemDetail,
  onOpenMyWork,
  onPlanDeleted,
  activeProject,
  unsavedChanges,
  plannedStructureCount = 0,
  onDeleteActiveProject,
}: {
  system: SystemDetail;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
  onOpenMyWork?: () => void;
  onPlanDeleted?: (projectName: string) => void;
  activeProject?: ColonyProject | null;
  unsavedChanges?: boolean;
  plannedStructureCount?: number;
  onDeleteActiveProject?: () => boolean;
}) {
  const [actionsOpen, setActionsOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const population = formatPopulationForSystem(system);
  const status = systemStatusLabel(system);
  const coords = formatCoords(system, system.id64);
  const deleteItemKind = activeProject?.status === 'draft' ? 'draft' : 'plan';
  const deleteActionLabel = activeProject?.status === 'draft' ? 'Delete draft' : 'Delete plan';
  const keepActionLabel = activeProject?.status === 'draft' ? 'Keep draft' : 'Keep plan';
  const statusTone = status === 'Colonised'
    ? 'canonical'
    : status === 'Colonising'
      ? 'caution'
      : 'available';

  return (
    <header className="panel overflow-hidden p-4 sm:p-5">
      <WorkspaceContextHeader
        testId="workspace-context-header"
        journeyLabel="Plan"
        title="Colony Planner"
        supportingText="Build the selected system with canonical planner data, then review read-only evidence separately before committing to assumptions."
        selectedSystemName={system.name || 'Unknown system'}
        selectedSystemMeta={<span className="tabular-nums">ID64 {system.id64}</span>}
        status={<SemanticStatusBadge label={status} tone={statusTone} />}
        facts={[
          { label: 'Coords', value: coords, tone: 'cyan' },
          { label: 'Archetype', value: system.primary_archetype ? formatArchetypeLabel(system.primary_archetype) : system.primary_economy ?? 'Unknown', tone: 'orange' },
          { label: 'Population', value: population },
        ]}
        actions={(
          <>
          <button
            type="button"
            onClick={onBackToFinder}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
          >
            <ArrowLeft size={14} />
            Back to Finder
          </button>
          <button
            type="button"
            onClick={() => onOpenSystemDetail(system.id64)}
            data-testid="back-to-system-detail"
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80"
          >
            <ExternalLink size={14} />
            Back to system detail
          </button>
          </>
        )}
      />
      {activeProject ? (
        <div
          data-testid="planner-arrival-context"
          className="mt-4 grid gap-3 rounded-chunk-lg border border-orange/30 bg-bg2/80 p-3 shadow-[0_16px_40px_-30px_rgba(0,0,0,0.8)] lg:grid-cols-[minmax(0,1fr)_auto]"
        >
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
                Active plan
              </span>
              <SemanticStatusBadge label={projectStatusLabel(activeProject.status)} tone={projectStatusTone(activeProject.status)} />
              <span
                data-testid="planner-local-save-state"
                className={[
                  'rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em]',
                  unsavedChanges
                    ? 'border-gold/40 bg-gold/10 text-gold'
                    : 'border-green/35 bg-green/10 text-green',
                ].join(' ')}
              >
                {unsavedChanges ? 'Unsaved local changes' : 'Saved locally'}
              </span>
              <span
                data-testid="planner-objective-context"
                className="rounded border border-border bg-bg3/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver"
              >
                {objectiveSummaryLabel(activeProject.objective)}
              </span>
            </div>
            <div>
              <h2
                data-testid="planner-project-name"
                className="truncate font-display text-lg tracking-[0.08em] text-orange-lt"
              >
                {activeProject.project_name}
              </h2>
              <p
                data-testid="planner-next-action"
                className="mt-1 max-w-3xl text-sm leading-relaxed text-silver"
              >
                {plannerNextActionCopy(activeProject.start_approach)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                data-testid="planner-start-approach-context"
                className="rounded border border-border bg-bg3/40 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk"
              >
                {startApproachLabel(activeProject.start_approach)}
              </span>
              <button
                type="button"
                onClick={onOpenMyWork}
                data-testid="planner-manage-my-work"
                className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-1.5 text-xs font-mono font-bold text-cyan hover:bg-cyan/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/80"
              >
                Manage in My Work
              </button>
            </div>
          </div>
          <div className="relative flex flex-col items-start gap-2 lg:items-end">
            <div className="flex flex-wrap items-center justify-start gap-2 lg:justify-end">
              <span
                data-testid="planner-project-status"
                className="rounded border border-border bg-bg3/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver"
              >
                {projectStatusLabel(activeProject.status)}
              </span>
              <span className="rounded border border-border bg-bg3/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
                This browser
              </span>
              <button
                type="button"
                onClick={() => {
                  setActionsOpen((open) => !open);
                  setConfirmDeleteOpen(false);
                }}
                data-testid="planner-plan-actions"
                aria-haspopup="menu"
                aria-expanded={actionsOpen}
                aria-controls="planner-plan-actions-menu"
                className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-1.5 text-xs font-mono font-bold text-silver hover:border-orange/45 hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
              >
                <MoreHorizontal size={14} />
                Plan actions
              </button>
            </div>
            {actionsOpen ? (
              <div
                id="planner-plan-actions-menu"
                role="menu"
                data-testid="planner-plan-actions-menu"
                className="w-full rounded-chunk-lg border border-border bg-bg1 p-2 shadow-metal lg:w-64"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => setConfirmDeleteOpen(true)}
                  data-testid="planner-delete-plan-menu-item"
                  className="flex w-full items-center gap-2 rounded border border-transparent px-3 py-2 text-left text-xs font-mono font-bold text-red hover:border-red/35 hover:bg-red/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red/70"
                >
                  <Trash2 size={14} />
                  {deleteActionLabel}
                </button>
              </div>
            ) : null}
            {confirmDeleteOpen ? (
              <div
                role="alertdialog"
                aria-labelledby="planner-delete-confirm-title"
                aria-describedby="planner-delete-confirm-body"
                data-testid="planner-delete-confirmation"
                className="w-full rounded-chunk-lg border border-red/45 bg-red/10 p-3 text-sm text-silver lg:w-80"
              >
                <h3 id="planner-delete-confirm-title" className="font-display text-sm tracking-[0.12em] text-red">
                  {activeProject.status === 'draft' ? 'Delete this draft?' : 'Delete this plan?'}
                </h3>
                <div id="planner-delete-confirm-body" className="mt-2 space-y-1 leading-relaxed">
                  <p>Delete “{activeProject.project_name}” from My Work.</p>
                  <p>Your saved system will stay.</p>
                  <p>{plannedStructureDeletionCopy(plannedStructureCount, deleteItemKind)}</p>
                  <p>This cannot be undone.</p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const deletedProjectName = activeProject.project_name;
                      const deleted = onDeleteActiveProject?.() ?? false;
                      setConfirmDeleteOpen(false);
                      setActionsOpen(false);
                      if (deleted) {
                        onPlanDeleted?.(deletedProjectName);
                        onOpenMyWork?.();
                      }
                    }}
                    data-testid="planner-confirm-delete"
                    className="rounded-chunk-sm border border-red/50 bg-red/20 px-3 py-2 text-xs font-mono font-bold text-red hover:bg-red/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red/80"
                  >
                    {deleteActionLabel}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteOpen(false)}
                    data-testid="planner-cancel-delete"
                    className="rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
                  >
                    {keepActionLabel}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </header>
  );
}
