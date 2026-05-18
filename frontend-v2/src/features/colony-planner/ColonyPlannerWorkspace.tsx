import { ArrowLeft, ExternalLink, Network, PanelRight, Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatPopulation } from '@/lib/format';
import type { SystemBody, SystemDetail } from '@/types/api';
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
              Stage 15B shell
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
  return (
    <section
      aria-label="Colony Planner application shell"
      data-testid="planner-workspace-shell-v2"
      className="grid gap-4 xl:grid-cols-[18rem_minmax(0,1fr)_20rem] xl:items-start"
    >
      <TopologySidebar system={system} />
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
              Existing planner tools remain here while topology editing moves into the workspace shell.
            </p>
          </div>
          <span className="rounded border border-cyan/30 bg-cyan/5 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            Contained planner
          </span>
        </div>
        <SimulationPreviewPanel system={system} selectedPlan={null} />
      </main>
      <SummaryPanel system={system} />
    </section>
  );
}

function TopologySidebar({ system }: { system: SystemDetail }) {
  const bodies = system.bodies ?? [];
  const stars = bodies.filter((body) => body.body_type === 'Star').length;
  const planets = bodies.filter((body) => body.body_type === 'Planet').length;
  const moons = Math.max(0, bodies.length - stars - planets);
  const notableBodies = bodies.filter(isNotableBody).slice(0, 5);

  return (
    <aside
      aria-label="Topology sidebar"
      data-testid="planner-topology-sidebar"
      className="panel p-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-14rem)] xl:overflow-y-auto"
    >
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">
        <Network size={13} />
        System topology
      </div>
      <p className="mt-2 text-[11px] leading-snug text-silver-dk">
        Body tree navigation lands in Stage 15D. For now, this rail keeps the planning workspace oriented around the system layout.
      </p>

      <div className="mt-3 grid gap-2 font-mono text-[10px]">
        <SidebarStat label="Bodies" value={String(bodies.length)} tone="orange" />
        <SidebarStat label="Stars" value={String(stars)} />
        <SidebarStat label="Planets" value={String(planets)} />
        <SidebarStat label="Moons/other" value={String(moons)} />
      </div>

      <section className="mt-4 rounded border border-border/60 bg-bg3/30 p-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">
          Body tree placeholder
        </h3>
        {notableBodies.length > 0 ? (
          <ul className="mt-2 space-y-1">
            {notableBodies.map((body) => (
              <li key={body.id ?? body.name} className="rounded border border-border/45 bg-bg2/55 px-2 py-1.5">
                <div className="truncate font-mono text-[11px] text-silver">{body.name ?? `Body ${body.id}`}</div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-silver-dk">
                  {body.subtype ?? body.body_type ?? 'Unknown body'}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 rounded border border-border/45 bg-bg2/45 px-2 py-2 font-mono text-[10px] text-silver-dk">
            No detailed body rows are loaded for this system.
          </p>
        )}
      </section>

      <section className="mt-3 rounded border border-gold/30 bg-gold/5 p-2">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
          Unassigned placements
        </h3>
        <p className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
          Future topology editing will surface placements that still need a body or slot assignment here.
        </p>
      </section>
    </aside>
  );
}

function SummaryPanel({ system }: { system: SystemDetail }) {
  const bodyCount = system.bodies?.length ?? 0;
  const stationCount = system.stations?.length ?? 0;
  const projectState = 'Unsaved workspace';
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
        Persistent project context lives here first; saved projects and validation drawers remain deferred.
      </p>

      <dl className="mt-3 space-y-2 font-mono text-[10px]">
        <SummaryRow label="Project" value={projectState} tone="gold" />
        <SummaryRow label="Planner" value={plannerState} tone="cyan" />
        <SummaryRow label="Bodies loaded" value={String(bodyCount)} />
        <SummaryRow label="Stations loaded" value={String(stationCount)} />
        <SummaryRow label="Architect" value={architectState} tone="gold" />
        <SummaryRow label="Suggested economy" value={system.economy_suggestion ?? system.primary_economy ?? 'Unknown'} tone="orange" />
      </dl>

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
          <li>15C: System Detail simplification</li>
          <li>15D: interactive body tree MVP</li>
          <li>15G: saved colony projects</li>
        </ul>
      </section>
    </aside>
  );
}

function SidebarStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'orange' | 'cyan';
}) {
  const toneClass = tone === 'orange' ? 'text-orange' : 'text-cyan';
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-border/55 bg-bg3/35 px-2 py-1.5">
      <span className="uppercase tracking-[0.14em] text-silver-dk">{label}</span>
      <span className={['tabular-nums', toneClass].join(' ')}>{value}</span>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: 'orange' | 'cyan' | 'gold';
}) {
  const toneClass = tone === 'orange'
    ? 'text-orange'
    : tone === 'gold'
      ? 'text-gold'
      : tone === 'cyan'
        ? 'text-cyan'
        : 'text-silver';
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-2 py-1.5">
      <dt className="uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className={['mt-0.5 break-words text-[11px]', toneClass].join(' ')}>{value}</dd>
    </div>
  );
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

function isNotableBody(body: SystemBody): boolean {
  return Boolean(
    body.is_earth_like
    || body.is_water_world
    || body.is_ammonia_world
    || body.is_landable
    || body.is_terraformable
    || body.body_type === 'Star',
  );
}
