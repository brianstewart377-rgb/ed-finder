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
            Plan a colony build for this system in a dedicated planning workflow. Start with Suggested Builds if you are unsure, compare them with your editable Build Plan, and run Preview before doing anything in-game.
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
      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
        <WorkflowChip step="1" label="Suggested Builds" tone="primary" />
        <WorkflowChip step="2" label="Build Plan" tone="primary" />
        <WorkflowChip step="3" label="Preview Result" tone="primary" />
        <WorkflowChip step="4" label="Observed Evidence - Later step" tone="later" />
        <WorkflowChip step="5" label="Validation - Later step" tone="later" />
      </div>
    </div>
  );
}

function WorkflowChip({
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
