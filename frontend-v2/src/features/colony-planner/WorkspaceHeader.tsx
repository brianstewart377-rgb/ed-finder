import { ArrowLeft, ExternalLink } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatPopulation } from '@/lib/format';
import type { SystemDetail } from '@/types/api';

export function WorkspaceHeaderSkeleton({
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

export function WorkspaceHeader({
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
