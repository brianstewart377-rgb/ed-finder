import { Compass, FileSearch, FileUp, GitBranch, Hammer, ListTree, Play, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';

export type SimulationWorkspaceMode = 'build-plan' | 'suggested-builds' | 'preview' | 'sequence' | 'map' | 'evidence' | 'validation' | 'export';

export const WORKSPACE_MODE_META: Record<SimulationWorkspaceMode, {
  label: string;
  helper: string;
  summary: string;
  emphasis: string;
  nextModes: SimulationWorkspaceMode[];
}> = {
  'build-plan': {
    label: 'Build Plan',
    helper: 'Edit placements',
    summary: 'Shape the canonical colony layout and keep it editable.',
    emphasis: 'Best when you need to add, move, or replace facilities before trusting any downstream review surface.',
    nextModes: ['suggested-builds', 'preview', 'sequence'],
  },
  'suggested-builds': {
    label: 'Suggested Builds',
    helper: 'Compare options',
    summary: 'Review ranked candidate plans without overwriting the editable plan.',
    emphasis: 'Best when you want option space and tradeoffs before committing the current plan.',
    nextModes: ['build-plan', 'preview', 'validation'],
  },
  preview: {
    label: 'Preview',
    helper: 'Review result',
    summary: 'See the predicted outcome for the current build plan.',
    emphasis: 'Best when you need a current mechanics read before checking evidence or export readiness.',
    nextModes: ['sequence', 'evidence', 'validation'],
  },
  sequence: {
    label: 'Sequence',
    helper: 'CP tradeoffs',
    summary: 'Inspect build order and colony-point tradeoffs before finalising.',
    emphasis: 'Best when the plan shape is settled and you want execution-aware sequencing.',
    nextModes: ['preview', 'validation', 'export'],
  },
  map: {
    label: 'Map',
    helper: 'Spatial context',
    summary: 'Keep spatial orientation visible without leaving the cockpit.',
    emphasis: 'Best when body layout matters more than list editing for the next planning move.',
    nextModes: ['build-plan', 'sequence', 'evidence'],
  },
  evidence: {
    label: 'Evidence',
    helper: 'Manual facts',
    summary: 'Review observed facts as read-only context beside the canonical plan.',
    emphasis: 'Best when you need to compare in-game observations without mutating planner truth.',
    nextModes: ['validation', 'export', 'build-plan'],
  },
  validation: {
    label: 'Validation',
    helper: 'Compare signals',
    summary: 'Compare prediction and observed evidence to judge confidence.',
    emphasis: 'Best when you need to understand where the plan is confirmed, contradicted, or still uncertain.',
    nextModes: ['evidence', 'export', 'build-plan'],
  },
  export: {
    label: 'Export',
    helper: 'Review packs',
    summary: 'Check readiness before sharing or carrying the plan outward.',
    emphasis: 'Best when the plan, evidence, and validation story are ready to be packed into reviewable output.',
    nextModes: ['validation', 'evidence', 'build-plan'],
  },
};

const MODES: Array<{
  id: SimulationWorkspaceMode;
  label: string;
  helper: string;
  icon: ReactNode;
}> = [
  { id: 'build-plan', label: 'Build Plan', helper: 'Edit placements', icon: <Hammer size={14} /> },
  { id: 'suggested-builds', label: 'Suggested Builds', helper: 'Compare options', icon: <ListTree size={14} /> },
  { id: 'preview', label: 'Preview', helper: 'Review result', icon: <Play size={14} /> },
  { id: 'sequence', label: 'Sequence', helper: 'CP tradeoffs', icon: <GitBranch size={14} /> },
  { id: 'map', label: 'Map', helper: 'Spatial context', icon: <Compass size={14} /> },
  { id: 'evidence', label: 'Evidence', helper: 'Manual facts', icon: <FileSearch size={14} /> },
  { id: 'validation', label: 'Validation', helper: 'Compare signals', icon: <ShieldCheck size={14} /> },
  { id: 'export', label: 'Export', helper: 'Review packs', icon: <FileUp size={14} /> },
];

export function workspaceModeLabel(mode: SimulationWorkspaceMode): string {
  return WORKSPACE_MODE_META[mode].label;
}

export function WorkspaceModeTabs({
  activeMode,
  onModeChange,
}: {
  activeMode: SimulationWorkspaceMode;
  onModeChange: (mode: SimulationWorkspaceMode) => void;
}) {
  return (
    <nav
      aria-label="Planner workspace modes"
      data-testid="workspace-mode-tabs"
      className="border-b border-border/60 bg-bg2/35 px-3 py-2"
    >
      <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-8">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            aria-pressed={activeMode === mode.id}
            onClick={() => onModeChange(mode.id)}
            data-testid={`workspace-mode-tab-${mode.id}`}
            className={[
              'flex min-h-[3.25rem] items-center gap-2 rounded border px-2 py-1.5 text-left font-mono transition-colors',
              activeMode === mode.id
                ? 'border-orange/60 bg-orange/15 text-orange'
                : 'border-border/65 bg-bg3/35 text-silver-dk hover:border-cyan/45 hover:text-silver',
            ].join(' ')}
          >
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded border border-current/35 bg-bg1/45">
              {mode.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-[10px] font-bold uppercase tracking-[0.12em]">{mode.label}</span>
              <span className="block truncate text-[10px] normal-case tracking-normal">{mode.helper}</span>
            </span>
          </button>
        ))}
      </div>
    </nav>
  );
}
