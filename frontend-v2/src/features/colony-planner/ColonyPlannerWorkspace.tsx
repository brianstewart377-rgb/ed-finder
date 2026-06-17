import { ArrowLeft, Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { getProvenanceCockpit, getWarehousePlannerEvidence } from '@/lib/api';
import { WholeSystemColonyPlanner } from './WholeSystemColonyPlanner';
import { WarehouseEvidenceCard } from './WarehouseEvidenceCard';
import { WorkspaceHeader, WorkspaceHeaderSkeleton } from './WorkspaceHeader';
import { toWarehouseEvidenceFromContract, toWarehouseEvidenceFromProvenance } from './warehouseEvidenceBridge';

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
    enabled: id64 != null && (
      warehouseEvidenceQuery.isError
      || warehouseEvidenceQuery.data?.evidence_summary.availability === 'unavailable'
    ),
    retry: 1,
    staleTime: 60_000,
  });
  const warehouseEvidence = useMemo(() => {
    const primaryEvidence = toWarehouseEvidenceFromContract(warehouseEvidenceQuery.data);
    if (primaryEvidence && primaryEvidence.availability !== 'unavailable') {
      return primaryEvidence;
    }
    return toWarehouseEvidenceFromProvenance(provenanceQuery.data) ?? primaryEvidence;
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
      />
      <WholeSystemColonyPlanner system={data} />
      {/*
       * Stage 18H.3: fetch the dedicated read-only warehouse planner evidence
       * contract first, then fall back to the existing provenance cockpit
       * bridge whenever the endpoint returns unavailable or cannot be read.
       * The planner still treats the result as report-only context only.
       */}
      <WarehouseEvidenceCard evidence={warehouseEvidence} />
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
