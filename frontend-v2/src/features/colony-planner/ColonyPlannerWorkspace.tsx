import { ArrowLeft, ExternalLink, PanelRight, Rocket } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { formatPopulation } from '@/lib/format';
import type { SimulateBuildRequest, SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';
import {
  ColonyTopologyRail,
  describeTopologySelection,
  type TopologyPlanSnapshot,
  type TopologySelection,
} from './ColonyTopologyRail';
import {
  activeProjectsForSystem,
  projectMatchesSnapshot,
  useColonyProjectStore,
  type ColonyProject,
} from './colonyProjectStore';

export interface ColonyPlannerWorkspaceProps {
  id64: number | null;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
}

export function ColonyPlannerWorkspace({
  id64,
  onBackToFinder,
  onOpenSystemDetail,
}: ColonyPlannerWorkspaceProps) {
  const { data, loading, error, refetch } = useSystemDetail(id64);

  if (id64 == null) {
    return (
      <WorkspaceShell>
        <EmptyWorkspace onBackToFinder={onBackToFinder} />
      </WorkspaceShell>
    );
  }

  if (loading) {
    return (
      <WorkspaceShell>
        <WorkspaceHeaderSkeleton id64={id64} onBackToFinder={onBackToFinder} />
        <div className="panel p-8 text-center font-mono text-sm text-text-dim">
          Loading Colony Planner...
        </div>
      </WorkspaceShell>
    );
  }

  if (error || !data) {
    return (
      <WorkspaceShell>
        <WorkspaceHeaderSkeleton id64={id64} onBackToFinder={onBackToFinder} />
        <div className="panel border-red/45 bg-red/10 p-5 font-mono text-sm text-red">
          <div className="font-bold">Failed to load Colony Planner.</div>
          <div className="mt-1 text-xs text-red/85">{error ?? 'System detail was unavailable.'}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={refetch}
              className="rounded-chunk-sm border border-red/50 bg-red/10 px-3 py-2 text-xs font-bold text-red hover:bg-red/20"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={onBackToFinder}
              className="rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-bold text-text-dim hover:text-orange"
            >
              Back to Finder
            </button>
          </div>
        </div>
      </WorkspaceShell>
    );
  }

  return (
    <WorkspaceShell>
      <WorkspaceHeader
        system={data}
        onBackToFinder={onBackToFinder}
        onOpenSystemDetail={onOpenSystemDetail}
      />
      <WorkspaceGrid system={data} />
    </WorkspaceShell>
  );
}

function WorkspaceShell({ children }: { children: ReactNode }) {
  return (
    <section data-testid="colony-planner-workspace" className="space-y-5">
      {children}
    </section>
  );
}

function EmptyWorkspace({ onBackToFinder }: { onBackToFinder: () => void }) {
  return (
    <div className="panel p-6 sm:p-8 text-center">
      <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-full border border-orange/35 bg-orange/10 text-orange">
        <Rocket size={22} />
      </div>
      <h1 className="font-display text-xl tracking-[0.14em] text-orange">
        No system selected for Colony Planner.
      </h1>
      <p className="mx-auto mt-2 max-w-xl font-mono text-xs leading-relaxed text-silver-dk">
        Choose Evaluate in Colony Planner from Finder or Advanced Search Tuning.
      </p>
      <button
        type="button"
        onClick={onBackToFinder}
        className="mt-5 inline-flex items-center gap-2 rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/20"
      >
        <ArrowLeft size={14} />
        Back to Finder
      </button>
    </div>
  );
}

function WorkspaceHeaderSkeleton({
  id64,
  onBackToFinder,
}: {
  id64: number;
  onBackToFinder: () => void;
}) {
  return (
    <header className="panel flex flex-wrap items-start justify-between gap-4 p-5">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-silver-dk">
          Colony Planner Workspace
        </div>
        <h1 className="mt-1 font-display text-xl tracking-[0.14em] text-orange">
          Loading system...
        </h1>
        <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
          ID64 <span className="text-silver tabular-nums">{id64}</span>
        </div>
      </div>
      <button
        type="button"
        onClick={onBackToFinder}
        className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange"
      >
        <ArrowLeft size={14} />
        Back to Finder
      </button>
    </header>
  );
}

function WorkspaceHeader({
  system,
  onBackToFinder,
  onOpenSystemDetail,
}: {
  system: SystemDetail;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
}) {
  const population = system.population && system.population > 0
    ? formatPopulation(system.population)
    : 'Uncolonised';
  const status = system.is_colonised ? 'Colonised' : 'Free';
  const coords = [
    system.x?.toFixed(2),
    system.y?.toFixed(2),
    system.z?.toFixed(2),
  ].filter((value): value is string => value != null).join(', ');

  return (
    <header className="panel overflow-hidden p-4 sm:p-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
            <span>Colony Planner Workspace</span>
            <span className="rounded border border-orange/35 bg-orange/10 px-1.5 py-0.5 text-orange">
              Stage 15D topology
            </span>
            <span className="rounded border border-cyan/30 bg-cyan/5 px-1.5 py-0.5 text-cyan">
              {status}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-1">
            <h1 className="min-w-0 truncate font-display text-2xl tracking-[0.12em] text-orange">
              {system.name || 'Unknown system'}
            </h1>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              ID64 <span className="text-silver tabular-nums">{system.id64}</span>
            </div>
          </div>
          <dl className="mt-3 flex flex-wrap gap-2 text-[10px] font-mono">
            <HeaderPill label="Coords" value={coords || 'Unknown'} tone="cyan" />
            <HeaderPill label="Economy" value={system.economy_suggestion ?? system.primary_economy ?? 'Unknown'} tone="orange" />
            <HeaderPill label="Population" value={population} />
          </dl>
        </div>
        <div className="flex flex-wrap gap-2 xl:justify-end">
          <button
            type="button"
            onClick={onBackToFinder}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-mono font-bold text-silver hover:text-orange"
          >
            <ArrowLeft size={14} />
            Back to Finder
          </button>
          <button
            type="button"
            onClick={() => onOpenSystemDetail(system.id64)}
            data-testid="back-to-system-detail"
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20"
          >
            <ExternalLink size={14} />
            Back to system detail
          </button>
        </div>
      </div>
    </header>
  );
}

function HeaderPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: 'cyan' | 'orange' | 'green' | 'red';
}) {
  const toneClass = {
    cyan: 'text-cyan',
    orange: 'text-orange',
    green: 'text-green',
    red: 'text-red',
  }[tone ?? 'cyan'];

  return (
    <div className="inline-flex min-w-0 items-center gap-1.5 rounded border border-border bg-bg3/50 px-2 py-1">
      <dt className="shrink-0 uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className={['min-w-0 truncate text-silver', toneClass].join(' ')}>{value}</dd>
    </div>
  );
}

