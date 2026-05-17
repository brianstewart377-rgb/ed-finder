import { ArrowLeft, ExternalLink, Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatPopulation } from '@/lib/format';
import type { SystemDetail } from '@/types/api';
import { useSystemDetail } from '@/features/system-detail/useSystemDetail';
import { SimulationPreviewPanel } from '@/features/system-detail/SimulationPreviewPanel';

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
      <section className="panel p-4 sm:p-5">
        <div className="mb-4 grid gap-3 border-b border-border pb-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0">
            <h2 className="font-mono text-[13px] uppercase tracking-[0.18em] text-orange">
              Colony Planner Workspace
            </h2>
            <p className="mt-1 max-w-3xl text-xs font-mono leading-snug text-silver-dk">
              Evaluate this system as a planning workspace: Suggested Builds, Build Plan, then Preview Result.
              Nothing runs or loads automatically.
            </p>
          </div>
          <PlannerWorkflowStrip />
        </div>
        <SimulationPreviewPanel system={data} selectedPlan={null} />
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
    <header className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-silver-dk">
            Colony Planner Workspace
          </div>
          <h1 className="mt-1 truncate font-display text-2xl tracking-[0.12em] text-orange">
            {system.name || 'Unknown system'}
          </h1>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
            ID64 <span className="text-silver tabular-nums">{system.id64}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
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
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 text-xs font-mono font-bold text-cyan hover:bg-cyan/20"
          >
            <ExternalLink size={14} />
            Open full system detail
          </button>
        </div>
      </div>

      <dl className="mt-4 grid gap-2 text-xs font-mono sm:grid-cols-2 lg:grid-cols-4">
        <HeaderFact label="Coordinates" value={coords || 'Unknown'} tone="cyan" />
        <HeaderFact label="Suggested economy" value={system.economy_suggestion ?? system.primary_economy ?? 'Unknown'} tone="orange" />
        <HeaderFact label="Status" value={status} tone={system.is_colonised ? 'red' : 'green'} />
        <HeaderFact label="Population" value={population} />
      </dl>
    </header>
  );
}

function HeaderFact({
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
    <div className="rounded-chunk-sm border border-border bg-bg3/50 px-3 py-2">
      <dt className="text-[10px] uppercase tracking-[0.16em] text-silver-dk">{label}</dt>
      <dd className={['mt-1 truncate text-silver', toneClass].join(' ')}>{value}</dd>
    </div>
  );
}

function PlannerWorkflowStrip() {
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Colony Planner flow</div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-mono">
        <FlowChip step="1" label="Suggested Builds" tone="primary" />
        <FlowChip step="2" label="Build Plan" tone="primary" />
        <FlowChip step="3" label="Preview Result" tone="primary" />
        <FlowChip step="4" label="Observed Evidence" tone="later" />
        <FlowChip step="5" label="Validation" tone="later" />
      </div>
      <p className="mt-2 text-[10px] font-mono leading-snug text-silver-dk">
        Observed Evidence and Validation are later-step checks after planning and in-game verification.
      </p>
    </div>
  );
}

function FlowChip({
  step,
  label,
  tone,
}: {
  step: string;
  label: string;
  tone: 'primary' | 'later';
}) {
  return (
    <span className={[
      'inline-flex items-center gap-1 rounded border px-1.5 py-0.5',
      tone === 'primary'
        ? 'border-orange/35 bg-orange/10 text-orange'
        : 'border-border/70 bg-bg3/40 text-silver-dk',
    ].join(' ')}>
      <span className="text-[9px] uppercase tracking-[0.08em]">{step}</span>
      <span>{label}</span>
    </span>
  );
}
