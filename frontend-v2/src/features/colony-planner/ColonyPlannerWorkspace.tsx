import { ArrowLeft, Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getProvenanceCockpit, getWarehousePlannerEvidence } from '@/lib/api';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WholeSystemColonyPlanner } from './WholeSystemColonyPlanner';
import { WarehouseEvidenceCard } from './WarehouseEvidenceCard';
import { WorkspaceHeader, WorkspaceHeaderSkeleton } from './WorkspaceHeader';
import { toWarehouseEvidenceFromContract, toWarehouseEvidenceFromProvenance } from './warehouseEvidenceBridge';
import { useColonyProjectStore, type ColonyProject } from './colonyProjectStore';
import type { SystemDetail } from '@/types/api';

export interface ColonyPlannerWorkspaceProps {
  id64: number | null;
  projectId?: string | null;
  invalidSystemRoute?: boolean;
  invalidProjectRoute?: boolean;
  system: SystemDetail | null;
  systemLoading?: boolean;
  systemError?: string | null;
  onRetrySystem?: () => void;
  onCreateDraft: (system: SystemDetail) => void;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
  onOpenMyWork?: () => void;
  onPlanDeleted?: (projectName: string) => void;
}

export function ColonyPlannerWorkspace({
  id64,
  projectId = null,
  invalidSystemRoute = false,
  invalidProjectRoute = false,
  system,
  systemLoading = false,
  systemError = null,
  onRetrySystem,
  onCreateDraft,
  onBackToFinder,
  onOpenSystemDetail,
  onOpenMyWork,
  onPlanDeleted,
}: ColonyPlannerWorkspaceProps) {
  const [projectContext, setProjectContext] = useState<{
    activeProject: ColonyProject | null;
    unsavedChanges: boolean;
    plannedStructureCount: number;
    deleteActiveProject?: () => boolean;
  }>({
    activeProject: null,
    unsavedChanges: false,
    plannedStructureCount: 0,
  });
  const projects = useColonyProjectStore((state) => state.projects);
  const warehouseEvidenceQuery = useQuery({
    queryKey: ['planner-workspace-warehouse-planner-evidence', id64],
    queryFn: () => getWarehousePlannerEvidence(id64 as number),
    enabled: id64 != null && system != null,
    retry: 1,
    staleTime: 60_000,
  });
  const provenanceQuery = useQuery({
    queryKey: ['planner-workspace-provenance-cockpit', id64],
    queryFn: () => getProvenanceCockpit(id64 as number),
    enabled: id64 != null && system != null && warehouseEvidenceQuery.isError,
    retry: 1,
    staleTime: 60_000,
  });
  const warehouseEvidence = useMemo(() => {
    const primaryEvidence = toWarehouseEvidenceFromContract(warehouseEvidenceQuery.data);
    if (primaryEvidence) {
      return primaryEvidence;
    }
    return toWarehouseEvidenceFromProvenance(provenanceQuery.data);
  }, [provenanceQuery.data, warehouseEvidenceQuery.data]);
  const routeProject = useMemo(() => {
    if (projectId == null) return null;
    const trimmed = projectId.trim();
    if (!trimmed) {
      return { state: 'malformed' as const, project: null };
    }
    const project = projects[trimmed] ?? null;
    if (!project) {
      return { state: 'missing' as const, project: null };
    }
    if (project.archived_at) {
      return { state: 'archived' as const, project };
    }
    if (id64 != null && project.system_id64 !== id64) {
      return { state: 'cross-system' as const, project };
    }
    return { state: 'active' as const, project };
  }, [id64, projectId, projects]);
  const projectErrorState = invalidProjectRoute
    ? 'malformed'
    : routeProject?.state === 'active'
      ? 'missing'
      : (routeProject?.state ?? 'missing');

  if (invalidSystemRoute) {
    return (
      <WorkspaceShell>
        <InlineWorkspaceState
          title="Selected system route invalid"
          detail="The planner route did not contain a valid system ID. Select a system from Finder to continue."
          actions={(
            <button
              type="button"
              onClick={onBackToFinder}
              className="rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-bold text-orange hover:bg-orange/20"
            >
              Back to Finder
            </button>
          )}
        />
      </WorkspaceShell>
    );
  }

  if (systemLoading) {
    return (
      <WorkspaceShell>
        <WorkspaceHeaderSkeleton id64={id64 ?? 0} onBackToFinder={onBackToFinder} />
        <div className="panel p-8 text-center font-mono text-sm text-text-dim">
          Loading Colony Planner...
        </div>
      </WorkspaceShell>
    );
  }

  if (id64 == null) {
    return (
      <WorkspaceShell>
        <EmptyWorkspace onBackToFinder={onBackToFinder} />
      </WorkspaceShell>
    );
  }

  if (systemError || !system) {
    return (
      <WorkspaceShell>
        <WorkspaceHeaderSkeleton id64={id64} onBackToFinder={onBackToFinder} />
        <div className="panel border-red/45 bg-red/10 p-5 font-mono text-sm text-red">
          <div className="font-bold">Selected system unavailable.</div>
          <div className="mt-1 text-xs text-red/85">{systemError ?? 'System detail was unavailable.'}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            {onRetrySystem ? (
              <button
                type="button"
                onClick={onRetrySystem}
                className="rounded-chunk-sm border border-red/50 bg-red/10 px-3 py-2 text-xs font-bold text-red hover:bg-red/20"
              >
                Retry
              </button>
            ) : null}
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

  if (projectId == null) {
    return (
      <WorkspaceShell>
        <WorkspaceHeader
          system={system}
          onBackToFinder={onBackToFinder}
          onOpenSystemDetail={onOpenSystemDetail}
          onOpenMyWork={onOpenMyWork}
          onPlanDeleted={onPlanDeleted}
          activeProject={null}
          unsavedChanges={false}
          plannedStructureCount={0}
        />
        <InlineWorkspaceState
          title="No active draft for this system"
          detail="Create a draft when you are ready to edit this system in the planner."
          actions={(
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onCreateDraft(system)}
                className="rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-bold text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
              >
                Create draft
              </button>
              <button
                type="button"
                onClick={onBackToFinder}
                className="rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-bold text-text-dim hover:text-orange"
              >
                Back to Finder
              </button>
            </div>
          )}
        />
      </WorkspaceShell>
    );
  }

  if (invalidProjectRoute || routeProject?.state !== 'active' || !routeProject.project) {
    return (
      <WorkspaceShell>
        <WorkspaceHeader
          system={system}
          onBackToFinder={onBackToFinder}
          onOpenSystemDetail={onOpenSystemDetail}
          onOpenMyWork={onOpenMyWork}
          onPlanDeleted={onPlanDeleted}
          activeProject={null}
          unsavedChanges={false}
          plannedStructureCount={0}
        />
        <InlineWorkspaceState
          title={plannerProjectErrorTitle(projectErrorState)}
          detail={plannerProjectErrorDetail(projectErrorState, system.name || 'this system')}
          actions={(
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onCreateDraft(system)}
                className="rounded-chunk-sm border border-orange/45 bg-orange/10 px-3 py-2 text-xs font-bold text-orange hover:bg-orange/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80"
              >
                Create draft
              </button>
              {onOpenMyWork ? (
                <button
                  type="button"
                  onClick={onOpenMyWork}
                  className="rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-bold text-text-dim hover:text-orange"
                >
                  Open My Work
                </button>
              ) : null}
              <button
                type="button"
                onClick={onBackToFinder}
                className="rounded-chunk-sm border border-border bg-bg4 px-3 py-2 text-xs font-bold text-text-dim hover:text-orange"
              >
                Back to Finder
              </button>
            </div>
          )}
        />
      </WorkspaceShell>
    );
  }

  return (
    <WorkspaceShell>
      <WorkspaceHeader
        system={system}
        onBackToFinder={onBackToFinder}
        onOpenSystemDetail={onOpenSystemDetail}
        onOpenMyWork={onOpenMyWork}
        onPlanDeleted={onPlanDeleted}
        activeProject={projectContext.activeProject}
        unsavedChanges={projectContext.unsavedChanges}
        plannedStructureCount={projectContext.plannedStructureCount}
        onDeleteActiveProject={projectContext.deleteActiveProject}
      />
      <WholeSystemColonyPlanner
        system={system}
        initialProjectId={routeProject.project.id}
        onProjectContextChange={setProjectContext}
      />
      {/*
       * Stage 18H.3: fetch the dedicated read-only warehouse planner evidence
       * contract first, then fall back to the existing provenance cockpit
       * bridge only when the endpoint cannot be read.
       * The planner still treats the result as report-only context only.
       */}
      <section
        data-testid="planner-evidence-discoverability-surface"
        className="space-y-3"
      >
        <div className="panel-thin p-4 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display tracking-[0.14em] text-orange-lt text-sm">
              Review evidence
            </h2>
            <SemanticStatusBadge
              label="Report-only context"
              tone="report_only"
            />
            <span className="px-1.5 py-0.5 rounded border border-border bg-bg4 text-[11px] uppercase tracking-wider text-text-dim">
              Selected-system context
            </span>
          </div>
          <p
            data-testid="planner-evidence-discoverability-summary"
            className="text-sm leading-relaxed text-silver"
          >
            Selected-system evidence stays separate from canonical planner truth. Review it when you need system-specific context, then keep planning on canonical data.
          </p>
        </div>
        <WarehouseEvidenceCard evidence={warehouseEvidence} />
      </section>
    </WorkspaceShell>
  );
}

