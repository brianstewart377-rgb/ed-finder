import type { ColonyProject } from './colonyProjectStore';

export function ProjectControlsCard({
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
  return (
    <section className="rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="project-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
          Project
        </h3>
        <span
          data-testid="project-unsaved-indicator"
          className={[
            'rounded border px-1.5 py-0.5 font-mono text-[10px]',
            unsavedChanges ? 'border-gold/45 bg-gold/10 text-gold' : 'border-green/35 bg-green/10 text-green',
          ].join(' ')}
        >
          {unsavedChanges ? 'Unsaved changes' : 'Saved'}
        </span>
      </div>

      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        Saved locally in this browser. Not cloud synced.
      </p>

      <label className="mt-2 block space-y-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Project name</span>
        <input
          aria-label="Project name"
          value={projectName}
          onChange={(event) => onProjectNameChange(event.target.value)}
          className="w-full rounded border border-border/70 bg-bg2 px-2 py-1.5 font-mono text-xs text-silver"
        />
      </label>

      <label className="mt-2 block space-y-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Notes</span>
        <textarea
          aria-label="Project notes"
          value={projectNotes}
          onChange={(event) => onProjectNotesChange(event.target.value)}
          rows={3}
          className="w-full resize-y rounded border border-border/70 bg-bg2 px-2 py-1.5 font-mono text-xs text-silver"
        />
      </label>

      <div className="mt-2 grid gap-2">
        <button type="button" onClick={onSaveProject} className="rounded border border-orange/45 bg-orange/10 px-2 py-1.5 font-mono text-[11px] font-bold text-orange hover:bg-orange/20">
          Save project
        </button>
        <button type="button" onClick={onRenameProject} disabled={!activeProject} className="rounded border border-border/70 bg-bg3 px-2 py-1.5 font-mono text-[11px] text-silver hover:border-cyan/50 disabled:opacity-45">
          Rename project
        </button>
      </div>

      <div className="mt-3 rounded border border-border/55 bg-bg3/30 p-2">
        <label className="block space-y-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Load project</span>
          <select
            aria-label="Load project"
            value={pendingProjectId}
            onChange={(event) => onPendingProjectChange(event.target.value)}
            className="w-full rounded border border-border/70 bg-bg2 px-2 py-1.5 font-mono text-xs text-silver"
          >
            <option value="">No saved project selected</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </label>
        <div className="mt-2 grid gap-2">
          <button type="button" onClick={onLoadProject} disabled={!pendingProjectId} className="rounded border border-cyan/45 bg-cyan/10 px-2 py-1.5 font-mono text-[11px] text-cyan hover:bg-cyan/20 disabled:opacity-45">
            Load project
          </button>
          <button type="button" onClick={onDuplicateProject} disabled={!activeProject} className="rounded border border-border/70 bg-bg3 px-2 py-1.5 font-mono text-[11px] text-silver hover:border-cyan/50 disabled:opacity-45">
            Duplicate project
          </button>
        </div>
      </div>

      <div className="mt-3 rounded border border-gold/30 bg-gold/5 p-2">
        {confirmArchive ? (
          <div>
            <p className="font-mono text-[10px] leading-snug text-gold">
              Archive this local project? The current workspace remains open, but the saved project is removed from this system list.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" onClick={() => onConfirmArchiveChange(false)} className="rounded border border-border bg-bg3 px-2 py-1 font-mono text-[10px] text-silver">
                Cancel
              </button>
              <button type="button" onClick={onArchiveProject} className="rounded border border-gold/45 bg-gold/10 px-2 py-1 font-mono text-[10px] font-bold text-gold">
                Archive project
              </button>
            </div>
          </div>
        ) : (
          <button type="button" onClick={() => onConfirmArchiveChange(true)} disabled={!activeProject} className="w-full rounded border border-gold/40 bg-gold/10 px-2 py-1.5 font-mono text-[11px] text-gold hover:bg-gold/20 disabled:opacity-45">
            Delete / archive project
          </button>
        )}
      </div>
    </section>
  );
}
