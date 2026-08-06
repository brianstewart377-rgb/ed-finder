import type {
  ColonyProject,
  ColonyProjectStatus,
} from '@/features/colony-planner/colonyProjectStore';
import {
  objectiveSummaryLabel,
  startApproachLabel,
} from '@/features/colony-planner/plannerDraftContext';
import { humanizeArchetype } from '@/features/colony-planner/workspaceUtils';
import { formatTimestamp, projectStatusLabel } from '../myWorkWorkspaceUtils';

export function PlanCard({
  project,
  isEditing,
  editingName,
  onEditNameChange,
  onBeginRename,
  onSaveRename,
  onCancelRename,
  onDuplicate,
  onArchive,
  onStatusChange,
  onContinue,
  onInspectSystem,
  onToggleColonised,
  isExplicitlyColonised,
}: {
  project: ColonyProject;
  isEditing: boolean;
  editingName: string;
  onEditNameChange: (value: string) => void;
  onBeginRename: () => void;
  onSaveRename: () => void;
  onCancelRename: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
  onStatusChange: (status: ColonyProjectStatus) => void;
  onContinue: () => void;
  onInspectSystem: () => void;
  onToggleColonised: (enabled: boolean) => void;
  isExplicitlyColonised: boolean;
}) {
  return (
    <article data-testid={`plan-card-${project.id}`} className="premium-subpanel p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          {isEditing ? (
            <div className="flex flex-wrap gap-2">
              <input
                value={editingName}
                onChange={(event) => onEditNameChange(event.target.value)}
                className="min-w-[18rem] flex-1 rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-xs text-silver"
              />
              <button
                type="button"
                onClick={onSaveRename}
                className="btn-primary text-[11px] font-mono"
              >
                Save name
              </button>
              <button
                type="button"
                onClick={onCancelRename}
                className="btn-metal text-[11px] font-mono"
              >
                Cancel
              </button>
            </div>
          ) : (
            <h3 className="truncate font-display text-sm tracking-[0.1em] text-text">
              {project.project_name}
            </h3>
          )}
          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-silver-dk">
            <span>Objective: {objectiveSummaryLabel(project.objective)}</span>
            <span>Start: {startApproachLabel(project.start_approach)}</span>
            <span>Saved locally</span>
            <span>Updated {formatTimestamp(project.updated_at)}</span>
          </div>
          <div className="grid gap-2 text-[11px] font-mono text-silver sm:grid-cols-2">
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Plan health: {project.build_plan_placements.length} placements · {humanizeArchetype(project.target_archetype)}
            </div>
            <div className="premium-toolbar rounded-xl px-2 py-1.5">
              Status: {projectStatusLabel(project.status)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onContinue}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
          <button
            type="button"
            onClick={onInspectSystem}
            className="btn-metal text-[11px] font-mono"
          >
            Inspect system
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Status
        </label>
        <select
          data-testid={`plan-status-${project.id}`}
          value={project.status}
          onChange={(event) => onStatusChange(event.target.value as ColonyProjectStatus)}
          className="rounded border border-border/70 bg-bg2/80 px-2 py-1.5 font-mono text-[11px] text-silver"
        >
          <option value="draft">Draft</option>
          <option value="ready_to_build">Ready to build</option>
          <option value="building">Building</option>
          <option value="established">Established</option>
        </select>
        <button
          type="button"
          onClick={onBeginRename}
          className="btn-metal text-[11px] font-mono"
        >
          Rename
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="btn-metal text-[11px] font-mono"
        >
          Duplicate
        </button>
        <button
          type="button"
          onClick={onArchive}
          className="rounded border border-gold/35 bg-gold/10 px-3 py-1.5 font-mono text-[11px] text-gold hover:bg-gold/20"
        >
          Archive
        </button>
      </div>
      {project.status === 'established' ? (
        <div className="premium-subpanel mt-3 border-violet/30 bg-violet/8 px-3 py-2 text-sm text-silver">
          <p>
            Established is still player-managed planning state. Use the action below if you also want this system to appear in My Colonies as explicitly colonised.
          </p>
          <button
            type="button"
            onClick={() => onToggleColonised(!isExplicitlyColonised)}
            className="mt-2 rounded border border-violet/35 bg-violet/12 px-3 py-1.5 font-mono text-[11px] text-violet hover:bg-violet/20"
          >
            {isExplicitlyColonised ? 'Remove colonised mark' : 'Mark system colonised'}
          </button>
        </div>
      ) : null}
    </article>
  );
}
