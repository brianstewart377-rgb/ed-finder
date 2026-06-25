import { ArrowLeft, Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { getProvenanceCockpit, getWarehousePlannerEvidence } from '@/lib/api';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WholeSystemColonyPlanner } from './WholeSystemColonyPlanner';
import { WarehouseEvidenceCard } from './WarehouseEvidenceCard';
import { WorkspaceHeader, WorkspaceHeaderSkeleton } from './WorkspaceHeader';
import { toWarehouseEvidenceFromContract, toWarehouseEvidenceFromProvenance } from './warehouseEvidenceBridge';
import type { ColonyProject } from './colonyProjectStore';

export interface ColonyPlannerWorkspaceProps {
  id64: number | null;
  projectId?: string | null;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
  onOpenMyWork?: () => void;
  onPlanDeleted?: (projectName: string) => void;
}

export function ColonyPlannerWorkspace({
  id64,
  projectId = null,
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
  const { data, loading, error, refetch } = useSystemDetail(id64);
  const warehouseEvidenceQuery = useQuery({
    queryKey: ['planner-workspace-warehouse-planner-evidence', id64],
    queryFn: () => getWarehousePlannerEvidence(id64 as number),
    enabled: id64 != null,
    retry: 1,
    staleTime: 60_000,
  });
  const provenanceQuery = useQuery({
    queryKey: ['planner-workspace-provenance-cockpit', id64],
    queryFn: () => getProvenanceCockpit(id64 as number),
    enabled: id64 != null && warehouseEvidenceQuery.isError,
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
        onOpenMyWork={onOpenMyWork}
        onPlanDeleted={onPlanDeleted}
        activeProject={projectContext.activeProject}
        unsavedChanges={projectContext.unsavedChanges}
        plannedStructureCount={projectContext.plannedStructureCount}
        onDeleteActiveProject={projectContext.deleteActiveProject}
      />
      <WholeSystemColonyPlanner
        system={data}
        initialProjectId={projectId}
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
