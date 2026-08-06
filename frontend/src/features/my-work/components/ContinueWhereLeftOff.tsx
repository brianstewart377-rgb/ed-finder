import type { ColonyProject } from '@/features/colony-planner/colonyProjectStore';
import {
  formatRecentActivity,
  labelText,
  projectStatusLabel,
  selectContinuation,
} from '../myWorkWorkspaceUtils';

export function ContinueWhereLeftOff({
  continuation,
  onInspectSystem,
  onContinuePlan,
}: {
  continuation: ReturnType<typeof selectContinuation>;
  onInspectSystem: (id64: number) => void;
  onContinuePlan: (project: ColonyProject) => void;
}) {
  if (!continuation) return null;
  if (continuation.kind === 'plan') {
    return (
      <section data-testid="my-work-continuation" className="premium-subpanel border-orange/35 bg-orange/8 p-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange">Continue planning</p>
        <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
          {continuation.project.system_name} - {continuation.project.project_name}
        </h2>
        <p className="mt-1 text-sm text-silver">
          {projectStatusLabel(continuation.project.status)} · Updated {formatRecentActivity(continuation.project.updated_at)}
        </p>
        <button
          type="button"
          onClick={() => onContinuePlan(continuation.project)}
          className="btn-primary mt-3 text-[11px] font-mono"
        >
          Continue plan
        </button>
      </section>
    );
  }

  return (
    <section data-testid="my-work-continuation" className="premium-subpanel border-cyan/35 bg-cyan/8 p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">Ready to revisit</p>
      <h2 className="mt-2 font-display text-lg tracking-[0.1em] text-text">
        {continuation.system.name}
      </h2>
      <p className="mt-1 text-sm text-silver">
        Saved as {continuation.system.labels.map(labelText).join(' · ')} · No plan yet
      </p>
      <button
        type="button"
        onClick={() => onInspectSystem(continuation.system.id64)}
        className="mt-3 rounded-chunk-sm border border-cyan/45 bg-cyan/10 px-3 py-1.5 font-mono text-[11px] font-bold text-cyan shadow-[0_14px_24px_-20px_rgba(34,211,238,0.8)] transition-colors hover:bg-cyan/20"
      >
        Inspect system
      </button>
    </section>
  );
}
