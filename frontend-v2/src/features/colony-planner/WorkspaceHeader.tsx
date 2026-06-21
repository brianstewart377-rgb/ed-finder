import { ArrowLeft, ExternalLink } from 'lucide-react';
import { formatCoords, formatPopulationForSystem, systemStatusLabel } from '@/lib/format';
import type { SystemDetail } from '@/types/api';
import { SemanticStatusBadge } from '@/components/SemanticStatusBadge';
import { WorkspaceContextHeader } from '@/components/WorkspaceContextHeader';

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
}: {
  system: SystemDetail;
  onBackToFinder: () => void;
  onOpenSystemDetail: (id64: number) => void;
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
    </header>
  );
}