function WorkspaceGrid({ system }: { system: SystemDetail }) {
  const [selection, setSelection] = useState<TopologySelection>({ type: 'system' });
  const [planSnapshot, setPlanSnapshot] = useState<TopologyPlanSnapshot>({
    placements: [],
    templates: [],
    targetArchetype: 'refinery_industrial',
  });
  const projects = useColonyProjectStore((state) => state.projects);
  const saveProject = useColonyProjectStore((state) => state.saveProject);
  const renameProject = useColonyProjectStore((state) => state.renameProject);
  const duplicateProject = useColonyProjectStore((state) => state.duplicateProject);
  const archiveProject = useColonyProjectStore((state) => state.archiveProject);
  const systemProjects = useMemo(() => activeProjectsForSystem(projects, system.id64), [projects, system.id64]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(() => systemProjects[0]?.id ?? null);
  const [pendingProjectId, setPendingProjectId] = useState<string>('');
  const [projectName, setProjectName] = useState(`${system.name || 'Colony'} project`);
  const [projectNotes, setProjectNotes] = useState('');
  const [confirmArchive, setConfirmArchive] = useState(false);
  const activeProject = systemProjects.find((project) => project.id === activeProjectId) ?? null;

  useEffect(() => {
    if (activeProjectId && systemProjects.some((project) => project.id === activeProjectId)) return;
    const next = systemProjects[0] ?? null;
    setActiveProjectId(next?.id ?? null);
  }, [activeProjectId, systemProjects]);

  useEffect(() => {
    setPendingProjectId(activeProjectId ?? '');
    setProjectName(activeProject?.project_name ?? `${system.name || 'Colony'} project`);
    setProjectNotes(activeProject?.notes ?? '');
    setConfirmArchive(false);
  }, [activeProject, activeProjectId, system.name]);

  const handlePlanSnapshotChange = useCallback((snapshot: TopologyPlanSnapshot) => {
    setPlanSnapshot(snapshot);
  }, []);
  const projectRequest = useMemo<SimulateBuildRequest | null>(() => {
    if (!activeProject) return null;
    return {
      system_id64: activeProject.system_id64,
      target_archetype: activeProject.target_archetype,
      placements: activeProject.build_plan_placements,
    };
  }, [activeProject]);
  const selectedContext = useMemo(
    () => describeTopologySelection(selection, system, planSnapshot),
    [planSnapshot, selection, system],
  );
  const unsavedChanges = !projectMatchesSnapshot(
    activeProject,
    planSnapshot.placements,
    planSnapshot.targetArchetype,
    projectNotes,
    projectName,
  );
  const handleSaveProject = () => {
    const saved = saveProject(activeProject?.id ?? null, {
      system_id64: system.id64,
      system_name: system.name || 'Unknown system',
      project_name: projectName,
      build_plan_placements: planSnapshot.placements,
      target_archetype: planSnapshot.targetArchetype,
      notes: projectNotes,
      status: 'draft',
    });
    setActiveProjectId(saved.id);
  };
  const handleRenameProject = () => {
    if (!activeProject) return;
    renameProject(activeProject.id, projectName);
  };
  const handleDuplicateProject = () => {
    if (!activeProject) return;
    const duplicate = duplicateProject(activeProject.id);
    if (duplicate) setActiveProjectId(duplicate.id);
  };
  const handleArchiveProject = () => {
    if (!activeProject) return;
    archiveProject(activeProject.id);
    setConfirmArchive(false);
    setActiveProjectId(null);
  };

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
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-border/70 pb-3">
          <div>
            <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-orange">
              Planning Workspace
            </h2>
            <p className="mt-1 max-w-2xl text-[11px] font-mono leading-snug text-silver-dk">
              Existing planner tools remain here while topology selection stays read-only.
            </p>
          </div>
          <span className="rounded border border-cyan/30 bg-cyan/5 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            Contained planner
          </span>
        </div>
        <SimulationPreviewPanel
          system={system}
          selectedPlan={null}
          onPlanSnapshotChange={handlePlanSnapshotChange}
          topologySelection={selection}
          initialRequest={projectRequest}
        />
      </main>
      <SummaryPanel
        system={system}
        snapshot={planSnapshot}
        selectedContext={selectedContext}
        projects={systemProjects}
        activeProject={activeProject}
        pendingProjectId={pendingProjectId}
        projectName={projectName}
        projectNotes={projectNotes}
        unsavedChanges={unsavedChanges}
        confirmArchive={confirmArchive}
        onPendingProjectChange={setPendingProjectId}
        onLoadProject={() => setActiveProjectId(pendingProjectId || null)}
        onProjectNameChange={setProjectName}
        onProjectNotesChange={setProjectNotes}
        onSaveProject={handleSaveProject}
        onRenameProject={handleRenameProject}
        onDuplicateProject={handleDuplicateProject}
        onArchiveProject={handleArchiveProject}
        onConfirmArchiveChange={setConfirmArchive}
      />
    </section>
  );
}

