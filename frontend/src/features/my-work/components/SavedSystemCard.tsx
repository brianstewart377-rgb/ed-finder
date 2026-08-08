import type { SavedSystemViewModel } from '../myWorkWorkspaceUtils';
import { formatTimestamp } from '../myWorkWorkspaceUtils';
import type { JournalTelemetryRecentSystem } from '@/types/api';

export function SavedSystemCard({
  system,
  telemetry,
  onInspect,
  onStartPlan,
  onContinuePlan,
  onToggleConsidering,
  onToggleFavourite,
  onToggleReadyToPlan,
  onRemove,
}: {
  system: SavedSystemViewModel;
  telemetry: JournalTelemetryRecentSystem | null;
  onInspect: () => void;
  onStartPlan: () => void;
  onContinuePlan: () => void;
  onToggleConsidering: (enabled: boolean) => void;
  onToggleFavourite: (enabled: boolean) => void;
  onToggleReadyToPlan: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <li data-testid={`saved-system-${system.id64}`} className="premium-subpanel flex flex-wrap items-start justify-between gap-4 p-4">
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-base tracking-[0.1em] text-text">
              {system.name}
            </h2>
            {system.activeProject ? (
              <span className="rounded border border-orange/35 bg-orange/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange">
                Has active plan
              </span>
            ) : null}
            {system.isColonised ? (
              <span className="rounded border border-violet/35 bg-violet/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-violet">
                Colonised
              </span>
            ) : null}
            {telemetry ? (
              <span className="rounded border border-cyan/35 bg-cyan/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
                Personal telemetry imported
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-[11px] text-silver-dk">
            {system.planCount} associated plan{system.planCount === 1 ? '' : 's'}
            {system.latestPlanActivity ? ` · latest plan update ${formatTimestamp(system.latestPlanActivity)}` : ''}
          </p>
          {telemetry ? (
            <p className="mt-1 text-sm text-silver">
              Last observed {formatTimestamp(telemetry.last_observed_at)} · {telemetry.event_count} telemetry event{telemetry.event_count === 1 ? '' : 's'} · {telemetry.event_types.join(', ')}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <LabelToggle
            active={system.labels.includes('considering')}
            label="Considering"
            onClick={() => onToggleConsidering(!system.labels.includes('considering'))}
          />
          <LabelToggle
            active={system.labels.includes('favourite')}
            label="Favourite"
            onClick={() => onToggleFavourite(!system.labels.includes('favourite'))}
          />
          <LabelToggle
            active={system.labels.includes('ready_to_plan')}
            label="Ready to plan"
            onClick={() => onToggleReadyToPlan(!system.labels.includes('ready_to_plan'))}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onInspect}
          className="btn-metal text-[11px] font-mono"
        >
          Inspect
        </button>
        {system.activeProject ? (
          <button
            type="button"
            onClick={onContinuePlan}
            className="btn-primary text-[11px] font-mono"
          >
            Continue plan
          </button>
        ) : (
          <button
            type="button"
            onClick={onStartPlan}
            className="btn-primary text-[11px] font-mono"
          >
            Start plan
          </button>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="rounded border border-red/40 bg-red/10 px-3 py-1.5 font-mono text-[11px] text-red hover:bg-red/20"
        >
          Remove from saved
        </button>
      </div>
    </li>
  );
}

function LabelToggle({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        'rounded border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors',
        active
          ? 'border-orange/50 bg-orange/12 text-orange'
          : 'border-border bg-bg3/35 text-silver-dk hover:border-orange/35 hover:text-orange-lt',
      ].join(' ')}
    >
      {label}
      {' '}
      <span className="sr-only">{active ? 'enabled' : 'disabled'}</span>
    </button>
  );
}
