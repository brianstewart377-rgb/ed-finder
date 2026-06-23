import { ArrowLeft, ExternalLink } from 'lucide-react';
import { formatCoords, formatPopulationForSystem, systemStatusLabel } from '@/lib/format';
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
        journeyLabel="Journey stage: Plan"
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
  activeProject,
  unsavedChanges,
}: {
  system: SystemDetail;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
  activeProject?: ColonyProject | null;
  unsavedChanges?: boolean;
}) {
  const population = formatPopulationForSystem(system);
  const status = systemStatusLabel(system);
  const coords = formatCoords(system, system.id64);
  const statusTone = status === 'Colonised'
    ? 'canonical'
    : status === 'Colonising'
      ? 'caution'
      : 'available';

  return (
    <header className="panel overflow-hidden p-4 sm:p-5">
      <WorkspaceContextHeader
        testId="workspace-context-header"
        journeyLabel="Journey stage: Plan"
        title="Colony Planner"
        supportingText="Build the selected system with canonical planner data, then review read-only evidence separately before committing to assumptions."
        selectedSystemName={system.name || 'Unknown system'}
        selectedSystemMeta={<span className="tabular-nums">ID64 {system.id64}</span>}
        status={<SemanticStatusBadge label={status} tone={statusTone} />}
        facts={[
          { label: 'Coords', value: coords, tone: 'cyan' },
          { label: 'Economy', value: system.economy_suggestion ?? system.primary_economy ?? 'Unknown', tone: 'orange' },
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
          className="mt-4 grid gap-3 rounded-chunk-lg border border-orange/30 bg-bg3/30 p-3 lg:grid-cols-[minmax(0,1fr)_auto]"
        >
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-orange">
                Active draft
              </span>
              <SemanticStatusBadge label="Draft" tone="available" />
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
          </div>
          <dl className="grid gap-2 text-[11px] font-mono sm:grid-cols-2 lg:min-w-[22rem]">
            <div className="rounded border border-border bg-bg2/60 px-2 py-1.5">
              <dt className="uppercase tracking-[0.14em] text-silver-dk">Objective</dt>
              <dd data-testid="planner-objective-context" className="mt-1 text-text">
                {objectiveSummaryLabel(activeProject.objective)}
              </dd>
            </div>
            <div className="rounded border border-border bg-bg2/60 px-2 py-1.5">
              <dt className="uppercase tracking-[0.14em] text-silver-dk">Start</dt>
              <dd data-testid="planner-start-approach-context" className="mt-1 text-text">
                {startApproachLabel(activeProject.start_approach)}
              </dd>
            </div>
            <div className="rounded border border-border bg-bg2/60 px-2 py-1.5">
              <dt className="uppercase tracking-[0.14em] text-silver-dk">Project status</dt>
              <dd data-testid="planner-project-status" className="mt-1 text-text">
                {projectStatusLabel(activeProject.status)}
              </dd>
            </div>
            <div className="rounded border border-border bg-bg2/60 px-2 py-1.5">
              <dt className="uppercase tracking-[0.14em] text-silver-dk">Saved in</dt>
              <dd className="mt-1 text-text">This browser</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </header>
  );
}
