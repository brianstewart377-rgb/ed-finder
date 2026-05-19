import { FileSearch, Hammer, ListTree, Play, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';

export type SimulationWorkspaceMode = 'build-plan' | 'suggested-builds' | 'preview' | 'evidence' | 'validation';

const MODES: Array<{
  id: SimulationWorkspaceMode;
  label: string;
  helper: string;
  icon: ReactNode;
}> = [
  { id: 'build-plan', label: 'Build Plan', helper: 'Edit placements', icon: <Hammer size={14} /> },
  { id: 'suggested-builds', label: 'Suggested Builds', helper: 'Compare options', icon: <ListTree size={14} /> },
  { id: 'preview', label: 'Preview', helper: 'Review result', icon: <Play size={14} /> },
  { id: 'evidence', label: 'Evidence', helper: 'Manual facts', icon: <FileSearch size={14} /> },
  { id: 'validation', label: 'Validation', helper: 'Compare signals', icon: <ShieldCheck size={14} /> },
];

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
      <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-5">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            aria-pressed={activeMode === mode.id}
            onClick={() => onModeChange(mode.id)}
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