function SummaryPanel({
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
  selectedContext: ReturnType<typeof describeTopologySelection>;
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
  const bodyCount = system.bodies?.length ?? 0;
  const stationCount = system.stations?.length ?? 0;
  const projectState = activeProject
    ? activeProject.project_name
    : 'Unsaved workspace';
  const architectState = 'Architect flag not observed';
  const plannerState = 'Preview remains explicit';

  return (
    <aside
      aria-label="Workspace summary"
      data-testid="planner-summary-panel"
      className="panel p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
        <PanelRight size={13} />
        Planner summary
      </div>
      <p className="mt-2 text-[11px] leading-snug text-silver-dk">
        Local saved project context lives here first; evidence and validation drawers remain deferred.
      </p>

      <dl className="mt-3 space-y-2 font-mono text-[10px]">
        <SummaryRow label="Project" value={projectState} tone={unsavedChanges ? 'gold' : 'green'} />
        <SummaryRow label="Changes" value={unsavedChanges ? 'Unsaved changes' : 'Saved'} tone={unsavedChanges ? 'gold' : 'green'} />
        <SummaryRow label="Last saved" value={formatProjectTimestamp(activeProject?.updated_at)} />
        <SummaryRow label="Planner" value={plannerState} tone="cyan" />
        <SummaryRow label="Bodies loaded" value={String(bodyCount)} />
        <SummaryRow label="Stations loaded" value={String(stationCount)} />
        <SummaryRow label="Plan placements" value={String(snapshot.placements.length)} tone="orange" />
        <SummaryRow label="Selected" value={selectedContext.label} tone="cyan" />
        <SummaryRow label="Selected type" value={selectedContext.kind} />
        <SummaryRow label="Selection placements" value={String(selectedContext.placementCount)} />
        <SummaryRow label="Selection warnings" value={String(selectedContext.warningCount)} tone={selectedContext.warningCount > 0 ? 'gold' : undefined} />
        <SummaryRow label="Architect" value={architectState} tone="gold" />
        <SummaryRow label="Suggested economy" value={system.economy_suggestion ?? system.primary_economy ?? 'Unknown'} tone="orange" />
      </dl>

      <section className="mt-4 rounded border border-orange/25 bg-orange/5 p-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
          Read-only topology selection
        </h3>
        <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
          {selectedContext.detail}
        </p>
        <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
          {selectedContext.architectStatus}
        </p>
      </section>

      <ProjectPanel
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

      <section className="mt-4 rounded border border-cyan/25 bg-cyan/5 p-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
          Workspace modes
        </h3>
        <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
          <ModeChip label="Plan" active />
          <ModeChip label="Preview" />
          <ModeChip label="Evidence" />
          <ModeChip label="Validation" />
        </div>
      </section>

      <section className="mt-3 rounded border border-border/60 bg-bg3/30 p-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">
          Deferred to next stages
        </h3>
        <ul className="mt-2 space-y-1 font-mono text-[10px] text-silver-dk">
          <li>15H: evidence and validation drawers</li>
          <li>15I: workspace QA hardening</li>
        </ul>
      </section>
    </aside>
  );
}

function ProjectPanel({
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
    <section className="mt-4 rounded border border-cyan/25 bg-cyan/5 p-2" data-testid="colony-project-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
          Saved project
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
            className="w-full"
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

      <p className="mt-2 font-mono text-[10px] leading-snug text-silver-dk">
        Local-only MVP. No account sync or backend persistence is used.
      </p>
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

function formatProjectTimestamp(value?: string | null) {
  if (!value) return 'Not saved';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function ModeChip({ label, active = false }: { label: string; active?: boolean }) {
  return (
    <span
      className={[
        'rounded border px-1.5 py-0.5',
        active
          ? 'border-orange/40 bg-orange/10 text-orange'
          : 'border-border/60 bg-bg2/55 text-silver-dk',
      ].join(' ')}
    >
      {label}
    </span>
  );
}
