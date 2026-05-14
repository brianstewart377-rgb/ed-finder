import { Play } from 'lucide-react';
import { PlanBadge } from './StartModes';
import type { StartMode } from './types';

export function ColonyPlannerHeader({
  initialPlanLabel,
  startMode,
  hasRecommendedBuild,
  canRun,
  running,
  onRunPreview,
}: {
  initialPlanLabel?: string | null;
  startMode: StartMode;
  hasRecommendedBuild: boolean;
  canRun: boolean;
  running: boolean;
  onRunPreview: () => void;
}) {
  return (
    <div className="px-4 py-3 border-b border-border/70 bg-orange/5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-orange text-sm font-bold tracking-[0.18em] uppercase">
            Colony Planner
          </h3>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            Plan a colony build for this system. Generate candidate plans, compare them with your editable build plan, and run a preview before doing anything in-game.
          </p>
          {initialPlanLabel && (
            <p className="mt-1 text-[11px] text-orange font-mono">
              You are previewing the {initialPlanLabel}.
            </p>
          )}
        </div>
        <PlanBadge mode={startMode} hasRecommendedBuild={hasRecommendedBuild} />
        <button
          type="button"
          onClick={onRunPreview}
          disabled={!canRun}
          className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 disabled:opacity-45 disabled:cursor-not-allowed"
        >
          <Play size={14} />
          {running ? 'Running' : 'Run Preview'}
        </button>
      </div>
    </div>
  );
}