function plannerProjectErrorTitle(state: 'malformed' | 'missing' | 'archived' | 'cross-system') {
  switch (state) {
    case 'archived':
      return 'Selected project is archived';
    case 'cross-system':
      return 'Selected project does not belong to this system';
    case 'malformed':
      return 'Selected project route invalid';
    case 'missing':
    default:
      return 'Selected project unavailable';
  }
}

function plannerProjectErrorDetail(state: 'malformed' | 'missing' | 'archived' | 'cross-system', systemName: string) {
  switch (state) {
    case 'archived':
      return 'The requested draft was archived and cannot be opened from this route.';
    case 'cross-system':
      return `The requested draft belongs to a different system. Select ${systemName} again and create a fresh draft if needed.`;
    case 'malformed':
      return 'The planner route did not contain a valid project ID.';
    case 'missing':
    default:
      return 'The requested draft could not be found in local planner storage.';
  }
}

function InlineWorkspaceState({
  title,
  detail,
  actions,
}: {
  title: string;
  detail: string;
  actions: ReactNode;
}) {
  return (
    <div className="panel border-orange/30 bg-bg3/20 p-5" data-testid="planner-inline-state">
      <h2 className="font-display text-lg tracking-[0.12em] text-orange">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-silver">{detail}</p>
      <div className="mt-4">{actions}</div>
    </div>
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
        Open System Detail from Explore and start a plan there, or continue with an existing direct planner route.
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
